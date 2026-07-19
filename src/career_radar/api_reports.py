"""日报查询与下载的 FastAPI 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .web_repository import WebRepository


def report_items(repository: WebRepository) -> list[dict[str, Any]]:
    """根据真实岗位事件和磁盘文件生成日报索引。"""

    settings = repository.settings
    jobs = repository.list_jobs()
    dates = {path.name.removesuffix("-jobs.md") for path in settings.app.output_dir.glob("*-jobs.md")}
    dates.update(job["firstSeenAt"][:10] for job in jobs if job.get("firstSeenAt"))
    result = []
    for date in sorted(dates, reverse=True):
        new_jobs = [job for job in jobs if job.get("firstSeenAt", "").startswith(date)]
        updated_jobs = [
            job
            for job in jobs
            if job["status"] == "updated" and job.get("lastUpdatedAt", "").startswith(date)
        ]
        high_jobs = [job for job in new_jobs + updated_jobs if job["abilityMatch"] == "high"]
        markdown = settings.app.output_dir / f"{date}-jobs.md"
        csv_path = settings.app.output_dir / f"{date}-jobs.csv"
        result.append(
            {
                "date": date,
                "newJobs": len(new_jobs),
                "updatedJobs": len(updated_jobs),
                "highMatchJobs": len(high_jobs),
                "markdownStatus": "generated" if markdown.exists() else "none",
                "csvStatus": "generated" if csv_path.exists() else "none",
                "emailStatus": "disabled" if not settings.smtp.enabled else "not_sent",
                "summary": f"新增 {len(new_jobs)} 个岗位，更新 {len(updated_jobs)} 个岗位。",
                "topJobIds": [job["id"] for job in high_jobs[:5]],
                "newJobIds": [job["id"] for job in new_jobs],
                "updatedJobIds": [job["id"] for job in updated_jobs],
                "anomalies": [],
                "tomorrowFocus": ["继续监控已启用企业官网，优先核验高匹配岗位有效期。"],
            }
        )
    return result


def create_reports_router(repository: WebRepository) -> APIRouter:
    """创建日报列表、详情与文件下载路由。"""

    router = APIRouter(prefix="/api", tags=["reports"])

    @router.get("/reports")
    def reports() -> list[dict[str, Any]]:
        return report_items(repository)

    @router.get("/reports/{date}")
    def report(date: str) -> dict[str, Any]:
        result = next((item for item in report_items(repository) if item["date"] == date), None)
        if result is None:
            raise HTTPException(404, "日报不存在")
        return result

    @router.get("/reports/{date}/download/{format_name}")
    def download_report(date: str, format_name: str) -> FileResponse:
        if format_name not in {"md", "csv"}:
            raise HTTPException(422, "只支持 md 或 csv")
        path = repository.settings.app.output_dir / f"{date}-jobs.{format_name}"
        if not path.is_file():
            raise HTTPException(404, "日报文件不存在")
        media = "text/markdown" if format_name == "md" else "text/csv"
        return FileResponse(path, media_type=media, filename=path.name)

    @router.post("/reports/generate")
    def generate_report() -> dict[str, bool]:
        raise HTTPException(409, "日报由真实扫描任务生成，请先创建扫描任务")

    @router.post("/reports/{date}/resend")
    def resend_report(_date: str) -> dict[str, bool]:
        raise HTTPException(409, "当前版本不支持脱离岗位事件重新发送历史日报")

    return router
