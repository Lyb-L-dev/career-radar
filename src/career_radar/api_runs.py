"""扫描运行任务的 FastAPI 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .llm import LLMError
from .run_manager import RunConflictError, RunManager
from .web_repository import WebRepository


class RunCreatePayload(BaseModel):
    """创建一次官网扫描所需的范围和通知选项。"""

    model_config = ConfigDict(extra="forbid")
    scope: str = Field(default="all", pattern=r"^(all|failed|company|company_type)$")
    companyId: str | None = None
    companyType: str | None = Field(
        default=None,
        pattern=r"^(central_soe|local_soe|private|foreign|joint_venture|other)$",
    )
    sendEmail: bool = False


def create_runs_router(repository: WebRepository, manager: RunManager) -> APIRouter:
    """创建运行记录查询、启动、重试和停止路由。"""

    router = APIRouter(prefix="/api", tags=["runs"])

    @router.get("/runs")
    def list_runs() -> list[dict[str, Any]]:
        return repository.list_runs()

    @router.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run = repository.get_run(run_id)
        if run is None:
            raise HTTPException(404, "运行任务不存在")
        return run

    @router.post("/runs", status_code=202)
    def create_run(payload: RunCreatePayload) -> dict[str, Any]:
        try:
            if payload.companyType:
                run = manager.create(
                    payload.scope,
                    payload.sendEmail,
                    payload.companyId,
                    payload.companyType,
                )
            else:
                # 保留原三参数形式，兼容现有扩展代码和测试替身。
                run = manager.create(payload.scope, payload.sendEmail, payload.companyId)
        except LLMError as exc:
            raise HTTPException(422, f"扫描前检查失败：{exc}") from exc
        except (RunConflictError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"ok": True, "runId": run["id"]}

    @router.post("/runs/{run_id}/retry", status_code=202)
    def retry_run(run_id: str) -> dict[str, Any]:
        if repository.get_run(run_id) is None:
            raise HTTPException(404, "运行任务不存在")
        try:
            retry = manager.create("failed", False)
        except LLMError as exc:
            raise HTTPException(422, f"扫描前检查失败：{exc}") from exc
        except (RunConflictError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"ok": True, "runId": retry["id"]}

    @router.post("/runs/{run_id}/stop")
    def stop_run(run_id: str) -> dict[str, bool]:
        try:
            manager.stop(run_id)
        except (RunConflictError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"ok": True}

    return router
