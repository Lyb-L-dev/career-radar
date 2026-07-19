"""OpenAI/Anthropic 供应商适配、长页面切片和结构化结果合并。"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from .discovery import (
    PageDocument,
    application_links,
    extract_application_method,
    is_irrelevant_link,
)
from .job_merge import is_same_job, merge_job_postings
from .models import (
    CandidateProfile,
    JobPosting,
    LLMConfig,
    PageAnalysis,
    SocialReputationAnalysis,
)
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .url_utils import canonicalize_url, resolve_http_url

LOGGER = logging.getLogger(__name__)

_EMAIL_PATTERN = re.compile(r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.I)

REPUTATION_SYSTEM_PROMPT = """你是谨慎的求职背调分析员。输入是社交平台公开搜索结果，不是经核实的事实。
只能归纳输入中明确出现的内容；不得根据公司名气、学校背景或单一帖子臆测。
每个主题结论必须引用输入中存在的 evidence_id。证据少、过旧、互相冲突或只有标题时，
必须降低 confidence，并明确写出信息不足。不得输出作者个人敏感信息，不得使用侮辱性标签。
重点分析工作强度、单双休、薪资福利、管理氛围、成长空间、稳定性、岗位边界和面试体验。
必须区分 relevance_scope：job 表示文本同时命中公司与具体岗位，company 表示只命中公司。
公司级评价不得被表述为该具体岗位的既定情况；只能作为面试时需要核实的公司层面线索。
"""


class LLMError(RuntimeError):
    """模型认证、请求、拒绝或结构化解析失败。"""


class RetryableLLMError(LLMError):
    """限流、服务端错误、连接超时或模型临时返回无效结构，可安全重试。"""


class FatalLLMError(LLMError):
    """认证、权限、模型/参数不存在等永久性错误，继续重试没有意义。"""


_RETRYABLE_EXCEPTION_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "RateLimitError",
    "ServiceUnavailableError",
}
_FATAL_EXCEPTION_NAMES = {
    "AuthenticationError",
    "BadRequestError",
    "NotFoundError",
    "PermissionDeniedError",
    "UnprocessableEntityError",
}
_FATAL_BILLING_CODES = {
    "billing_not_active",
    "credit_balance_too_low",
    "insufficient_balance",
    "insufficient_quota",
}


def _error_status(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    if value is None:
        value = getattr(getattr(exc, "response", None), "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _error_code(exc: Exception) -> str:
    direct = getattr(exc, "code", None)
    if direct:
        return str(direct).casefold()
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict) and error.get("code"):
            return str(error["code"]).casefold()
    return ""


def _request_error(provider: str, exc: Exception) -> LLMError:
    """把不同 SDK 的异常统一为可重试/永久错误，避免依赖供应商具体类。"""

    status = _error_status(exc)
    code = _error_code(exc)
    name = type(exc).__name__
    message = f"{provider} 请求失败：{name}: {exc}"
    if code in _FATAL_BILLING_CODES:
        return FatalLLMError(message)
    if status in {408, 409, 425, 429} or (status is not None and status >= 500):
        return RetryableLLMError(message)
    if status is not None and 400 <= status < 500:
        return FatalLLMError(message)
    if name in _RETRYABLE_EXCEPTION_NAMES or isinstance(exc, (TimeoutError, ConnectionError)):
        return RetryableLLMError(message)
    if name in _FATAL_EXCEPTION_NAMES:
        return FatalLLMError(message)
    # 未分类异常通常是 SDK 用法或程序错误。保守地立即失败，避免重复发送同一请求。
    return FatalLLMError(message)


class LLMProvider(ABC):
    """供应商无关的页面分析接口。"""

    @abstractmethod
    def analyze(self, user_prompt: str) -> PageAnalysis:
        """把单个完整页面或切片转换为 ``PageAnalysis``。"""

    def analyze_reputation(self, user_prompt: str) -> SocialReputationAnalysis:
        """分析公开社交证据；测试替身可不实现，真实供应商必须覆盖。"""

        raise FatalLLMError("当前 LLM 供应商未实现社交口碑分析")


def _require_api_key(variable_name: str, provider_name: str) -> str:
    """读取 API Key，并把模板占位符识别为“尚未配置”。"""

    value = os.getenv(variable_name, "").strip()
    if not value or "your-" in value.casefold() or value.casefold().endswith("api-key"):
        raise FatalLLMError(
            f"缺少有效的 {variable_name}，请在 .env 中填写 {provider_name} API Key"
        )
    return value


def _extract_json_object(text: str, provider_name: str) -> dict[str, Any]:
    """从纯 JSON 或 Markdown 代码块中读取第一个完整 JSON 对象。"""

    start = text.find("{")
    if start < 0:
        raise RetryableLLMError(f"{provider_name} 响应中没有 JSON 对象")
    try:
        value, _end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise RetryableLLMError(f"{provider_name} JSON 解析失败：{exc}") from exc
    if not isinstance(value, dict):
        raise RetryableLLMError(f"{provider_name} 返回的 JSON 顶层不是对象")
    return value


def _validated_mailto(value: str, page_text: str, page_emails: list[str]) -> str | None:
    """只接受正文原样出现的单一邮箱，避免模型虚构地址或注入 mailto 参数。"""

    if not value.casefold().startswith("mailto:"):
        return None
    address = value[7:].split("?", 1)[0].strip()
    if not _EMAIL_PATTERN.fullmatch(address):
        return None
    if address.casefold() not in page_text.casefold() and address.casefold() not in {
        item.casefold() for item in page_emails
    }:
        return None
    return f"mailto:{address}"


def _looks_like_summary(job: JobPosting) -> bool:
    """保守识别只有标题/短介绍、没有职责与任职资格的列表摘要。"""

    if job.record_type == "notice":
        return False
    text_length = len(re.sub(r"\s+", "", job.description or ""))
    requirements_length = len(re.sub(r"\s+", "", job.requirements or ""))
    # 正式官网有不少岗位只写 2～3 条简短职责，但同时给出了明确任职资格；
    # 这类内容虽短，仍是页面能提供的完整 JD，不能仅按 300 字阈值误删。
    return text_length < 80 or (text_length < 180 and requirements_length < 30)


class OpenAIProvider(LLMProvider):
    """使用官方 OpenAI Python SDK 的 Responses API + Pydantic 结构化输出。"""

    def __init__(self, config: LLMConfig) -> None:
        api_key = _require_api_key("OPENAI_API_KEY", "OpenAI")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise FatalLLMError("未安装 openai SDK，请执行 pip install -e .") from exc
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": config.request_timeout_seconds,
            # 统一由 PageAnalyzer 按配置重试，避免 SDK 与外层重试相乘。
            "max_retries": 0,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self.client = OpenAI(**kwargs)
        self.config = config

    def analyze(self, user_prompt: str) -> PageAnalysis:
        """SDK 负责把 Pydantic 模型转成严格 JSON Schema 并校验响应。"""

        try:
            response = self.client.responses.parse(
                model=self.config.model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                text_format=PageAnalysis,
                max_output_tokens=self.config.max_output_tokens,
            )
        except Exception as exc:
            raise _request_error("OpenAI", exc) from exc
        parsed = response.output_parsed
        if parsed is None:
            raise RetryableLLMError(
                "OpenAI 未返回可解析的结构化结果（可能发生拒绝或输出不完整）"
            )
        return parsed

    def analyze_reputation(self, user_prompt: str) -> SocialReputationAnalysis:
        try:
            response = self.client.responses.parse(
                model=self.config.model,
                input=[
                    {"role": "system", "content": REPUTATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                text_format=SocialReputationAnalysis,
                max_output_tokens=min(self.config.max_output_tokens, 12_000),
            )
        except Exception as exc:
            raise _request_error("OpenAI 口碑分析", exc) from exc
        parsed = response.output_parsed
        if parsed is None:
            raise RetryableLLMError("OpenAI 未返回可解析的口碑分析")
        return parsed


class DeepSeekProvider(LLMProvider):
    """使用 OpenAI 兼容的 Chat Completions 接入 DeepSeek JSON Output。"""

    DEFAULT_BASE_URL = "https://api.deepseek.com"

    def __init__(self, config: LLMConfig) -> None:
        api_key = _require_api_key("DEEPSEEK_API_KEY", "DeepSeek")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise FatalLLMError(
                "DeepSeek 适配依赖 openai SDK，请执行 pip install -e ."
            ) from exc
        self.client = OpenAI(
            api_key=api_key,
            base_url=config.base_url or self.DEFAULT_BASE_URL,
            timeout=config.request_timeout_seconds,
            max_retries=0,
        )
        self.config = config

    def analyze(self, user_prompt: str) -> PageAnalysis:
        """请求 DeepSeek 的 JSON Object 模式，再用 Pydantic 做第二次严格校验。"""

        schema = json.dumps(PageAnalysis.model_json_schema(), ensure_ascii=False)
        full_prompt = (
            f"{user_prompt}\n\n请只输出一个 JSON 对象，不要输出 Markdown。"
            f"JSON 必须符合以下 Schema：\n{schema}"
        )
        request: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": full_prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": self.config.max_output_tokens,
        }
        if self.config.disable_thinking:
            # 官方 DeepSeek 支持此扩展；兼容代理不支持时可在 YAML 中关闭。
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            completion = self.client.chat.completions.create(**request)
        except Exception as exc:
            raise _request_error("DeepSeek", exc) from exc
        content = completion.choices[0].message.content or ""
        if not content.strip():
            raise RetryableLLMError("DeepSeek 返回了空 JSON 内容，将由上层重试")
        try:
            return PageAnalysis.model_validate(_extract_json_object(content, "DeepSeek"))
        except Exception as exc:
            if isinstance(exc, LLMError):
                raise
            raise RetryableLLMError(f"DeepSeek 结构化结果校验失败：{exc}") from exc

    def analyze_reputation(self, user_prompt: str) -> SocialReputationAnalysis:
        schema = json.dumps(SocialReputationAnalysis.model_json_schema(), ensure_ascii=False)
        full_prompt = (
            f"{user_prompt}\n\n请只输出一个符合以下 Schema 的 JSON 对象：\n{schema}"
        )
        request: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": REPUTATION_SYSTEM_PROMPT},
                {"role": "user", "content": full_prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": min(self.config.max_output_tokens, 12_000),
        }
        if self.config.disable_thinking:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            completion = self.client.chat.completions.create(**request)
        except Exception as exc:
            raise _request_error("DeepSeek 口碑分析", exc) from exc
        content = completion.choices[0].message.content or ""
        try:
            return SocialReputationAnalysis.model_validate(
                _extract_json_object(content, "DeepSeek")
            )
        except Exception as exc:
            if isinstance(exc, LLMError):
                raise
            raise RetryableLLMError(f"DeepSeek 口碑结构校验失败：{exc}") from exc


class AnthropicProvider(LLMProvider):
    """Anthropic 官方 SDK 适配器。

    为兼容不同 Claude 账号/SDK 版本，这里把 Pydantic JSON Schema 放入提示词，
    再用同一模型做本地严格校验；供应商切换不会影响后续数据库结构。
    """

    def __init__(self, config: LLMConfig) -> None:
        api_key = _require_api_key("ANTHROPIC_API_KEY", "Anthropic")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise FatalLLMError("未安装 anthropic SDK，请执行 pip install -e .") from exc
        self.client = Anthropic(
            api_key=api_key,
            timeout=config.request_timeout_seconds,
            max_retries=0,
        )
        self.config = config

    def analyze(self, user_prompt: str) -> PageAnalysis:
        schema = json.dumps(PageAnalysis.model_json_schema(), ensure_ascii=False)
        full_prompt = f"{user_prompt}\n\n必须只返回符合以下 JSON Schema 的 JSON 对象：\n{schema}"
        try:
            message = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_output_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": full_prompt}],
            )
        except Exception as exc:
            raise _request_error("Anthropic", exc) from exc
        text = "\n".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        try:
            return PageAnalysis.model_validate(_extract_json_object(text, "Claude"))
        except Exception as exc:
            if isinstance(exc, LLMError):
                raise
            raise RetryableLLMError(f"Claude 结构化结果校验失败：{exc}") from exc

    def analyze_reputation(self, user_prompt: str) -> SocialReputationAnalysis:
        schema = json.dumps(SocialReputationAnalysis.model_json_schema(), ensure_ascii=False)
        full_prompt = f"{user_prompt}\n\n必须只返回符合以下 JSON Schema 的 JSON 对象：\n{schema}"
        try:
            message = self.client.messages.create(
                model=self.config.model,
                max_tokens=min(self.config.max_output_tokens, 12_000),
                system=REPUTATION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": full_prompt}],
            )
        except Exception as exc:
            raise _request_error("Claude 口碑分析", exc) from exc
        text = "\n".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        try:
            return SocialReputationAnalysis.model_validate(_extract_json_object(text, "Claude"))
        except Exception as exc:
            if isinstance(exc, LLMError):
                raise
            raise RetryableLLMError(f"Claude 口碑结构校验失败：{exc}") from exc


def create_provider(config: LLMConfig) -> LLMProvider:
    """根据 YAML 选择供应商；API Key 始终由环境变量提供。"""

    if config.provider == "openai":
        return OpenAIProvider(config)
    if config.provider == "deepseek":
        return DeepSeekProvider(config)
    return AnthropicProvider(config)


def _split_text(text: str, size: int, overlap: int) -> list[str]:
    """按字符上限切片，并尽量在换行处断开以保持 JD 段落完整。"""

    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            newline = text.rfind("\n", start + size // 2, end)
            if newline > start:
                end = newline
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _merge_analyses(analyses: list[PageAnalysis]) -> PageAnalysis:
    """把长页面各切片恢复为单个页面结果。"""

    type_rank = {"no_jobs": 0, "career_home": 1, "job_list": 2, "job_detail": 3, "mixed": 4}
    jobs: list[JobPosting] = []
    follow: dict[str, Any] = {}
    notes: list[str] = []
    for analysis in analyses:
        for job in analysis.jobs:
            for index, existing in enumerate(jobs):
                if is_same_job(
                    existing,
                    job,
                    allow_missing_location=False,
                    require_shared_url=False,
                ):
                    jobs[index] = merge_job_postings(
                        existing,
                        job,
                        text_strategy="overlap",
                    )
                    break
            else:
                jobs.append(job)
        for link in analysis.follow_links:
            follow[canonicalize_url(link.url)] = link
        if analysis.notes:
            notes.append(analysis.notes)
    best_type = max(analyses, key=lambda item: type_rank[item.page_type]).page_type
    return PageAnalysis(
        page_type=best_type,
        contains_recruitment_info=any(item.contains_recruitment_info for item in analyses),
        jobs=jobs,
        follow_links=list(follow.values()),
        notes=" | ".join(notes),
    )


class PageAnalyzer:
    """为 LLM 增加重试、长页面切片、URL 校验和统一字段补全。"""

    def __init__(
        self,
        config: LLMConfig,
        provider: LLMProvider,
        candidate_profile: CandidateProfile | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.provider = provider
        self.candidate_profile = candidate_profile or CandidateProfile()
        self.sleeper = sleeper

    def _call_with_retry(self, prompt: str) -> PageAnalysis:
        last_error: RetryableLLMError | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                return self.provider.analyze(prompt)
            except FatalLLMError:
                # API Key、权限、模型或参数错误不会自行恢复，必须立即反馈用户。
                raise
            except RetryableLLMError as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    delay = min(2 ** (attempt - 1), 20)
                    LOGGER.warning(
                        "LLM 瞬时错误，%s 秒后重试（%s/%s）：%s",
                        delay,
                        attempt,
                        self.config.max_retries,
                        exc,
                    )
                    self.sleeper(delay)
            except Exception as exc:
                # 自定义 Provider 未按契约分类的异常通常是程序错误，不能盲目重发。
                raise FatalLLMError(
                    f"LLM Provider 返回未分类异常：{type(exc).__name__}: {exc}"
                ) from exc
        raise RetryableLLMError(
            f"LLM 连续发生瞬时错误 {self.config.max_retries} 次：{last_error}"
        )

    def analyze_page(
        self,
        company: str,
        page_url: str,
        document: PageDocument,
        link_limit: int,
        *,
        monitor_mode: str = "jobs",
    ) -> PageAnalysis:
        """分析页面，并拒绝模型臆造的申请/后续 URL。"""

        chunk_size = self.config.max_input_chars
        chunk_overlap = self.config.chunk_overlap_chars
        dense_job_markers = max(
            document.text.count("工作描述"),
            document.text.count("职位要求"),
            document.text.count("岗位职责"),
            document.text.count("任职资格"),
        )
        if dense_job_markers >= 4:
            # 部分央企 ATS 在一个页面直接展开十余条完整 JD。整页一次返回会生成
            # 很大的 JSON，DeepSeek 容易截断或退化为空列表；拆成较小重叠切片后
            # 再按岗位名/地点合并，既保留全文，也显著提高结构化输出稳定性。
            chunk_size = min(chunk_size, 3_500)
            chunk_overlap = min(chunk_overlap, 800)
            LOGGER.info(
                "检测到同页密集岗位（%s 个字段标记），按 %s 字符切片分析",
                dense_job_markers,
                chunk_size,
            )
        chunks = _split_text(
            document.text,
            chunk_size,
            chunk_overlap,
        )
        analyses: list[PageAnalysis] = []
        for index, chunk in enumerate(chunks, 1):
            prompt = build_user_prompt(
                company,
                page_url,
                document,
                chunk,
                link_limit,
                index,
                len(chunks),
                self.candidate_profile,
                monitor_mode,
            )
            analyses.append(self._call_with_retry(prompt))
        merged = _merge_analyses(analyses)

        allowed = {canonicalize_url(link.url) for link in document.links}
        page_application_links = application_links(document)
        page_apply_set = set(page_application_links)
        page_application_method = extract_application_method(document)
        normalized_jobs: list[JobPosting] = []
        for job in merged.jobs:
            job.company = company
            job.source_url = page_url
            if job.apply_url:
                if job.apply_url.casefold().startswith("mailto:"):
                    validated_email = _validated_mailto(
                        job.apply_url, document.text, document.emails
                    )
                    if validated_email:
                        job.apply_url = validated_email
                    else:
                        LOGGER.warning("丢弃 LLM 返回的非页面邮箱投递地址：%s", job.apply_url)
                        job.apply_url = None
                else:
                    resolved = resolve_http_url(page_url, job.apply_url)
                    canonical = canonicalize_url(resolved) if resolved else None
                    if canonical not in allowed:
                        LOGGER.warning("丢弃 LLM 返回的非页面候选申请链接：%s", job.apply_url)
                        job.apply_url = None
                    else:
                        job.apply_url = canonical

            # LLM 容易遗漏 href 中的邮箱或“立即申请”锚点。详情页（或页面只有一个
            # 岗位）可安全地用页面证据补全；多岗位列表不把第一个申请链接错配给全部岗位。
            can_use_page_wide_application = len(merged.jobs) == 1
            if not job.apply_url and can_use_page_wide_application:
                if page_application_links:
                    job.apply_url = page_application_links[0]
                elif document.emails:
                    job.apply_url = f"mailto:{document.emails[0]}"
            if job.apply_url and job.apply_url.casefold().startswith("mailto:"):
                job.contact_email = job.apply_url[7:].split("?", 1)[0]
            elif not job.contact_email and document.emails and can_use_page_wide_application:
                job.contact_email = document.emails[0]
            if not job.application_method:
                if page_application_method and can_use_page_wide_application:
                    job.application_method = page_application_method
                elif job.contact_email:
                    job.application_method = f"发送简历至 {job.contact_email}"
                elif job.apply_url:
                    job.application_method = "通过企业官网申请链接投递"
            normalized_jobs.append(job)

        valid_follow = []
        for follow in merged.follow_links:
            resolved = resolve_http_url(page_url, follow.url)
            canonical = canonicalize_url(resolved) if resolved else None
            if follow.kind == "job_detail" and canonical in page_apply_set:
                LOGGER.info("申请端点不作为职位详情继续抓取：%s", canonical)
                continue
            if canonical in allowed:
                follow.url = canonical
                valid_follow.append(follow)
            else:
                LOGGER.warning("丢弃 LLM 返回的非页面候选后续链接：%s", follow.url)
        merged.jobs = normalized_jobs
        merged.follow_links = valid_follow

        # 不只依赖 LLM：把页面上高置信的详情锚点强制加入后续队列，避免模型因
        # 列表过长漏掉链接。申请表和新闻页明确排除。
        known_follow = {link.url for link in valid_follow}
        if merged.page_type in {"job_list", "mixed"}:
            for link in document.links:
                if (
                    link.job_score >= 4
                    and link.url not in page_apply_set
                    and not is_irrelevant_link(link.url, link.text)
                    and link.url not in known_follow
                ):
                    from .models import FollowLink

                    valid_follow.append(
                        FollowLink(
                            url=link.url,
                            kind="job_detail",
                            reason="启发式识别到职位详情链接，强制继续抓取完整 JD",
                        )
                    )
                    known_follow.add(link.url)

        detail_links_exist = any(link.kind == "job_detail" for link in valid_follow)
        if merged.page_type in {"job_list", "mixed"} and detail_links_exist:
            summary_count = sum(_looks_like_summary(job) for job in merged.jobs)
            if summary_count:
                LOGGER.info(
                    "列表页存在职位详情链接，忽略 %s 条摘要，强制由详情页提取完整 JD",
                    summary_count,
                )
            merged.jobs = [job for job in merged.jobs if not _looks_like_summary(job)]
        else:
            for job in merged.jobs:
                if _looks_like_summary(job):
                    job.jd_complete = False
                    job.jd_incomplete_reason = (
                        "页面仅提供岗位摘要，未发现可继续访问的职位详情链接"
                        if merged.page_type in {"job_list", "mixed", "career_home"}
                        else "职位详情正文过短或缺少任职资格，无法确认 JD 完整"
                    )
                else:
                    # 页面字段已经达到完整 JD 的最低证据标准时，以本地可复核规则
                    # 覆盖模型偶发的保守误判。
                    job.jd_complete = True
                    job.jd_incomplete_reason = None
        merged.follow_links = valid_follow
        return merged
