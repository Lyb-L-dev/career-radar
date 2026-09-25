"""Import and triage BOSS leads separately from verified official jobs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .platform_leads import BossExportError, BossLeadRepository, parse_boss_export
from .web_repository import WebRepository


class BossImportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=2, max_length=5_000_000)


class BossStatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(pattern="^(favorite|applied|hidden)$")
    value: bool


def create_platform_leads_router(leads: BossLeadRepository, repository: WebRepository) -> APIRouter:
    router = APIRouter(prefix="/api/platform-leads", tags=["platform-leads"])

    @router.post("/preview")
    def preview_import(payload: BossImportPayload) -> dict[str, object]:
        try:
            rows = parse_boss_export(payload.content)
        except BossExportError as exc:
            raise HTTPException(422, str(exc)) from exc
        complete = sum(row.jd_complete for row in rows)
        return {"total": len(rows), "completeJd": complete, "needsReview": len(rows) - complete}

    @router.post("/import")
    def import_boss(payload: BossImportPayload) -> dict[str, int]:
        try:
            rows = parse_boss_export(payload.content)
        except BossExportError as exc:
            raise HTTPException(422, str(exc)) from exc
        return leads.import_leads(rows)

    @router.get("")
    def list_leads() -> list[dict[str, object]]:
        return leads.list_leads(repository.settings.candidate)

    @router.post("/{lead_id}/state")
    def set_state(lead_id: str, payload: BossStatePayload) -> dict[str, bool]:
        if not leads.set_state(lead_id, payload.field, payload.value):
            raise HTTPException(404, "平台岗位不存在")
        return {"ok": True}

    return router
