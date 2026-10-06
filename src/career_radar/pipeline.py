"""把抓取、智能分析、内存合并、去重、输出和通知串成一次完整运行。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import deque
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo

from .ats_source import ATSSourceError, ats_jobs_to_postings, fetch_ats_jobs
from .crawler import CrawlError, PageFetcher
from .discovery import PageDocument, heuristic_follow_links, is_irrelevant_link, parse_html
from .job_merge import is_same_job, merge_job_postings
from .llm import PageAnalyzer, create_provider
from .mailer import MailError, send_job_email
from .models import (
    CompanyConfig,
    CompanyRunResult,
    JobPosting,
    LinkCandidate,
    MonitorMode,
    PageAnalysis,
    RunResult,
    Settings,
    StoredJobEvent,
)
from .notifications import NotificationError, send_job_notifications
from .official_sources import EXTRACTOR_VERSION, extract_official_jobs
from .output import ReportWriter, prune_expired_reports
from .prompts import SYSTEM_PROMPT
from .report_delivery import notification_events
from .sitemap_discovery import discover_recruitment_urls
from .storage import JobStorage, compute_job_hashes
from .url_utils import (
    canonicalize_crawl_url,
    canonicalize_url,
    crawl_path_key,
    normalize_request_url,
)

LOGGER = logging.getLogger(__name__)

PageProgressCallback = Callable[[str, dict[str, Any]], None]
CompanyStartCallback = Callable[[CompanyConfig], None]
CompanyCompleteCallback = Callable[[CompanyRunResult, list[StoredJobEvent]], None]
CancellationCheck = Callable[[], bool]


class AnalysisBudgetExceeded(RuntimeError):
    """One run reached its configured maximum number of paid page analyses."""


class AnalysisBudget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def consume(self) -> None:
        if self.used >= self.limit:
            raise AnalysisBudgetExceeded(
                f"本次运行已达到 LLM 页面分析上限 {self.limit}，"
                "剩余变化页面留待下次扫描"
            )
        self.used += 1


def _analysis_context_hash(settings: Settings, company: CompanyConfig) -> str:
    """Invalidate cached model output when prompts/config/profile semantics change."""

    payload = {
        "company": company.name,
        "monitorMode": company.monitor_mode.value,
        "attributionKeywords": company.attribution_keywords,
        "provider": settings.llm.provider,
        "model": settings.llm.model,
        "renderMode": settings.crawler.render_mode,
        "entryWaitSelector": company.entry_wait_selector,
        "minStaticTextChars": settings.crawler.min_static_text_chars,
        "waitAfterLoadMs": settings.crawler.playwright_wait_after_load_ms,
        "maxLinks": settings.crawler.max_links_in_prompt,
        "candidate": settings.candidate.model_dump(mode="json"),
        "systemPromptHash": hashlib.sha256(
            SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "officialExtractorVersion": EXTRACTOR_VERSION,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _document_payload(document: PageDocument) -> dict[str, object]:
    return {
        "title": document.title,
        "text": document.text,
        "links": [link.model_dump(mode="json") for link in document.links],
        "emails": document.emails,
    }


def _document_from_cache(payload: dict[str, Any]) -> PageDocument:
    return PageDocument(
        title=str(payload.get("title") or ""),
        text=str(payload.get("text") or ""),
        links=[
            LinkCandidate.model_validate(item)
            for item in payload.get("links", [])
        ],
        emails=[str(item) for item in payload.get("emails", [])],
    )


def _document_content_hash(document: PageDocument) -> str:
    raw = json.dumps(_document_payload(document), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class MonitoringCancelled(RuntimeError):
    """调用方在流水线安全边界请求协作停止。"""


def _raise_if_cancelled(should_cancel: CancellationCheck | None) -> None:
    if should_cancel is not None and should_cancel():
        raise MonitoringCancelled("用户请求停止扫描")


def _safe_callback(callback: Callable[..., None] | None, *args: object) -> None:
    """Web 进度持久化失败不能中断核心扫描，但必须进入服务日志便于排查。"""

    if callback is None:
        return
    try:
        callback(*args)
    except Exception:
        LOGGER.exception("运行进度回调失败；核心扫描继续执行")


def _add_or_merge(jobs: list[JobPosting], candidate: JobPosting) -> None:
    """在单次运行内先合并重复岗位，防止列表摘要先触发一次“新增”。"""

    for index, existing in enumerate(jobs):
        if is_same_job(existing, candidate, allow_missing_location=True):
            jobs[index] = merge_job_postings(existing, candidate, text_strategy="richer")
            return
    jobs.append(candidate)


def _homepage_discovery_enabled(company: CompanyConfig) -> bool:
    """auto 仅把根路径或常见首页文件视为官网首页。"""

    if isinstance(company.discover_from_homepage, bool):
        return company.discover_from_homepage
    path = urlsplit(company.url).path.rstrip("/").casefold()
    return path in {"", "/index", "/index.html", "/home"}


def _sitemap_discovery_enabled(company: CompanyConfig) -> bool:
    if isinstance(company.discover_from_sitemap, bool):
        return company.discover_from_sitemap
    return _homepage_discovery_enabled(company) or company.monitor_mode in {
        MonitorMode.NOTICES,
        MonitorMode.BOTH,
    }


def _page_matches_company_scope(company: CompanyConfig, page_text: str) -> bool:
    """集团招聘页只有明确出现子公司归属词时才能产出该公司的岗位。"""

    if company.recruitment_channel.value != "group_recruitment":
        return True
    normalized_text = re.sub(r"\s+", "", page_text).casefold()
    return any(
        re.sub(r"\s+", "", keyword).casefold() in normalized_text
        for keyword in company.attribution_keywords
        if keyword.strip()
    )


def _job_matches_company_scope(company: CompanyConfig, job: JobPosting) -> bool:
    """集团平台中的每条记录也必须保留子公司归属，不能只靠页面导航命中。"""

    if company.recruitment_channel.value != "group_recruitment":
        return True
    job_text = "\n".join(
        value
        for value in (
            job.title,
            job.description,
            job.requirements,
            job.application_method,
        )
        if value
    )
    normalized_text = re.sub(r"\s+", "", job_text).casefold()
    return any(
        re.sub(r"\s+", "", keyword).casefold() in normalized_text
        for keyword in company.attribution_keywords
        if keyword.strip()
    )


class CompanyMonitor:
    """对一家公司的公开页面执行有边界的广度优先遍历。"""

    def __init__(
        self,
        settings: Settings,
        fetcher: PageFetcher,
        analyzer: PageAnalyzer,
        storage: JobStorage | None = None,
        analysis_budget: AnalysisBudget | None = None,
    ) -> None:
        self.settings = settings
        self.fetcher = fetcher
        self.analyzer = analyzer
        self.storage = storage
        self.analysis_budget = analysis_budget

    def crawl(
        self,
        company: CompanyConfig,
        on_page_progress: PageProgressCallback | None = None,
        should_cancel: CancellationCheck | None = None,
    ) -> CompanyRunResult:
        start_url = canonicalize_crawl_url(company.url)
        queue: deque[str] = deque([start_url])
        queued = {start_url}
        visited: set[str] = set()
        query_variants: dict[str, set[str]] = {crawl_path_key(start_url): {start_url}}
        trusted_hosts = {urlsplit(start_url).hostname or ""}
        jobs: list[JobPosting] = []
        errors: list[str] = []
        attempts = 0
        discovery_enabled = _homepage_discovery_enabled(company)
        context_hash = _analysis_context_hash(self.settings, company)

        # 大型央国企招聘站的栏目很多，允许为单家公司设置更保守的页数上限；
        # 未配置时继续使用全局值，保持旧配置行为不变。
        page_limit = company.max_pages or self.settings.crawler.max_pages_per_company
        if page_limit > 1 and _sitemap_discovery_enabled(company):
            sitemap_fetch = getattr(self.fetcher, "fetch_sitemap", None)
            if callable(sitemap_fetch):
                robots = getattr(self.fetcher, "robots", None)
                hints = robots.sitemaps_for(start_url) if robots is not None else ()
                for discovered in discover_recruitment_urls(
                    start_url,
                    self.fetcher,
                    sitemap_hints=hints,
                    should_cancel=should_cancel,
                ):
                    variants = query_variants.setdefault(crawl_path_key(discovered), set())
                    if (
                        discovered not in variants
                        and len(variants) >= self.settings.crawler.max_query_variants_per_path
                    ):
                        continue
                    variants.add(discovered)
                    if discovered not in queued:
                        queue.append(discovered)
                        queued.add(discovered)
        while queue and attempts < page_limit:
            _raise_if_cancelled(should_cancel)
            requested_url = queue.popleft()
            attempts += 1
            _safe_callback(
                on_page_progress,
                company.name,
                {
                    "phase": "started",
                    "requestedUrl": requested_url,
                    "currentPage": requested_url,
                    "pagesVisited": len(visited),
                    "queuedPages": len(queue),
                },
            )
            try:
                cache_key = canonicalize_url(requested_url)
                cached = (
                    self.storage.get_page_analysis_cache(company.name, cache_key)
                    if self.storage is not None
                    else None
                )
                cache_valid = bool(
                    cached and cached.get("context_hash") == context_hash
                )
                conditional_headers: dict[str, str] = {}
                if cache_valid and cached:
                    if cached.get("etag"):
                        conditional_headers["If-None-Match"] = str(cached["etag"])
                    if cached.get("last_modified"):
                        conditional_headers["If-Modified-Since"] = str(
                            cached["last_modified"]
                        )
                entry_selector = (
                    company.entry_wait_selector if requested_url == start_url else None
                )
                if entry_selector:
                    page = self.fetcher.fetch(
                        requested_url,
                        conditional_headers or None,
                        wait_selector=entry_selector,
                    )
                else:
                    page = (
                        self.fetcher.fetch(requested_url, conditional_headers)
                        if conditional_headers
                        else self.fetcher.fetch(requested_url)
                    )
                _raise_if_cancelled(should_cancel)
                final_url = canonicalize_url(page.final_url)
                final_host = urlsplit(final_url).hostname or ""
                if final_host:
                    trusted_hosts.add(final_host)
                if final_url in visited:
                    continue
                visited.add(final_url)
                # ``final_url`` 用作去重键可以去掉尾斜杠；解析相对链接时必须使用
                # 服务端真实目录 URL，否则 ``./202607/article.htm`` 会错误地少一层路径。
                cache_status = "miss"
                direct_complete = False
                direct_follow_urls: list[str] = []
                if page.not_modified:
                    if not cache_valid or cached is None:
                        raise RuntimeError("页面返回 304，但没有可复用的分析缓存")
                    document_payload = json.loads(str(cached["document_json"]))
                    document = _document_from_cache(document_payload)
                    direct_complete = bool(document_payload.get("direct_complete"))
                    direct_follow_urls = list(document_payload.get("direct_follow_urls") or [])
                    analysis = PageAnalysis.model_validate_json(
                        str(cached["analysis_json"])
                    )
                    content_hash = str(cached["content_hash"])
                    cache_status = "not_modified"
                else:
                    document = parse_html(
                        page.html,
                        normalize_request_url(page.final_url),
                    )
                    content_hash = _document_content_hash(document)
                    direct_extraction = extract_official_jobs(
                        final_url, page.html, company.name
                    )
                    if (
                        cache_valid
                        and cached is not None
                        and cached.get("content_hash") == content_hash
                    ):
                        analysis = PageAnalysis.model_validate_json(
                            str(cached["analysis_json"])
                        )
                        direct_complete = bool(
                            json.loads(str(cached["document_json"])).get("direct_complete")
                        )
                        direct_follow_urls = list(
                            json.loads(str(cached["document_json"])).get("direct_follow_urls") or []
                        )
                        cache_status = "content_unchanged"
                    elif direct_extraction is not None:
                        analysis = PageAnalysis(
                            page_type=direct_extraction.page_type,
                            contains_recruitment_info=True,
                            jobs=direct_extraction.jobs,
                        )
                        direct_complete = direct_extraction.list_complete
                        direct_follow_urls = direct_extraction.follow_urls
                        cache_status = "direct"
                    else:
                        _raise_if_cancelled(should_cancel)
                        if self.analysis_budget is not None:
                            self.analysis_budget.consume()
                        analysis = self.analyzer.analyze_page(
                            company.name,
                            final_url,
                            document,
                            self.settings.crawler.max_links_in_prompt,
                            monitor_mode=company.monitor_mode.value,
                        )
                        cache_status = "analyzed"
                _raise_if_cancelled(should_cancel)
                LOGGER.info(
                    "公司=%s 页面=%s 类型=%s 岗位=%s 渲染=%s",
                    company.name,
                    final_url,
                    analysis.page_type,
                    len(analysis.jobs),
                    page.rendered,
                )
                page_in_scope = _page_matches_company_scope(company, document.text)
                if analysis.jobs and not page_in_scope:
                    LOGGER.info(
                        "集团招聘页面未命中 %s 的归属词，忽略本页 %s 条记录：%s",
                        company.name,
                        len(analysis.jobs),
                        final_url,
                    )
                accepted_jobs = [
                    job
                    for job in analysis.jobs
                    if page_in_scope and _job_matches_company_scope(company, job)
                ]
                if page_in_scope and len(accepted_jobs) != len(analysis.jobs):
                    LOGGER.info(
                        "集团招聘页有 %s 条记录未在岗位正文命中 %s 归属词，已忽略",
                        len(analysis.jobs) - len(accepted_jobs),
                        company.name,
                    )
                if page_in_scope:
                    for job in accepted_jobs:
                        _add_or_merge(jobs, job)

                fetched_at = datetime.now(
                    ZoneInfo(self.settings.app.timezone)
                ).isoformat(timespec="seconds")
                if self.storage is not None:
                    self.storage.save_page_analysis_cache(
                        company_name=company.name,
                        url=cache_key,
                        context_hash=context_hash,
                        content_hash=content_hash,
                        etag=page.etag or (str(cached["etag"]) if cached and cached.get("etag") else None),
                        last_modified=page.last_modified
                        or (
                            str(cached["last_modified"])
                            if cached and cached.get("last_modified")
                            else None
                        ),
                        document={
                            **_document_payload(document),
                            "direct_complete": direct_complete,
                            "direct_follow_urls": direct_follow_urls,
                        },
                        analysis=analysis.model_dump(mode="json"),
                        updated_at=fetched_at,
                    )
                _safe_callback(
                    on_page_progress,
                    company.name,
                    {
                        "phase": "completed",
                        "requestedUrl": requested_url,
                        "finalUrl": final_url,
                        "currentPage": final_url,
                        "pagesVisited": len(visited),
                        "queuedPages": len(queue),
                        "pageType": analysis.page_type,
                        "method": "playwright" if page.rendered else "requests",
                        "httpStatus": page.status_code,
                        "contentLength": len(document.text),
                        "llmExtracted": cache_status == "analyzed",
                        "cacheStatus": cache_status,
                        "jobsFound": len(accepted_jobs),
                        "status": "success",
                        "fetchedAt": fetched_at,
                    },
                )

                candidates_by_url = {
                    canonicalize_url(link.url): link for link in document.links
                }
                follow_urls = list(direct_follow_urls)
                for follow in ([] if direct_complete else analysis.follow_links):
                    candidate = candidates_by_url.get(canonicalize_url(follow.url))
                    if candidate is None or is_irrelevant_link(candidate.url, candidate.text):
                        continue
                    if follow.kind == "job_detail" and candidate.job_score < 4:
                        evidence = f"{candidate.text} {candidate.url}".casefold()
                        dated_recruitment = candidate.career_score >= 3 and any(
                            term in evidence
                            for term in (
                                "2025",
                                "2026",
                                "2027",
                                "campus",
                                "graduate",
                                "招聘岗位",
                                "招聘职位",
                            )
                        )
                        if not dated_recruitment:
                            LOGGER.debug(
                                "LLM 详情链接缺少职位锚点证据，跳过：%s", follow.url
                            )
                            continue
                    if follow.kind in {"career_section", "job_list"} and max(
                        candidate.career_score, candidate.job_score
                    ) < 3:
                        LOGGER.debug("LLM 招聘入口缺少页面锚点证据，跳过：%s", follow.url)
                        continue
                    follow_urls.append(follow.url)
                # 官网首页仅在启用发现时展开；配置成 /jobs、/careers 等明确招聘入口
                # 时，即使 auto 没有开启首页发现，也应跟进页面上可见的岗位详情。
                start_path = urlsplit(company.url).path.rstrip("/").casefold()
                explicit_entry = start_path not in {"", "/index", "/index.html", "/home"}
                allow_heuristic = (
                    not direct_complete
                    and (
                        final_url != canonicalize_url(company.url)
                        or discovery_enabled
                        or (
                            explicit_entry
                            and analysis.page_type in {"career_home", "job_list", "mixed"}
                        )
                    )
                )
                if allow_heuristic:
                    follow_urls.extend(
                        heuristic_follow_links(
                            document,
                            analysis.page_type,
                            self.settings.crawler.max_follow_links_per_page,
                        )
                    )
                for next_url in follow_urls[: self.settings.crawler.max_follow_links_per_page]:
                    canonical = canonicalize_crawl_url(next_url)
                    next_host = urlsplit(canonical).hostname or ""
                    if next_host not in trusted_hosts:
                        candidate = next(
                            (item for item in document.links if canonicalize_crawl_url(item.url) == canonical),
                            None,
                        )
                        # 官网首页可能把招聘托管到独立 ATS 域名；仅允许页面真实存在且
                        # 招聘得分高的少量外部入口，禁止后续页面继续跨站扩散。
                        if (
                            final_url != canonicalize_url(company.url)
                            or candidate is None
                            or max(candidate.career_score, candidate.job_score) < 6
                            or len(trusted_hosts) >= 3
                        ):
                            LOGGER.debug("跳过非可信外部站点链接：%s", canonical)
                            continue
                        trusted_hosts.add(next_host)

                    query = parse_qsl(urlsplit(canonical).query, keep_blank_values=False)
                    has_identity = any(
                        key.casefold()
                        in {
                            "id",
                            "jobid",
                            "job_id",
                            "positionid",
                            "position_id",
                            "requisitionid",
                            "requisition_id",
                        }
                        and value.strip()
                        for key, value in query
                    )
                    path_key = crawl_path_key(canonical)
                    variants = query_variants.setdefault(path_key, set())
                    if (
                        not has_identity
                        and canonical not in variants
                        and len(variants) >= self.settings.crawler.max_query_variants_per_path
                    ):
                        LOGGER.debug("同路径查询参数变体达到上限，跳过：%s", canonical)
                        continue
                    variants.add(canonical)
                    if canonical not in visited and canonical not in queued:
                        queue.append(canonical)
                        queued.add(canonical)
            except MonitoringCancelled:
                raise
            except Exception as exc:
                message = f"{company.name}｜{requested_url}｜{type(exc).__name__}: {exc}"
                LOGGER.error(message)
                errors.append(message)
                _safe_callback(
                    on_page_progress,
                    company.name,
                    {
                        "phase": "failed",
                        "requestedUrl": requested_url,
                        "finalUrl": requested_url,
                        "currentPage": requested_url,
                        "pagesVisited": len(visited),
                        "queuedPages": len(queue),
                        "pageType": None,
                        "method": "requests",
                        "httpStatus": None,
                        "contentLength": 0,
                        "llmExtracted": False,
                        "jobsFound": 0,
                        "status": "failed",
                        "error": message,
                        "fetchedAt": datetime.now(
                            ZoneInfo(self.settings.app.timezone)
                        ).isoformat(timespec="seconds"),
                    },
                )

        if queue:
            # 页面上限是主动的容量边界，尤其政府公告栏目可能保留多年历史。
            # 到达上限不代表抓取失败，不应让一次全成功的有界扫描显示为“部分失败”。
            LOGGER.info(
                "%s 达到页面上限 max_pages=%s，本轮按配置停止，队列剩余 %s 页",
                company.name,
                page_limit,
                len(queue),
            )
        return CompanyRunResult(
            company=company.name,
            pages_visited=len(visited),
            jobs=jobs,
            errors=errors,
        )

    def fetch_ats(
        self,
        company: CompanyConfig,
        on_page_progress: PageProgressCallback | None = None,
        should_cancel: CancellationCheck | None = None,
    ) -> CompanyRunResult:
        """通过公司配置的 ATS 公开接口直接拉取岗位，不做 HTML 遍历。"""

        source = company.ats_source
        if source is None:
            raise ValueError("fetch_ats 需要 company.ats_source")
        display = f"{source.type.value}://{source.tenant or 'json_feed'}"
        result = CompanyRunResult(company=company.name)
        now_text = datetime.now(ZoneInfo(self.settings.app.timezone)).isoformat(
            timespec="seconds"
        )
        _safe_callback(
            on_page_progress,
            company.name,
            {
                "phase": "started",
                "requestedUrl": display,
                "currentPage": display,
                "pagesVisited": 0,
                "queuedPages": 0,
            },
        )
        try:
            def before_request(url: str) -> None:
                _raise_if_cancelled(should_cancel)
                self.fetcher.robots.ensure_allowed(url)
                self.fetcher.limiter.wait(url)

            ats_jobs = fetch_ats_jobs(source, before_request=before_request)
        except (ATSSourceError, CrawlError) as exc:
            message = f"{company.name}｜ATS 接口失败｜{exc}"
            LOGGER.error(message)
            result.errors.append(message)
            _safe_callback(
                on_page_progress,
                company.name,
                {
                    "phase": "failed",
                    "requestedUrl": display,
                    "currentPage": display,
                    "pagesVisited": 0,
                    "queuedPages": 0,
                    "fetchedAt": now_text,
                    "method": "ats_api",
                    "error": message,
                },
            )
            return result

        _raise_if_cancelled(should_cancel)
        result.pages_visited = 1
        postings = ats_jobs_to_postings(ats_jobs, company)
        if source.evaluate_with_llm:
            postings = self._evaluate_ats_jobs(company, postings, should_cancel)
        result.jobs = postings
        LOGGER.info("公司=%s ATS=%s 岗位=%s", company.name, source.type.value, len(postings))
        _safe_callback(
            on_page_progress,
            company.name,
            {
                "phase": "completed",
                "requestedUrl": display,
                "currentPage": display,
                "pagesVisited": 1,
                "queuedPages": 0,
                "fetchedAt": now_text,
                "method": "ats_api",
                "pageType": "ats_api",
                "httpStatus": 200,
                "contentLength": 0,
                "llmExtracted": bool(source.evaluate_with_llm),
                "jobsFound": len(postings),
            },
        )
        return result

    def _evaluate_ats_jobs(
        self,
        company: CompanyConfig,
        jobs: list[JobPosting],
        should_cancel: CancellationCheck | None = None,
    ) -> list[JobPosting]:
        """对 ATS 岗位跑一次 LLM 评估，让届别/能力匹配与通知链路保持不变。"""

        evaluated: list[JobPosting] = []
        budget_exhausted = False
        for job in jobs:
            _raise_if_cancelled(should_cancel)
            if budget_exhausted:
                evaluated.append(job)
                continue
            document = PageDocument(
                title=job.title,
                text=f"{job.title}\n\n{job.description}".strip(),
                links=[],
            )
            try:
                if self.analysis_budget is not None:
                    self.analysis_budget.consume()
                analysis = self.analyzer.analyze_page(
                    company.name,
                    job.source_url or company.url,
                    document,
                    link_limit=0,
                    monitor_mode=company.monitor_mode.value,
                )
            except AnalysisBudgetExceeded:
                budget_exhausted = True
                LOGGER.warning(
                    "ATS 岗位评估达到单次运行上限，其余岗位保留未评估：%s",
                    company.name,
                )
                evaluated.append(job)
                continue
            except Exception as exc:
                LOGGER.error("ATS 岗位评估失败（保留原始字段）：%s｜%s", company.name, exc)
                evaluated.append(job)
                continue
            if analysis.jobs:
                matched = analysis.jobs[0]
                job = job.model_copy(
                    update={
                        "match_level": matched.match_level,
                        "match_reason": matched.match_reason,
                        "profile_fit_level": matched.profile_fit_level,
                        "profile_fit_reason": matched.profile_fit_reason,
                        "difficulty_level": matched.difficulty_level,
                        "difficulty_score": matched.difficulty_score,
                        "difficulty_reason": matched.difficulty_reason,
                    }
                )
            evaluated.append(job)
        return evaluated


class MonitorService:
    """应用服务入口，负责跨公司隔离错误并生成最终统计。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(
        self,
        *,
        company_names: set[str] | None = None,
        dry_run: bool = False,
        disable_email: bool = False,
        on_company_start: CompanyStartCallback | None = None,
        on_page_progress: PageProgressCallback | None = None,
        on_company_complete: CompanyCompleteCallback | None = None,
        should_cancel: CancellationCheck | None = None,
    ) -> RunResult:
        timezone = ZoneInfo(self.settings.app.timezone)
        started = datetime.now(timezone)
        selected = [
            company
            for company in self.settings.companies
            if company.enabled and (not company_names or company.name in company_names)
        ]
        if not selected:
            raise ValueError("没有启用且符合筛选条件的公司，请检查 companies[].enabled/--company")

        _raise_if_cancelled(should_cancel)
        provider = create_provider(self.settings.llm)
        analyzer = PageAnalyzer(self.settings.llm, provider, self.settings.candidate)
        company_results: list[CompanyRunResult] = []
        events: list[StoredJobEvent] = []
        storage: JobStorage | None = None
        if not dry_run:
            storage = JobStorage(
                self.settings.app.database_path,
                semantic_duplicate_window_days=(
                    self.settings.app.semantic_duplicate_window_days
                ),
            )
            storage.initialize()
        analysis_budget = AnalysisBudget(
            self.settings.crawler.max_llm_pages_per_run
        )
        with PageFetcher(self.settings.crawler) as fetcher:
            monitor = CompanyMonitor(
                self.settings,
                fetcher,
                analyzer,
                storage,
                analysis_budget,
            )
            for company in selected:
                _raise_if_cancelled(should_cancel)
                LOGGER.info("开始监控公司：%s (%s)", company.name, company.url)
                _safe_callback(on_company_start, company)
                try:
                    if company.ats_source is not None and company.ats_source.enabled:
                        company_result = monitor.fetch_ats(
                            company,
                            on_page_progress,
                            should_cancel,
                        )
                    else:
                        company_result = monitor.crawl(
                            company,
                            on_page_progress,
                            should_cancel,
                        )
                except MonitoringCancelled:
                    raise
                except Exception as exc:
                    # 公司级兜底保证一家站点的未知异常不会中止其他公司。
                    message = f"{company.name}｜公司级异常｜{type(exc).__name__}: {exc}"
                    LOGGER.exception(message)
                    company_result = CompanyRunResult(company=company.name, errors=[message])

                detected_at = datetime.now(timezone).isoformat(timespec="seconds")
                try:
                    if dry_run:
                        company_events = []
                        for job in company_result.jobs:
                            entity_key, fingerprint, _prefix, _content = compute_job_hashes(job)
                            company_events.append(
                                StoredJobEvent(
                                    event_type="preview",
                                    job=job,
                                    entity_key=entity_key,
                                    fingerprint=fingerprint,
                                    detected_at=detected_at,
                                )
                            )
                    else:
                        assert storage is not None
                        # 关键保证：每家公司结束立即独立事务入库，后续公司失败不会
                        # 回滚或隐藏已经完成公司的岗位。
                        company_events = storage.store_jobs(company_result.jobs, detected_at)
                except Exception as exc:
                    message = f"{company.name}｜岗位入库失败｜{type(exc).__name__}: {exc}"
                    LOGGER.exception(message)
                    company_result.errors.append(message)
                    company_events = []
                company_results.append(company_result)
                events.extend(company_events)
                _safe_callback(on_company_complete, company_result, company_events)
                _raise_if_cancelled(should_cancel)

        all_jobs = [job for result in company_results for job in result.jobs]
        errors = [error for result in company_results for error in result.errors]

        changed = [event for event in events if event.event_type in {"new", "updated", "preview"}]
        output_levels = set(self.settings.app.output_match_levels)
        output_events = [event for event in changed if event.job.match_level in output_levels]
        if not self.settings.app.include_updates_in_output:
            output_events = [event for event in output_events if event.event_type != "updated"]

        report_path: Path | None = None
        csv_path: Path | None = None
        email_sent = False
        apprise_sent = False
        if not dry_run:
            _raise_if_cancelled(should_cancel)
            report_now = datetime.now(timezone)
            writer = ReportWriter(self.settings.app.output_dir)
            report_path, csv_path = writer.write_daily(
                output_events,
                errors,
                report_now,
                write_empty=self.settings.app.write_empty_report,
            )
            try:
                removed_reports = prune_expired_reports(
                    self.settings.app.output_dir,
                    self.settings.app.report_retention_days,
                    today=report_now.date(),
                )
                if removed_reports:
                    LOGGER.info("已自动清理 %s 个过期日报文件", removed_reports)
            except OSError as exc:
                message = f"历史日报自动清理失败｜{type(exc).__name__}: {exc}"
                LOGGER.error(message)
                errors.append(message)
            _raise_if_cancelled(should_cancel)
            email_events = notification_events(self.settings, changed)
            if self.settings.smtp.enabled and not disable_email and email_events:
                _raise_if_cancelled(should_cancel)
                try:
                    send_job_email(
                        self.settings.smtp,
                        email_events,
                        datetime.now(timezone).strftime("%Y-%m-%d"),
                    )
                    email_sent = True
                except MailError as exc:
                    LOGGER.error("邮件发送失败：%s", exc)
                    errors.append(str(exc))
            if self.settings.apprise.enabled and not disable_email and email_events:
                _raise_if_cancelled(should_cancel)
                try:
                    send_job_notifications(
                        self.settings.apprise,
                        email_events,
                        datetime.now(timezone).strftime("%Y-%m-%d"),
                    )
                    apprise_sent = True
                except NotificationError as exc:
                    LOGGER.error("Apprise 推送失败：%s", exc)
                    errors.append(str(exc))

        finished = datetime.now(timezone)
        return RunResult(
            started_at=started.isoformat(timespec="seconds"),
            finished_at=finished.isoformat(timespec="seconds"),
            companies_processed=len(company_results),
            pages_visited=sum(result.pages_visited for result in company_results),
            jobs_seen=len(all_jobs),
            new_jobs=sum(event.event_type == "new" for event in events),
            updated_jobs=sum(event.event_type == "updated" for event in events),
            unchanged_jobs=sum(event.event_type == "unchanged" for event in events),
            report_path=str(report_path) if report_path else None,
            csv_path=str(csv_path) if csv_path else None,
            email_sent=email_sent,
            apprise_sent=apprise_sent,
            errors=errors,
        )
