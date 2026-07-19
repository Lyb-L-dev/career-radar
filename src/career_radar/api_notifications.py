"""站内通知资源的 FastAPI 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .web_repository import WebRepository


def notification_items(repository: WebRepository) -> list[dict[str, Any]]:
    """根据高匹配岗位和失败运行实时构造通知，并叠加已读状态。"""

    items: list[dict[str, Any]] = []
    for job in repository.list_jobs()[:100]:
        if job["gradYearMatch"] == "high" and job["abilityMatch"] in {"high", "medium"}:
            items.append(
                {
                    "id": f"job-{job['id']}",
                    "type": "high_match_job",
                    "title": f"发现匹配岗位：{job['title']}",
                    "body": f"{job['companyName']} · {job['city']} · 难度 {job['difficulty']}/10",
                    "time": job["lastUpdatedAt"],
                    "read": False,
                    "link": f"/jobs/{job['id']}",
                }
            )
    for run in repository.list_runs()[:20]:
        if run["status"] in {"failed", "partial"}:
            items.append(
                {
                    "id": f"run-{run['id']}",
                    "type": "company_failed",
                    "title": "扫描任务存在失败企业",
                    "body": f"{run['code']}：失败 {run['failedCount']} 家，请查看运行详情。",
                    "time": run.get("finishedAt") or run["startedAt"],
                    "read": False,
                    "link": f"/runs/{run['id']}",
                }
            )
    states = repository.notification_states()
    visible = []
    for item in items:
        is_read, is_dismissed = states.get(item["id"], (False, False))
        if is_dismissed:
            continue
        item["read"] = is_read
        visible.append(item)
    return sorted(visible, key=lambda item: item["time"], reverse=True)


def create_notifications_router(repository: WebRepository) -> APIRouter:
    """创建通知列表、标记已读和删除路由。"""

    router = APIRouter(prefix="/api", tags=["notifications"])

    @router.get("/notifications")
    def notifications() -> list[dict[str, Any]]:
        return notification_items(repository)

    @router.post("/notifications/{notification_id}/read")
    def read_notification(notification_id: str) -> dict[str, bool]:
        repository.set_notification_state([notification_id], is_read=True)
        return {"ok": True}

    @router.post("/notifications/read-all")
    def read_all_notifications() -> dict[str, bool]:
        repository.set_notification_state(
            [item["id"] for item in notification_items(repository)], is_read=True
        )
        return {"ok": True}

    @router.delete("/notifications/{notification_id}")
    def remove_notification(notification_id: str) -> dict[str, bool]:
        repository.set_notification_state([notification_id], is_dismissed=True)
        return {"ok": True}

    return router
