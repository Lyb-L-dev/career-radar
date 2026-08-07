"""Automation-center routes with preview and explicit mutation confirmation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .automation import AutomationError, AutomationService
from .web_repository import WebRepository


class AutomationMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = False
    dailyRunTime: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def create_automation_router(
    repository: WebRepository,
    service: AutomationService,
) -> APIRouter:
    router = APIRouter(prefix="/api/automation", tags=["automation"])

    @router.get("")
    def status() -> dict[str, object]:
        return service.status(repository.settings.app.daily_run_time)

    @router.get("/preview")
    def preview(dailyRunTime: str | None = None) -> dict[str, object]:
        return service.preview(
            dailyRunTime or repository.settings.app.daily_run_time
        )

    @router.post("/install")
    def install(payload: AutomationMutation) -> dict[str, object]:
        try:
            return service.install(
                payload.dailyRunTime,
                confirmed=payload.confirmed,
            )
        except (AutomationError, ValueError) as exc:
            raise HTTPException(428 if not payload.confirmed else 422, str(exc)) from exc

    @router.post("/remove")
    def remove(payload: AutomationMutation) -> dict[str, object]:
        try:
            return service.remove(
                payload.dailyRunTime,
                confirmed=payload.confirmed,
            )
        except (AutomationError, ValueError) as exc:
            raise HTTPException(428 if not payload.confirmed else 422, str(exc)) from exc

    return router
