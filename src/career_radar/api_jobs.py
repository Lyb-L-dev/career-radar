"""岗位资源的 FastAPI 路由。

路由与应用装配分离后，岗位状态写入可以独立测试，也避免 ``api.py``
同时承担应用工厂、数据访问和所有 HTTP 资源的职责。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .official_screening_service import OfficialScreeningManager
from .web_repository import WebRepository


class JobStatePayload(BaseModel):
    """单个岗位布尔状态，例如收藏或已投递。"""

    model_config = ConfigDict(extra="forbid")
    value: bool


class BulkJobStatePayload(BaseModel):
    """批量岗位状态请求。"""

    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=1000)


class ScreeningPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] | None = Field(default=None, min_length=1, max_length=200)
    force: bool = False


def create_jobs_router(repository: WebRepository, screening: OfficialScreeningManager | None = None) -> APIRouter:
    """创建岗位路由；仓储由应用工厂显式注入。"""

    router = APIRouter(prefix="/api", tags=["jobs"])

    @router.get("/jobs/screening")
    def screening_status() -> dict:
        return screening.status() if screening else {"status": "idle"}

    @router.post("/jobs/screening", status_code=202)
    def screen_jobs(payload: ScreeningPayload) -> dict:
        if screening is None:
            raise HTTPException(503, "官网评估服务尚未启动")
        try:
            return screening.start(payload.ids, force=payload.force)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.delete("/jobs/screening")
    def stop_screening() -> dict:
        if screening is None:
            raise HTTPException(503, "官网评估服务尚未启动")
        return screening.stop()

    @router.get("/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return repository.list_jobs()

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = repository.get_job(job_id)
        if job is None:
            raise HTTPException(404, "岗位不存在")
        return job

    @router.get("/jobs/{job_id}/similar")
    def similar_jobs(
        job_id: str,
        limit: int = Query(default=5, ge=1, le=20),
    ) -> list[dict[str, Any]]:
        if repository.get_job(job_id) is None:
            raise HTTPException(404, "岗位不存在")
        return repository.similar_jobs(job_id, limit)

    @router.post("/jobs/{job_id}/favorite")
    def favorite_job(job_id: str, payload: JobStatePayload) -> dict[str, Any]:
        repository.set_job_state([job_id], "favorite", payload.value)
        return {"isFavorite": payload.value}

    @router.post("/jobs/{job_id}/applied")
    def applied_job(job_id: str, payload: JobStatePayload) -> dict[str, bool]:
        repository.set_job_state([job_id], "applied", payload.value)
        return {"ok": True}

    @router.post("/jobs/{job_id}/ignore-update")
    def ignore_job_update(job_id: str) -> dict[str, bool]:
        if not repository.ignore_job_update(job_id):
            raise HTTPException(404, "岗位不存在")
        return {"ok": True}

    @router.post("/jobs/not-interested")
    def jobs_not_interested(payload: BulkJobStatePayload) -> dict[str, bool]:
        repository.set_job_state(payload.ids, "not_interested", True)
        return {"ok": True}

    @router.post("/jobs/favorite-many")
    def jobs_favorite_many(payload: BulkJobStatePayload) -> dict[str, bool]:
        repository.set_job_state(payload.ids, "favorite", True)
        return {"ok": True}

    return router
