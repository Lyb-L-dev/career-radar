"""官网岗位评估的缓存、后台进度与本地资料版本保护。"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from .application.llm import ApplicationLLMGateway, CompatibleApplicationGateway
from .llm import FatalLLMError
from .models import CandidateProfile, JobPosting, LLMConfig
from .official_screening import (
    OfficialFitResult,
    evaluate_fit,
    fit_context_hash,
    priority_view,
    qualify,
)
from .public_errors import public_error_message
from .storage import JobStorage
from .task_coordinator import TaskCoordinator

if TYPE_CHECKING:
    from .web_repository import WebRepository

LOGGER = logging.getLogger(__name__)


def assessment_view(job: JobPosting, profile: CandidateProfile, model: str, cached: dict | None) -> dict:
    qualification = qualify(job, profile)
    fit = None
    status = "pending"
    if cached:
        if cached["context_hash"] != fit_context_hash(job, profile, model):
            status = "stale"
        elif cached.get("error"):
            status = "failed"
        elif cached.get("payload_json"):
            fit = OfficialFitResult.model_validate_json(cached["payload_json"])
            status = "current"
    return {
        "eligibility": qualification.model_dump(mode="json"),
        "aiAssessment": {
            "status": status,
            "model": cached["model"] if cached else model,
            "evaluatedAt": cached["evaluated_at"] if cached else None,
            "error": cached.get("error") if cached and status == "failed" else None,
            "result": fit.model_dump(mode="json") if fit else None,
        },
        "priority": priority_view(qualification, fit),
    }


class OfficialScreeningManager:
    def __init__(
        self,
        repository: WebRepository,
        coordinator: TaskCoordinator | None = None,
        gateway_factory: Callable[[LLMConfig], ApplicationLLMGateway] = CompatibleApplicationGateway,
    ) -> None:
        self.repository = repository
        self.coordinator = coordinator or TaskCoordinator()
        self.gateway_factory = gateway_factory
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="official-screening")
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._closed = False
        self._state: dict = {"status": "idle", "total": 0, "processed": 0, "evaluated": 0, "cached": 0, "ineligible": 0, "failed": 0, "skipped": 0, "error": None, "currentTitle": None}

    def status(self) -> dict:
        with self._lock:
            return dict(self._state)

    def _update(self, **values) -> None:
        with self._lock:
            self._state.update(values)

    def start(self, ids: list[str] | None = None, *, force: bool = False) -> dict:
        settings = self.repository.settings
        storage = JobStorage(settings.app.database_path)
        storage.initialize()
        with storage.transaction() as conn:
            rows = conn.execute("SELECT entity_key,payload_json FROM jobs ORDER BY updated_at DESC").fetchall()
        available = {r["entity_key"]: JobPosting.model_validate_json(r["payload_json"]) for r in rows}
        if ids and any(key not in available for key in ids):
            raise ValueError("部分官网岗位已不存在，请刷新后重试")
        selected = [(key, job) for key, job in available.items() if ids is None or key in ids]
        with self._lock:
            if self._closed:
                raise RuntimeError("评估服务正在关闭")
            if self._state["status"] == "running":
                raise RuntimeError("官网岗位评估正在进行，请等待完成")
            self._cancel.clear()
            self._state = {"status": "running", "total": len(selected), "processed": 0, "evaluated": 0, "cached": 0, "ineligible": 0, "failed": 0, "skipped": 0, "error": None, "currentTitle": None}
        self._executor.submit(self._run, selected, settings.candidate.model_copy(deep=True), settings.llm.model_copy(deep=True), force)
        return self.status()

    def stop(self) -> dict:
        self._cancel.set()
        return self.status()

    def _run(self, selected: list[tuple[str, JobPosting]], profile: CandidateProfile, llm: LLMConfig, force: bool) -> None:
        counts = {"processed": 0, "evaluated": 0, "cached": 0, "ineligible": 0, "failed": 0, "skipped": 0}
        storage = JobStorage(self.repository.settings.app.database_path)
        gateway = None
        fatal = False
        try:
            for key, job in selected:
                if self._cancel.is_set():
                    break
                self._update(currentTitle=job.title)
                if job.record_type != "job" or not job.jd_complete:
                    counts["skipped"] += 1
                elif qualify(job, profile).verdict == "ineligible":
                    counts["ineligible"] += 1
                else:
                    context = fit_context_hash(job, profile, llm.model)
                    with storage.transaction() as conn:
                        row = conn.execute("SELECT * FROM official_job_assessments WHERE entity_key=?", (key,)).fetchone()
                    if not force and row and row["context_hash"] == context and row["payload_json"] and not row["error"]:
                        counts["cached"] += 1
                    else:
                        payload = None
                        error = None
                        try:
                            with self.coordinator.acquire("official_screening", key, {"llm"}):
                                if self._cancel.is_set():
                                    break
                                gateway = gateway or self.gateway_factory(llm.model_copy(update={"max_output_tokens": min(llm.max_output_tokens, 6000)}))
                                result = evaluate_fit(job, profile, gateway)
                                payload = result.model_dump_json()
                        except Exception as exc:
                            LOGGER.warning("官网岗位评估失败 %s：%s", key, type(exc).__name__)
                            error = public_error_message(exc, context="官网岗位评估")
                            counts["failed"] += 1
                            self._update(error=error)
                            fatal = isinstance(exc, FatalLLMError)
                        # 新画像或新 JD 不能被旧任务结果覆盖。页面读取时再次验证上下文哈希。
                        current_settings = self.repository.settings
                        with storage.transaction() as conn:
                            current_row = conn.execute("SELECT payload_json FROM jobs WHERE entity_key=?", (key,)).fetchone()
                            current_job = JobPosting.model_validate_json(current_row[0]) if current_row else None
                            if current_job and fit_context_hash(current_job, current_settings.candidate, current_settings.llm.model) == context:
                                conn.execute("""INSERT INTO official_job_assessments(entity_key,context_hash,payload_json,error,model,evaluated_at)
                                    VALUES(?,?,?,?,?,?) ON CONFLICT(entity_key) DO UPDATE SET context_hash=excluded.context_hash,
                                    payload_json=excluded.payload_json,error=excluded.error,model=excluded.model,evaluated_at=excluded.evaluated_at""",
                                    (key, context, payload, error, llm.model, datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")))
                                if payload:
                                    counts["evaluated"] += 1
                            else:
                                counts["skipped"] += 1
                counts["processed"] += 1
                self._update(**counts)
                if fatal:
                    break
            self._update(status="cancelled" if self._cancel.is_set() else "partial" if fatal or counts["failed"] else "completed", currentTitle=None, **counts)
        except Exception as exc:
            self._update(status="partial", currentTitle=None, error=public_error_message(exc, context="官网批量评估"), **counts)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
        self._cancel.set()
        self._executor.shutdown(wait=True, cancel_futures=True)
