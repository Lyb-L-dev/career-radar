"""Import and triage BOSS leads separately from verified official jobs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .application.llm import CompatibleApplicationGateway
from .boss_ai import BossAIScreener
from .boss_capture import (
    BossCaptureError,
    BossCaptureManager,
    CaptureRequest,
    candidate_from_verified_resume,
    model_identity,
)
from .llm import LLMError
from .platform_leads import (
    BossExportError,
    BossLeadRepository,
    BossPreferences,
    parse_boss_export,
)
from .public_errors import public_error_message
from .web_repository import WebRepository


class BossImportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=2, max_length=5_000_000)


class BossStatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(pattern="^(favorite|applied|hidden)$")
    value: bool


class BossAIScreenPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = False


class BossPreferencesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currentStudent: bool | None = None
    acceptInternship: bool


class BossCrawlPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keyword: str = Field(default="", max_length=40)
    city: str = Field(default="全国", min_length=1, max_length=30)
    pages: int = Field(default=1, ge=1, le=2)
    maxDetails: int = Field(default=8, ge=1, le=12)


def _candidate(settings):
    try:
        return candidate_from_verified_resume(settings)
    except BossCaptureError:
        return settings.candidate


def create_platform_leads_router(
    leads: BossLeadRepository, repository: WebRepository, capture: BossCaptureManager
) -> APIRouter:
    router = APIRouter(prefix="/api/platform-leads", tags=["platform-leads"])

    @router.get("/crawl")
    def get_crawl_status() -> dict[str, object]:
        return capture.status()

    @router.get("/crawl/plan")
    def get_crawl_plan(keyword: str = "") -> dict[str, object]:
        if len(keyword) > 40 or (keyword.strip() and len(keyword.strip()) < 2):
            raise HTTPException(422, "补充关键词需为 2–40 个字符")
        try:
            return capture.plan(keyword.strip())
        except BossCaptureError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/crawl/browser")
    def open_crawl_browser() -> dict[str, bool]:
        try:
            return capture.open_browser()
        except BossCaptureError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/crawl")
    def start_crawl(payload: BossCrawlPayload) -> dict[str, object]:
        keyword = payload.keyword.strip()
        city = payload.city.strip()
        if (keyword and len(keyword) < 2) or not city:
            raise HTTPException(422, "请填写有效的补充关键词和城市；城市不限可填全国")
        try:
            return capture.start(CaptureRequest(
                keyword=keyword, city=city,
                pages=payload.pages, max_details=payload.maxDetails,
            ))
        except BossCaptureError as exc:
            raise HTTPException(422, str(exc)) from exc

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
        settings = repository.settings
        return leads.list_leads(_candidate(settings), model_identity(settings))

    @router.get("/preferences")
    def get_preferences() -> dict[str, bool | None]:
        preferences = leads.get_preferences(repository.settings.candidate.accept_internship)
        return {
            "currentStudent": preferences.current_student,
            "acceptInternship": preferences.accept_internship,
        }

    @router.put("/preferences")
    def save_preferences(payload: BossPreferencesPayload) -> dict[str, bool | None]:
        preferences = BossPreferences(
            current_student=payload.currentStudent,
            accept_internship=payload.acceptInternship,
        )
        leads.set_preferences(preferences)
        return {
            "currentStudent": preferences.current_student,
            "acceptInternship": preferences.accept_internship,
        }

    @router.post("/{lead_id}/ai-screen")
    def ai_screen(lead_id: str, payload: BossAIScreenPayload) -> dict[str, object]:
        if not payload.confirmed:
            raise HTTPException(422, "点击 AI 筛选后才会调用当前配置的模型")
        settings = repository.settings
        if settings.llm.provider != "mimo":
            raise HTTPException(422, "BOSS AI 筛选使用小米 MiMo，请先在设置中选择 MiMo")
        screen_config = settings.llm.model_copy(
            update={
                "max_output_tokens": min(settings.llm.max_output_tokens, 1800),
                "max_retries": min(settings.llm.max_retries, 2),
                "request_timeout_seconds": min(settings.llm.request_timeout_seconds, 45),
            }
        )
        screener = BossAIScreener(leads, lambda: CompatibleApplicationGateway(screen_config))
        try:
            return screener.screen(lead_id, _candidate(settings), model_identity(settings))
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, public_error_message(exc, context="AI 筛选")) from exc
        except LLMError as exc:
            raise HTTPException(503, public_error_message(exc, context="AI 筛选")) from exc

    @router.post("/{lead_id}/state")
    def set_state(lead_id: str, payload: BossStatePayload) -> dict[str, bool]:
        if not leads.set_state(lead_id, payload.field, payload.value):
            raise HTTPException(404, "平台岗位不存在")
        return {"ok": True}

    return router
