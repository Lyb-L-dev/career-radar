"""微信公众号招聘文章的只读搜索、账号核验、去重与通知导入。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import yaml

from .models import JobPosting, WechatRecruitmentConfig
from .reputation import Runner, _default_runner
from .storage import JobStorage
from .web_repository import WebRepository

LOGGER = logging.getLogger(__name__)

_WECHAT_HOSTS = {"mp.weixin.qq.com"}
_POSITIVE_TERMS = (
    "招聘",
    "校园招聘",
    "校招",
    "社会招聘",
    "社招",
    "实习生",
    "实习招聘",
    "招贤纳士",
    "人才招聘",
    "岗位",
    "管培生",
)
_OPPORTUNITY_TERMS = (
    "报名",
    "投递",
    "简历",
    "岗位职责",
    "任职资格",
    "招聘岗位",
    "截止时间",
    "申请方式",
)
_RESULT_ONLY_TERMS = (
    "拟录用",
    "录用公示",
    "成绩公示",
    "面试名单",
    "资格审查结果",
    "体检名单",
    "递补名单",
)


class WechatRecruitmentError(RuntimeError):
    """OpenCLI 缺失、浏览器不可用、搜索失败或文章结构不可信。"""


def _safe_text(value: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _public_error(value: object, limit: int = 600) -> str:
    """保留诊断摘要，但移除用户目录和临时目录等本机路径。"""

    text = _safe_text(value, limit * 2)
    for root in {str(Path.home()), tempfile.gettempdir()}:
        if root:
            text = re.sub(
                re.escape(root),
                "[本机路径]",
                text,
                flags=re.IGNORECASE,
            )
    return text[:limit]


def _identity_key(value: object) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").casefold())


def _wechat_url(value: object) -> str | None:
    url = str(value or "").strip()
    parts = urlsplit(url)
    if (
        parts.scheme.casefold() not in {"http", "https"}
        or not parts.hostname
        or parts.hostname.casefold() not in _WECHAT_HOSTS
    ):
        return None
    return url


def _biz_id(url: str) -> str | None:
    value = parse_qs(urlsplit(url).query).get("__biz", [None])[0]
    return _safe_text(value, 200) or None


def _field_rows(value: object) -> dict[str, Any] | None:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        return None
    rows = [row for row in value if "field" in row and "value" in row]
    return {str(row["field"]): row.get("value") for row in rows} if rows else None


def _unwrap_payload(value: object) -> object:
    current = value
    for _ in range(3):
        field_map = _field_rows(current)
        if field_map is not None:
            return field_map
        if not isinstance(current, dict):
            break
        nested = next(
            (
                current[key]
                for key in ("data", "result", "output")
                if key in current and current[key] is not current
            ),
            None,
        )
        if nested is None:
            break
        current = nested
    return current


def _markdown_metadata(content: str) -> dict[str, str]:
    """从 OpenCLI 生成的 Markdown 头部保守提取公开账号元数据。"""

    metadata: dict[str, str] = {}
    for line in content.splitlines()[:40]:
        match = re.match(
            r"^\s*(?:[-*>]\s*)?(公众号|微信号|作者|发布时间|发布日期)\s*[：:]\s*(.+?)\s*$",
            line,
        )
        if match:
            metadata[match.group(1)] = match.group(2).strip()
    return metadata


class WechatOpenCLIConnector:
    """OpenCLI 微信搜索/下载的固定白名单适配器。"""

    def __init__(
        self,
        config: WechatRecruitmentConfig,
        *,
        runner: Runner = _default_runner,
    ) -> None:
        self.config = config
        self.runner = runner
        self.command = self._resolve_command(config.opencli_command)

    @staticmethod
    def _resolve_command(raw_command: str) -> list[str]:
        expanded = os.path.expandvars(os.path.expanduser(raw_command.strip()))
        path = Path(expanded)
        if not path.is_file():
            located = shutil.which(expanded)
            if located:
                path = Path(located)
            else:
                fallback = (
                    Path.home()
                    / ".agent-reach"
                    / "node-global"
                    / ("opencli.cmd" if os.name == "nt" else "opencli")
                )
                if not fallback.is_file():
                    raise WechatRecruitmentError(
                        "找不到 OpenCLI，请检查 wechat_recruitment.opencli_command"
                    )
                path = fallback
        if path.suffix.casefold() in {".cmd", ".ps1"}:
            entry = (
                path.parent
                / "node_modules"
                / "@jackwener"
                / "opencli"
                / "dist"
                / "src"
                / "main.js"
            )
            node = shutil.which("node")
            if entry.is_file() and node:
                return [node, str(entry)]
        return [str(path)]

    def _run(
        self,
        arguments: list[str],
        *,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        completed = self.runner(
            [*self.command, *arguments],
            timeout or self.config.command_timeout_seconds,
        )
        if completed.returncode != 0:
            message = _public_error(
                f"{completed.stdout}\n{completed.stderr}",
                600,
            )
            raise WechatRecruitmentError(
                message or f"OpenCLI 退出码 {completed.returncode}"
            )
        return completed

    def _json_call(self, arguments: list[str]) -> object:
        completed = self._run([*arguments, "-f", "json"])
        stdout = completed.stdout.strip().lstrip("\ufeff")
        if not stdout:
            return []
        try:
            return _unwrap_payload(json.loads(stdout))
        except json.JSONDecodeError:
            try:
                return _unwrap_payload(yaml.safe_load(stdout))
            except yaml.YAMLError as exc:
                raise WechatRecruitmentError("OpenCLI 返回了无法解析的数据") from exc

    def health(self) -> dict[str, Any]:
        if not self.config.enabled:
            return {
                "enabled": False,
                "available": False,
                "message": "微信公众号招聘搜索未启用",
            }
        try:
            self._run(
                ["weixin", "search", "--help"],
                timeout=min(20, self.config.command_timeout_seconds),
            )
            doctor = self._run(
                ["doctor"],
                timeout=min(20, self.config.command_timeout_seconds),
            )
        except WechatRecruitmentError as exc:
            LOGGER.warning("微信公众号招聘健康检查失败：%s", exc)
            return {
                "enabled": True,
                "available": False,
                "message": "OpenCLI 微信命令不可用，请检查本机安装与 Browser Bridge",
            }
        doctor_output = f"{doctor.stdout}\n{doctor.stderr}"
        if "Everything looks good" not in doctor_output:
            return {
                "enabled": True,
                "available": False,
                "message": "OpenCLI Browser Bridge 尚未连接",
            }
        return {
            "enabled": True,
            "available": True,
            "message": "OpenCLI 微信搜索命令与 Browser Bridge 均可用",
        }

    def search(self, query: str) -> list[dict[str, Any]]:
        clean_query = _safe_text(query, 200)
        if not clean_query:
            return []
        raw = self._json_call(
            [
                "weixin",
                "search",
                clean_query,
                "--page",
                "1",
                "--limit",
                str(self.config.results_per_query),
                "--window",
                "background",
                "--site-session",
                "ephemeral",
            ]
        )
        if isinstance(raw, dict):
            rows = raw.get("items") or raw.get("results") or []
        else:
            rows = raw
        if not isinstance(rows, list):
            raise WechatRecruitmentError("微信搜索结果不是列表")
        results = []
        for index, raw_item in enumerate(rows):
            field_map = _field_rows(raw_item)
            item = field_map or raw_item
            if not isinstance(item, dict):
                continue
            url = _wechat_url(item.get("url") or item.get("link"))
            if not url:
                continue
            results.append(
                {
                    "rank": int(item.get("rank") or index + 1),
                    "title": _safe_text(item.get("title"), 300),
                    "url": url,
                    "summary": _safe_text(
                        item.get("summary")
                        or item.get("snippet")
                        or item.get("description"),
                        1_000,
                    ),
                    "publishedAt": _safe_text(
                        item.get("publish_time")
                        or item.get("published_at")
                        or item.get("time"),
                        80,
                    )
                    or None,
                    "accountName": _safe_text(
                        item.get("account_name")
                        or item.get("wechat_name")
                        or item.get("source"),
                        200,
                    )
                    or None,
                    "accountIdentifier": _safe_text(
                        item.get("account_id") or item.get("wechat_id"),
                        200,
                    )
                    or None,
                }
            )
        return results

    def read_article(self, result: dict[str, Any]) -> dict[str, Any]:
        url = _wechat_url(result.get("url"))
        if not url:
            raise WechatRecruitmentError("微信公众号文章链接无效")
        with tempfile.TemporaryDirectory(prefix="career-radar-wechat-") as raw_dir:
            output_dir = Path(raw_dir).resolve()
            raw = self._json_call(
                [
                    "weixin",
                    "download",
                    "--url",
                    url,
                    "--output",
                    str(output_dir),
                    "--download-images",
                    "false",
                    "--window",
                    "background",
                    "--site-session",
                    "ephemeral",
                ]
            )
            row = raw
            if isinstance(raw, list) and raw and isinstance(raw[0], dict):
                row = raw[0]
            field_map = _field_rows(row)
            if field_map is not None:
                row = field_map
            metadata = row if isinstance(row, dict) else {}
            saved = str(metadata.get("saved") or metadata.get("path") or "").strip()
            candidates: list[Path] = []
            if saved:
                saved_path = Path(saved)
                if not saved_path.is_absolute():
                    saved_path = output_dir / saved_path
                candidates.append(saved_path.resolve())
            candidates.extend(path.resolve() for path in output_dir.rglob("*.md"))
            markdown_path = next(
                (
                    path
                    for path in candidates
                    if path.is_file()
                    and output_dir in path.parents
                    and path.suffix.casefold() == ".md"
                ),
                None,
            )
            if markdown_path is None:
                raise WechatRecruitmentError("OpenCLI 未生成公众号文章 Markdown")
            content = markdown_path.read_text(
                encoding="utf-8",
                errors="replace",
            ).strip()
        if not content:
            raise WechatRecruitmentError("公众号文章正文为空")
        content = content[: self.config.max_article_chars]
        markdown_meta = _markdown_metadata(content)
        return {
            "title": _safe_text(
                metadata.get("title") or result.get("title"),
                300,
            )
            or "未提供标题",
            "url": url,
            "summary": _safe_text(result.get("summary"), 1_000),
            "content": content,
            "publishedAt": _safe_text(
                metadata.get("publish_time")
                or markdown_meta.get("发布时间")
                or markdown_meta.get("发布日期")
                or result.get("publishedAt"),
                80,
            )
            or None,
            "accountName": _safe_text(
                metadata.get("account_name")
                or metadata.get("author")
                or markdown_meta.get("公众号"),
                200,
            )
            or None,
            "accountIdentifier": _safe_text(
                metadata.get("account_id")
                or markdown_meta.get("微信号"),
                200,
            )
            or None,
            "bizId": _biz_id(url),
        }


def _matches_account(
    article: dict[str, Any],
    account: dict[str, Any],
) -> bool:
    comparisons = (
        (article.get("accountName"), account.get("account_name")),
        (article.get("accountIdentifier"), account.get("account_identifier")),
        (article.get("bizId"), account.get("biz_id")),
    )
    return any(
        left
        and right
        and _identity_key(left) == _identity_key(right)
        for left, right in comparisons
    )


def classify_wechat_article(
    article: dict[str, Any],
    accounts: list[dict[str, Any]],
) -> tuple[str, str, dict[str, Any] | None]:
    """仅强账号身份命中且正文满足范围时认定为官方招聘。"""

    text = f"{article.get('title') or ''}\n{article.get('content') or ''}"
    has_positive = any(term in text for term in _POSITIVE_TERMS)
    result_only = any(term in text for term in _RESULT_ONLY_TERMS)
    has_opportunity = any(term in text for term in _OPPORTUNITY_TERMS)
    if not has_positive or (result_only and not has_opportunity):
        return "non_recruitment", "正文未呈现可投递招聘机会", None

    matched = next(
        (account for account in accounts if _matches_account(article, account)),
        None,
    )
    if matched is None:
        return (
            "third_party_lead",
            "文章账号身份未命中已登记公众号，只保存为待核验线索",
            None,
        )
    if matched["verification_status"] != "verified":
        return (
            "third_party_lead",
            "公众号尚未由人工核验，只保存为待核验线索",
            matched,
        )
    if matched["scope"] == "group":
        compact = _identity_key(text)
        keywords = matched.get("attribution_keywords") or []
        if not any(_identity_key(keyword) in compact for keyword in keywords):
            return (
                "third_party_lead",
                "集团公众号文章未明确命中目标子公司归属词",
                matched,
            )
    return "official_recruitment", "账号身份与招聘正文均通过核验", matched


class WechatRecruitmentManager:
    """串行运行公众号扫描；搜索和分类全程不调用 LLM。"""

    def __init__(
        self,
        repository: WebRepository,
        *,
        connector_factory: Any = WechatOpenCLIConnector,
    ) -> None:
        self.repository = repository
        self.connector_factory = connector_factory
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="wechat-recruitment",
        )
        self._lock = threading.Lock()
        self._active: Future[None] | None = None
        self.repository.recover_interrupted_wechat_scans()

    def health(self) -> dict[str, Any]:
        try:
            connector = self.connector_factory(
                self.repository.settings.wechat_recruitment
            )
            return connector.health()
        except (WechatRecruitmentError, OSError) as exc:
            LOGGER.warning("微信公众号招聘连接器初始化失败：%s", exc)
            return {
                "enabled": self.repository.settings.wechat_recruitment.enabled,
                "available": False,
                "message": "OpenCLI 微信命令不可用，请检查本机安装与 Browser Bridge",
            }

    def start(
        self,
        *,
        candidate_id: str,
        company_name: str,
    ) -> dict[str, Any]:
        if not self.repository.settings.wechat_recruitment.enabled:
            raise ValueError("微信公众号招聘扫描未启用")
        accounts = [
            item
            for item in self.repository.list_wechat_accounts(candidate_id)
            if item["enabled"]
        ]
        if not accounts:
            raise ValueError("请先登记并启用至少一个企业招聘公众号")
        with self._lock:
            if self._active is not None and not self._active.done():
                raise RuntimeError("已有微信公众号招聘扫描正在运行")
            now = self._now()
            payload = {
                "id": f"wechat-scan-{uuid.uuid4().hex}",
                "candidateId": candidate_id,
                "companyName": company_name,
                "status": "pending",
                "startedAt": now,
                "updatedAt": now,
                "finishedAt": None,
                "accounts": [
                    {
                        "id": item["account_id"],
                        "name": item["account_name"],
                        "verificationStatus": item["verification_status"],
                    }
                    for item in accounts
                ],
                "queries": [],
                "articles": [],
                "stats": {
                    "searched": 0,
                    "read": 0,
                    "official": 0,
                    "leads": 0,
                    "ignored": 0,
                    "imported": 0,
                    "new": 0,
                    "updated": 0,
                    "unchanged": 0,
                },
                "errors": [],
            }
            self.repository.save_wechat_scan(payload)
            self._active = self._executor.submit(
                self._run,
                payload["id"],
                candidate_id,
                company_name,
                accounts,
            )
            return payload

    def _now(self) -> str:
        return datetime.now(
            ZoneInfo(self.repository.settings.app.timezone)
        ).isoformat(timespec="seconds")

    def _save(self, payload: dict[str, Any]) -> None:
        payload["updatedAt"] = self._now()
        self.repository.save_wechat_scan(payload)

    def _run(
        self,
        scan_id: str,
        candidate_id: str,
        company_name: str,
        accounts: list[dict[str, Any]],
    ) -> None:
        payload = self.repository.get_wechat_scan(scan_id)
        if payload is None:  # pragma: no cover
            return
        payload["status"] = "running"
        self._save(payload)
        try:
            connector = self.connector_factory(
                self.repository.settings.wechat_recruitment
            )
            health = connector.health()
            if not health.get("available"):
                raise WechatRecruitmentError(
                    str(health.get("message") or "OpenCLI 微信命令不可用")
                )
            self._execute_scan(
                payload,
                connector,
                candidate_id,
                company_name,
                accounts,
            )
            payload["status"] = "partial" if payload["errors"] else "completed"
        except Exception as exc:
            LOGGER.exception("微信公众号招聘扫描失败")
            payload["errors"].append(_public_error(exc))
            payload["status"] = (
                "partial" if payload["stats"]["read"] else "failed"
            )
        finally:
            payload["finishedAt"] = self._now()
            self._save(payload)

    def _execute_scan(
        self,
        payload: dict[str, Any],
        connector: WechatOpenCLIConnector,
        candidate_id: str,
        company_name: str,
        accounts: list[dict[str, Any]],
    ) -> None:
        config = self.repository.settings.wechat_recruitment
        search_results: dict[str, dict[str, Any]] = {}
        for account in accounts:
            for term in config.search_terms:
                query = _safe_text(
                    f"{account['account_name']} {company_name} {term}",
                    200,
                )
                payload["queries"].append(query)
                try:
                    rows = connector.search(query)
                except (WechatRecruitmentError, subprocess.SubprocessError) as exc:
                    payload["errors"].append(f"{query}：{_public_error(exc, 400)}")
                    continue
                payload["stats"]["searched"] += len(rows)
                for row in rows:
                    search_results.setdefault(row["url"], row)
                self._save(payload)

        for result in list(search_results.values())[: config.max_articles_per_scan]:
            try:
                article = connector.read_article(result)
            except (WechatRecruitmentError, subprocess.SubprocessError, OSError) as exc:
                payload["errors"].append(
                    f"{result.get('title') or result['url']}："
                    f"{_public_error(exc, 400)}"
                )
                continue
            payload["stats"]["read"] += 1
            classification, reason, matched_account = classify_wechat_article(
                article,
                accounts,
            )
            stored = self._store_article(
                candidate_id=candidate_id,
                company_name=company_name,
                article=article,
                classification=classification,
                reason=reason,
                matched_account=matched_account,
            )
            payload["stats"][stored["event"]] += 1
            if classification == "official_recruitment":
                payload["stats"]["official"] += 1
                if stored["imported"]:
                    payload["stats"]["imported"] += 1
            elif classification == "third_party_lead":
                payload["stats"]["leads"] += 1
            else:
                payload["stats"]["ignored"] += 1
            payload["articles"].append(
                {
                    "id": stored["articleId"],
                    "title": article["title"],
                    "accountName": article.get("accountName"),
                    "url": article["url"],
                    "publishedAt": article.get("publishedAt"),
                    "classification": classification,
                    "reason": reason,
                    "event": stored["event"],
                    "imported": stored["imported"],
                }
            )
            self._save(payload)

    def _store_article(
        self,
        *,
        candidate_id: str,
        company_name: str,
        article: dict[str, Any],
        classification: str,
        reason: str,
        matched_account: dict[str, Any] | None,
    ) -> dict[str, Any]:
        now = self._now()
        identity = f"{candidate_id}|{article['url']}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        article_id = f"wechat-article-{digest[:24]}"
        source_id = (
            f"wechat-source-{digest[:24]}"
            if classification != "non_recruitment"
            else None
        )
        verification = (
            "verified_official"
            if classification == "official_recruitment"
            else "pending"
            if classification == "third_party_lead"
            else "rejected"
        )
        record = {
            "article_id": article_id,
            "candidate_id": candidate_id,
            "account_id": (
                matched_account["account_id"] if matched_account else None
            ),
            "title": article["title"],
            "account_name": article.get("accountName"),
            "account_identifier": article.get("accountIdentifier"),
            "biz_id": article.get("bizId"),
            "source_url": article["url"],
            "summary": article.get("summary"),
            "content": article["content"],
            "published_at": article.get("publishedAt"),
            "classification": classification,
            "verification_status": verification,
            "reason": reason,
            "content_hash": hashlib.sha256(
                article["content"].encode("utf-8")
            ).hexdigest(),
            "source_id": source_id,
            "imported_job_id": None,
            "first_seen_at": now,
            "updated_at": now,
        }
        event = self.repository.save_wechat_article(record)
        imported_job_id: str | None = None
        if source_id:
            self.repository.save_candidate_source(
                {
                    "source_id": source_id,
                    "candidate_id": candidate_id,
                    "source_kind": (
                        "official_account"
                        if classification == "official_recruitment"
                        else "third_party_lead"
                    ),
                    "verification_status": verification,
                    "material_type": "webpage",
                    "title": article["title"],
                    "source_url": article["url"],
                    "content": article["content"],
                    "published_at": article.get("publishedAt"),
                    "parent_company": (
                        matched_account.get("parent_company")
                        if matched_account
                        else None
                    ),
                    "imported_job_id": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        if classification == "official_recruitment":
            job_event = JobStorage(
                self.repository.settings.app.database_path
            ).store_jobs(
                [
                    JobPosting(
                        record_type="notice",
                        company=company_name,
                        title=article["title"],
                        description=article["content"],
                        published_at=article.get("publishedAt"),
                        source_url=article["url"],
                        application_method="企业官方招聘公众号发布",
                        match_reason="公众号自动导入，尚未使用 DeepSeek 评估届别匹配",
                        profile_fit_reason="公众号自动导入，尚未使用 DeepSeek 评估能力匹配",
                        difficulty_reason="公众号自动导入，尚未使用 DeepSeek 评估投递难度",
                    )
                ],
                now,
            )[0]
            imported_job_id = job_event.entity_key
            self.repository.set_candidate_source_imported_job(
                source_id,
                imported_job_id,
            )
        if source_id:
            self.repository.set_wechat_article_imports(
                article_id,
                source_id=source_id,
                imported_job_id=imported_job_id,
            )
        return {
            "articleId": article_id,
            "event": event,
            "imported": imported_job_id is not None,
        }
