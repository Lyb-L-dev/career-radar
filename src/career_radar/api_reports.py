"""日报查询与下载的 FastAPI 路由。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from .mailer import MailError
from .report_delivery import HistoricalReportDelivery, ReportDeliveryError
from .web_repository import WebRepository


class ReportEmailPayload(BaseModel):
    """重新发送邮件会产生外部通信，必须由用户明确确认。"""

    model_config = ConfigDict(extra="forbid")
    confirmed: bool = False


def report_items(repository: WebRepository) -> list[dict[str, Any]]:
    """根据真实岗位事件和磁盘文件生成日报索引。"""

    settings = repository.settings
    event_summaries = repository.report_event_summaries()
    delivery_states = repository.report_email_states()
    run_email_dates = repository.report_sent_dates()
    dates = {path.name.removesuffix("-jobs.md") for path in settings.app.output_dir.glob("*-jobs.md")}
    dates.update(event_summaries)
    result = []
    for date in sorted(dates, reverse=True):
        summary = event_summaries.get(
            date,
            {"newJobIds": [], "updatedJobIds": [], "highMatchJobIds": []},
        )
        new_job_ids = summary["newJobIds"]
        updated_job_ids = summary["updatedJobIds"]
        high_job_ids = summary["highMatchJobIds"]
        markdown = settings.app.output_dir / f"{date}-jobs.md"
        csv_path = settings.app.output_dir / f"{date}-jobs.csv"
        email_sent = date in delivery_states or date in run_email_dates
        result.append(
            {
                "date": date,
                "newJobs": len(new_job_ids),
                "updatedJobs": len(updated_job_ids),
                "highMatchJobs": len(high_job_ids),
                "markdownStatus": "generated" if markdown.exists() else "none",
                "csvStatus": "generated" if csv_path.exists() else "none",
                "emailStatus": (
                    "sent"
                    if email_sent
                    else ("disabled" if not settings.smtp.enabled else "not_sent")
                ),
                "summary": f"新增 {len(new_job_ids)} 个岗位，更新 {len(updated_job_ids)} 个岗位。",
                "topJobIds": high_job_ids[:5],
                "newJobIds": new_job_ids,
                "updatedJobIds": updated_job_ids,
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
    async def resend_report(date: str, payload: ReportEmailPayload) -> dict[str, Any]:
        if not payload.confirmed:
            raise HTTPException(428, "请先确认将通过 SMTP 重新发送这份历史日报")
        settings = repository.settings
        try:
            result = await asyncio.to_thread(
                HistoricalReportDelivery(settings).deliver,
                date,
            )
        except ReportDeliveryError as exc:
            raise HTTPException(409, str(exc)) from exc
        except MailError as exc:
            raise HTTPException(502, str(exc)) from exc

        sent_at = datetime.now(ZoneInfo(settings.app.timezone)).isoformat(
            timespec="seconds"
        )
        repository.record_report_email_delivery(
            result.report_date,
            result.event_count,
            sent_at,
        )
        return {
            "ok": True,
            "message": f"历史日报邮件已发送，共 {result.event_count} 个岗位事件",
            "eventCount": result.event_count,
            "sentAt": sent_at,
        }

    return router
