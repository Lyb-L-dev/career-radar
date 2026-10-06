"""本地健康状态、今日概览和跨资源搜索路由。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from .api_reports import report_items
from .web_repository import WebRepository


def _dashboard_json(repository: WebRepository) -> dict[str, Any]:
    settings = repository.settings
    jobs = repository.list_jobs()
    runs = repository.list_runs()
    today = datetime.now(ZoneInfo(settings.app.timezone)).date().isoformat()
    today_new = [job for job in jobs if job.get("firstSeenAt", "").startswith(today)]
    today_updated = [
        job
        for job in jobs
        if job["status"] == "updated" and job.get("lastUpdatedAt", "").startswith(today)
    ]
    companies = repository.list_companies()
    success = sum(company["status"] == "active" for company in companies)
    pending = sum(company["status"] == "pending_verification" for company in companies)
    last_scan = (
        (runs[0].get("finishedAt") or runs[0]["startedAt"])
        if runs
        else max(
            (job["lastUpdatedAt"] for job in jobs),
            default=datetime.now().isoformat(),
        )
    )
    attention = []
    if pending:
        attention.append(
            {
                "id": "pending-companies",
                "kind": "verify",
                "text": f"{pending} 家企业尚无真实岗位记录，建议运行首次扫描",
                "actionLabel": "查看企业",
                "link": "/companies",
            }
        )
    if not settings.smtp.enabled:
        attention.append(
            {
                "id": "smtp-disabled",
                "kind": "smtp",
                "text": "SMTP 尚未开启，邮件提醒当前不可用",
                "actionLabel": "前往设置",
                "link": "/settings?tab=email",
            }
        )
    return {
        "todayNew": len(today_new),
        "todayNewDelta": 0,
        "todayUpdated": len(today_updated),
        "todayUpdatedDelta": 0,
        "highMatch": sum(job["abilityMatch"] == "high" and job.get("eligibility", {}).get("verdict") != "ineligible" for job in jobs),
        "highMatchDelta": 0,
        "monitoredCompanies": sum(company["enabled"] for company in companies),
        "lastScanAt": last_scan,
        "environment": {
            **repository.environment(),
            "successCompanies": success,
            "pendingCompanies": pending,
        },
        "attentionItems": attention,
    }


def _search_json(repository: WebRepository, query: str, limit: int) -> dict[str, Any]:
    keyword = query.casefold().strip()
    jobs = repository.search_jobs(keyword, limit)
    companies = [
        company
        for company in repository.list_companies()
        if keyword
        in " ".join(
            (company["name"], company["website"], company["note"] or "")
        ).casefold()
    ][:limit]
    reports = [
        item
        for item in report_items(repository)
        if keyword in f"{item['date']} {item['summary']}".casefold()
    ][:limit]
    runs = [
        item
        for item in repository.list_runs()
        if keyword in f"{item['code']} {item['status']}".casefold()
    ][:limit]
    return {"jobs": jobs, "companies": companies, "reports": reports, "runs": runs}


def create_overview_router(repository: WebRepository) -> APIRouter:
    """创建只读概览路由，将聚合规则集中在一个模块中。"""

    router = APIRouter(prefix="/api", tags=["overview"])

    @router.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/dashboard")
    def dashboard() -> dict[str, Any]:
        return _dashboard_json(repository)

    @router.get("/search")
    def search(
        q: str = Query(min_length=1, max_length=200),
        limit: int = Query(20, ge=1, le=100),
    ) -> dict[str, Any]:
        return _search_json(repository, q, limit)

    return router
