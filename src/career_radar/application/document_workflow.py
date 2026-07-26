"""文档渲染、验证、artifact 登记与断点恢复。"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .document_renderer import (
    ApplicationDocumentRenderer,
    RenderedApplicationDocuments,
    file_sha256,
)
from .document_verifier import ApplicationDocumentVerifier
from .models import ApplicationArtifact, ApplicationRun, ApplicationStatus
from .repository import ApplicationRepository

LOGGER = logging.getLogger(__name__)


class ApplicationDocumentWorkflow:
    """消费第二阶段终稿，成功后把任务推进到 ready。"""

    def __init__(
        self,
        repository: ApplicationRepository,
        renderer: ApplicationDocumentRenderer,
        verifier: ApplicationDocumentVerifier,
        timezone: str,
    ) -> None:
        self.repository = repository
        self.renderer = renderer
        self.verifier = verifier
        self.timezone = timezone

    def _now(self) -> str:
        return datetime.now(ZoneInfo(self.timezone)).isoformat(timespec="seconds")

    def _display_date(self) -> str:
        return datetime.now(ZoneInfo(self.timezone)).strftime("%Y年%m月%d日")

    def _context(self, application_id: str):
        run = self.repository.get_run(application_id)
        job = self.repository.get_run_job_snapshot(application_id)
        profile = self.repository.get_profile_snapshot(application_id)
        drafts = self.repository.get_draft_bundle(application_id, 2)
        if run is None or job is None or profile is None or drafts is None:
            raise ValueError("申请任务、冻结快照或终稿不完整")
        return run, job, profile, drafts

    def _artifact(self, run: ApplicationRun, kind: str, path: Path) -> None:
        self.repository.save_artifact(
            ApplicationArtifact(
                id=f"{run.id}-{kind}",
                application_id=run.id,
                kind=kind,
                path=str(path.resolve()),
                sha256=file_sha256(path),
                created_at=self._now(),
            )
        )

    def _register_documents(
        self,
        run: ApplicationRun,
        rendered: RenderedApplicationDocuments,
    ) -> None:
        self._artifact(run, "resume_docx", rendered.resume_docx)
        if rendered.resume_pdf is not None:
            self._artifact(run, "resume_pdf", rendered.resume_pdf)
        else:
            self.repository.delete_artifact(run.id, "resume_pdf")
        if rendered.cover_letter_docx is not None:
            self._artifact(run, "cover_letter_docx", rendered.cover_letter_docx)
        else:
            self.repository.delete_artifact(run.id, "cover_letter_docx")
        if rendered.cover_letter_pdf is not None:
            self._artifact(run, "cover_letter_pdf", rendered.cover_letter_pdf)
        else:
            self.repository.delete_artifact(run.id, "cover_letter_pdf")

    def _write_verification(self, run: ApplicationRun, output_dir: Path, report) -> Path:
        target = output_dir / "verification.json"
        building = output_dir / ".verification.json.building"
        building.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(building, target)
        self._artifact(run, "verification", target)
        return target

    def _fail(self, application_id: str, exc: Exception) -> ApplicationRun:
        LOGGER.exception("申请任务 %s 的文档阶段失败", application_id)
        return self.repository.mark_failed(application_id, str(exc), self._now())

    def run(self, application_id: str) -> ApplicationRun:
        run = self.repository.get_run(application_id)
        if run is None:
            raise ValueError("申请任务不存在")
        if run.status not in {ApplicationStatus.RENDERING, ApplicationStatus.VERIFYING}:
            raise ValueError("只有 rendering/verifying 状态可以执行文档阶段")

        rendered = None
        if run.status == ApplicationStatus.RENDERING:
            try:
                run, job, profile, drafts = self._context(application_id)
                rendered = self.renderer.render(
                    run,
                    job,
                    profile,
                    drafts,
                    self._display_date(),
                )
                self._register_documents(run, rendered)
                run = self.repository.transition(
                    application_id, ApplicationStatus.VERIFYING, self._now()
                )
            except Exception as exc:
                return self._fail(application_id, exc)

        try:
            run, job, profile, drafts = self._context(application_id)
            if rendered is None:
                rendered = self.renderer.existing(run, drafts)
                self._register_documents(run, rendered)
            report = self.verifier.verify(
                run,
                job,
                profile,
                drafts,
                rendered,
                self._now(),
            )
            self._write_verification(run, rendered.output_dir, report)
            if not report.passed:
                return self.repository.mark_failed(
                    application_id,
                    "生成的申请文档未通过本地完整性或页数校验",
                    self._now(),
                )
            return self.repository.transition(
                application_id, ApplicationStatus.READY, self._now()
            )
        except Exception as exc:
            return self._fail(application_id, exc)

    def resume(self, application_id: str) -> ApplicationRun:
        run = self.repository.get_run(application_id)
        if run is None:
            raise ValueError("申请任务不存在")
        if run.status == ApplicationStatus.FAILED:
            if run.failed_step not in {
                ApplicationStatus.RENDERING,
                ApplicationStatus.VERIFYING,
            }:
                raise ValueError("该失败任务不属于文档阶段")
            self.repository.resume_failed(application_id, self._now())
        return self.run(application_id)
