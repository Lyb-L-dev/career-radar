"""Local growth API; model mutations return persistent background operations."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetPayload(Payload):
    source: Literal["official", "boss", "manual"]
    id: str | None = Field(default=None, max_length=200)
    title: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=100_000)


class TargetUpdate(Payload):
    focus: bool | None = None
    active: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=100_000)


class RequestPayload(Payload):
    requestId: str = Field(min_length=1, max_length=100)


class AnalyzePayload(RequestPayload):
    targetIds: list[str] = Field(default_factory=list, max_length=50)


class SessionPayload(RequestPayload):
    kind: Literal["recall", "baseline"] = "recall"
    skillIds: list[str] = Field(default_factory=list, max_length=3)


class QuestionPayload(RequestPayload):
    questionId: str = Field(min_length=1, max_length=100)


class AnswerPayload(QuestionPayload):
    answer: str = Field(default="", max_length=30_000)
    skipped: bool = False


class ProjectPayload(RequestPayload):
    skillId: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=30_000)
    explanation: str = Field(min_length=1, max_length=10_000)
    runRecord: str = Field(default="", max_length=10_000)


class PlanPayload(Payload):
    adjust: bool = False


class ReflectionPayload(Payload):
    status: Literal["todo", "partial", "done", "blocked"]
    blocker: str = Field(default="", max_length=2000)
    output: str = Field(default="", max_length=5000)


class SettingsPayload(Payload):
    dailyMinutes: int = Field(ge=30, le=480)


class PointPayload(Payload):
    notLearned: bool


def create_growth_router(service, manager):
    router = APIRouter(prefix="/api/growth", tags=["growth"])

    def call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def start(kind, payload, extra=None):
        data = payload.model_dump(exclude={"requestId"})
        return call(manager.start, kind, {**data, **(extra or {})}, payload.requestId)

    @router.get("")
    def overview():
        return service.snapshot()

    @router.get("/sources")
    def sources():
        return service.sources()

    @router.post("/targets")
    def add_target(payload: TargetPayload):
        return call(service.add_target, payload.model_dump())

    @router.patch("/targets/{target_id}")
    def update_target(target_id: str, payload: TargetUpdate):
        return call(service.update_target, target_id, payload.model_dump(exclude_none=True))

    @router.post("/targets/{target_id}/refresh")
    def refresh_target(target_id: str):
        return call(service.refresh_target, target_id)

    @router.post("/analyze", status_code=202)
    def analyze(payload: AnalyzePayload):
        return start("analyze", payload)

    @router.get("/skills/{skill_id}")
    def skill_detail(skill_id: str):
        return call(service.skill_detail, skill_id)

    @router.put("/skills/{skill_id}/points/{point_id}")
    def mark_point(skill_id: str, point_id: str, payload: PointPayload):
        call(service.mark_unlearned, skill_id, point_id, payload.notLearned)
        return {"saved": True}

    @router.post("/sessions", status_code=202)
    def session(payload: SessionPayload):
        return start("session", payload)

    @router.get("/sessions/{session_id}")
    def get_session(session_id: str):
        return service.public_session(call(service.require, "sessions", session_id))

    @router.post("/sessions/{session_id}/answers", status_code=202)
    def answer(session_id: str, payload: AnswerPayload):
        if not payload.skipped and not payload.answer.strip():
            raise HTTPException(422, "请填写回答；不会时可以直接写‘不会’或请求讲解")
        return start("answer", payload, {"sessionId": session_id})

    @router.post("/sessions/{session_id}/hint", status_code=202)
    def hint(session_id: str, payload: QuestionPayload):
        return start("hint", payload, {"sessionId": session_id})

    @router.post("/projects", status_code=202)
    def project(payload: ProjectPayload):
        if not payload.code.strip() or not payload.explanation.strip():
            raise HTTPException(422, "请提交代码或项目材料，以及自己的解释")
        return start("project", payload)

    @router.get("/operations/{operation_id}")
    def operation(operation_id: str):
        return service.public_operation(call(service.require, "operations", operation_id))

    @router.post("/operations/{operation_id}/retry", status_code=202)
    def retry(operation_id: str):
        return call(manager.retry, operation_id)

    @router.post("/plans/today")
    def plan(payload: PlanPayload):
        return call(service.plan, payload.adjust)

    @router.get("/plans")
    def history():
        return list(reversed(service.repo.all("plans")))

    @router.patch("/plans/{date}/tasks/{task_id}")
    def reflect(date: str, task_id: str, payload: ReflectionPayload):
        return call(service.reflect, date, task_id, payload.model_dump())

    @router.put("/settings")
    def settings(payload: SettingsPayload):
        call(service.update_settings, payload.dailyMinutes)
        return {"saved": True}

    return router
