"""岗位口碑扫描资源的 FastAPI 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from .reputation import ReputationConflictError, ReputationManager
from .web_repository import WebRepository


def create_reputation_router(
    repository: WebRepository,
    manager: ReputationManager,
) -> APIRouter:
    """创建口碑健康检查、发起扫描和查询结果路由。"""

    router = APIRouter(prefix="/api", tags=["reputation"])

    @router.get("/reputation/health")
    def reputation_health() -> dict[str, Any]:
        return manager.health()

    @router.get("/jobs/{job_id}/reputation")
    def latest_job_reputation(job_id: str) -> dict[str, Any] | None:
        if repository.get_job(job_id) is None:
            raise HTTPException(404, "岗位不存在")
        return manager.latest(job_id)

    @router.post("/jobs/{job_id}/reputation-scan", status_code=202)
    def create_job_reputation_scan(job_id: str) -> dict[str, Any]:
        try:
            payload = manager.create(job_id)
        except ReputationConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"ok": True, "scanId": payload["id"]}

    @router.get("/reputation-scans/{scan_id}")
    def get_reputation_scan(scan_id: str) -> dict[str, Any]:
        payload = manager.get(scan_id)
        if payload is None:
            raise HTTPException(404, "口碑调查不存在")
        return payload

    return router
