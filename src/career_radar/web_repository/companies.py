"""公司列表、详情与页面记录。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..models import CompanyConfig
from .common import _INDUSTRY_LABELS, company_id


class CompaniesMixin:
    def list_companies(self) -> list[dict[str, Any]]:
        settings = self.settings
        with self.transaction() as connection:
            stats = {
                row["company"]: row
                for row in connection.execute(
                    """
                    SELECT company, COUNT(*) AS job_count,
                           MAX(last_seen_at) AS last_scan_at
                    FROM jobs GROUP BY company
                    """
                ).fetchall()
            }
        render_mode = {"auto": "auto", "never": "static", "always": "dynamic"}[
            settings.crawler.render_mode
        ]
        runs = self.list_runs()
        config_added_at = datetime.fromtimestamp(
            self.config_path.stat().st_ctime,
            ZoneInfo(settings.app.timezone),
        ).isoformat(timespec="seconds")
        result = []
        for company in settings.companies:
            stat = stats.get(company.name)
            run_results: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for run in runs:
                company_run = next(
                    (
                        item
                        for item in run.get("companies", [])
                        if item.get("companyName") == company.name
                    ),
                    None,
                )
                if company_run is not None:
                    run_results.append((run, company_run))
            latest_run, latest_company_run = run_results[0] if run_results else ({}, {})
            latest_status = latest_company_run.get("status")
            last_error = latest_company_run.get("error")
            consecutive_failures = 0
            for _run, company_run in run_results:
                if company_run.get("status") != "failed":
                    break
                consecutive_failures += 1
            if not company.enabled:
                status = "paused"
            elif latest_status in {"running", "waiting"} and latest_run.get("status") in {
                "pending",
                "running",
                "stopping",
            }:
                status = "scanning"
            elif latest_status == "failed":
                status = "robots_blocked" if "robots" in (last_error or "").casefold() else "request_failed"
            elif (
                latest_status == "skipped"
                and latest_company_run.get("skipReason") == "user_stop"
            ):
                status = "active" if stat and stat["last_scan_at"] else "pending_verification"
            elif latest_status == "skipped":
                status = "robots_blocked" if "robots" in (last_error or "").casefold() else "structure_error"
            elif latest_status == "success" or (stat and stat["last_scan_at"]):
                status = "active"
            else:
                status = "pending_verification"
            last_scan_at = (
                latest_run.get("finishedAt")
                or latest_run.get("startedAt")
                or (stat["last_scan_at"] if stat else None)
            )
            result.append(
                {
                    "id": company_id(company.name),
                    "name": company.name,
                    "shortName": company.name.split()[0],
                    "website": company.url,
                    "careersUrl": company.url,
                    "industry": _INDUSTRY_LABELS[company.industry_category.value],
                    "industryCategory": company.industry_category.value,
                    "companyType": company.company_type.value,
                    "province": company.province,
                    "city": company.city,
                    "priority": company.priority.value,
                    "monitorMode": company.monitor_mode.value,
                    "atsSource": (
                        company.ats_source.type.value
                        if company.ats_source is not None and company.ats_source.enabled
                        else None
                    ),
                    "governmentHonors": company.government_honors,
                    "evidenceUrls": company.evidence_urls,
                    "status": status,
                    "renderMode": render_mode,
                    "robotsStatus": "blocked" if status == "robots_blocked" else "unknown",
                    "lastScanAt": last_scan_at,
                    "recentJobCount": stat["job_count"] if stat else 0,
                    "consecutiveFailures": consecutive_failures,
                    "maxPages": company.max_pages or settings.crawler.max_pages_per_company,
                    "recruitmentChannel": company.recruitment_channel.value,
                    "parentCompany": company.parent_company,
                    "attributionKeywords": company.attribution_keywords,
                    "enabled": company.enabled,
                    "note": company.notes,
                    "discoveredEntry": company.url,
                    "lastError": last_error,
                    "addedAt": config_added_at,
                }
            )
        return result

    def find_company(self, identifier: str) -> tuple[int, CompanyConfig] | None:
        for index, company in enumerate(self.settings.companies):
            if company_id(company.name) == identifier:
                return index, company
        return None

    def list_company_pages(
        self,
        identifier: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """返回企业最近的真实页面抓取记录，包含失败页供诊断。"""

        labels = {
            "no_jobs": "非招聘页",
            "career_home": "招聘入口页",
            "job_list": "招聘列表页",
            "job_detail": "职位详情页",
            "mixed": "招聘混合页",
        }
        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT * FROM web_page_visits
                WHERE company_id = ? ORDER BY id DESC LIMIT ?
                """,
                (identifier, limit),
            ).fetchall()
        return [
            {
                "runId": row["run_id"],
                "url": row["final_url"],
                "requestedUrl": row["requested_url"],
                "pageType": labels.get(row["page_type"], "抓取失败页"),
                "method": row["method"],
                "httpStatus": row["http_status"],
                "contentLength": row["content_length"],
                "llmExtracted": bool(row["llm_extracted"]),
                "cacheStatus": row["cache_status"],
                "jobsFound": row["jobs_found"],
                "status": row["status"],
                "error": row["error"],
                "fetchedAt": row["fetched_at"],
            }
            for row in rows
        ]

