"""把抓取、智能分析、内存合并、去重、输出和通知串成一次完整运行。"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo

from .crawler import PageFetcher
from .discovery import heuristic_follow_links, is_irrelevant_link, parse_html
from .job_merge import is_same_job, merge_job_postings
from .llm import PageAnalyzer, create_provider
from .mailer import MailError, send_job_email
from .models import (
    CompanyConfig,
    CompanyRunResult,
    JobPosting,
    RunResult,
    Settings,
    StoredJobEvent,
)
from .output import ReportWriter
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


class CompanyMonitor:
    """对一家公司的公开页面执行有边界的广度优先遍历。"""

    def __init__(self, settings: Settings, fetcher: PageFetcher, analyzer: PageAnalyzer) -> None:
        self.settings = settings
        self.fetcher = fetcher
        self.analyzer = analyzer

    def crawl(
        self,
        company: CompanyConfig,
        on_page_progress: PageProgressCallback | None = None,
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

        # 大型央国企招聘站的栏目很多，允许为单家公司设置更保守的页数上限；
        # 未配置时继续使用全局值，保持旧配置行为不变。
        page_limit = company.max_pages or self.settings.crawler.max_pages_per_company
        while queue and attempts < page_limit:
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
                page = self.fetcher.fetch(requested_url)
                final_url = canonicalize_url(page.final_url)
                final_host = urlsplit(final_url).hostname or ""
                if final_host:
                    trusted_hosts.add(final_host)
                if final_url in visited:
                    continue
                visited.add(final_url)
                # ``final_url`` 用作去重键可以去掉尾斜杠；解析相对链接时必须使用
                # 服务端真实目录 URL，否则 ``./202607/article.htm`` 会错误地少一层路径。
                document = parse_html(
                    page.html,
                    normalize_request_url(page.final_url),
                )
                analysis = self.analyzer.analyze_page(
                    company.name,
                    final_url,
                    document,
                    self.settings.crawler.max_links_in_prompt,
                    monitor_mode=company.monitor_mode.value,
                )
                LOGGER.info(
                    "公司=%s 页面=%s 类型=%s 岗位=%s 渲染=%s",
                    company.name,
                    final_url,
                    analysis.page_type,
                    len(analysis.jobs),
                    page.rendered,
                )
                for job in analysis.jobs:
                    _add_or_merge(jobs, job)

                fetched_at = datetime.now(
                    ZoneInfo(self.settings.app.timezone)
                ).isoformat(timespec="seconds")
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
                        "llmExtracted": True,
                        "jobsFound": len(analysis.jobs),
                        "status": "success",
                        "fetchedAt": fetched_at,
                    },
                )

                candidates_by_url = {
                    canonicalize_url(link.url): link for link in document.links
                }
                follow_urls = []
                for follow in analysis.follow_links:
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
                # 官网首页只有明确开启智能发现时才补充启发式招聘入口。
                allow_heuristic = final_url != canonicalize_url(company.url) or discovery_enabled
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

        provider = create_provider(self.settings.llm)
        analyzer = PageAnalyzer(self.settings.llm, provider, self.settings.candidate)
        company_results: list[CompanyRunResult] = []
        events: list[StoredJobEvent] = []
        storage: JobStorage | None = None
        if not dry_run:
            storage = JobStorage(self.settings.app.database_path)
            storage.initialize()
        with PageFetcher(self.settings.crawler) as fetcher:
            monitor = CompanyMonitor(self.settings, fetcher, analyzer)
            for company in selected:
                LOGGER.info("开始监控公司：%s (%s)", company.name, company.url)
                _safe_callback(on_company_start, company)
                try:
                    company_result = monitor.crawl(company, on_page_progress)
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
        if not dry_run:
            writer = ReportWriter(self.settings.app.output_dir)
            report_path, csv_path = writer.write_daily(
                output_events,
                errors,
                datetime.now(timezone),
                write_empty=self.settings.app.write_empty_report,
            )
            notify_levels = set(self.settings.app.notify_match_levels)
            notify_profile_levels = set(self.settings.app.notify_profile_fit_levels)
            email_events = [
                event
                for event in changed
                if event.job.match_level in notify_levels
                and event.job.profile_fit_level in notify_profile_levels
                and event.job.difficulty_score <= self.settings.app.notify_max_difficulty_score
            ]
            if self.settings.smtp.enabled and not disable_email and email_events:
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
            errors=errors,
        )
