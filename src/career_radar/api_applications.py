"""求职申请任务、审批动作和本地生成文件下载接口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .application.document_renderer import file_sha256
from .application.models import (
    APPLICATION_STATUS_PROGRESS,
    ApplicationRun,
    ApplicationStatus,
)
from .application.profile import ApplicationProfileError, load_application_profile, profile_summary
from .application.repository import ApplicationRepository
from .application.service import ApplicationService
from .application_manager import ApplicationConflictError, ApplicationManager
from .web_repository import WebRepository


def _repository(manager: ApplicationManager) -> ApplicationRepository:
    return manager.repository()


def _application_json(
    repository: ApplicationRepository,
    run: ApplicationRun,
    *,
    active: bool = False,
) -> dict[str, Any]:
    service_payload = ApplicationService.public_json(run)
    job = repository.get_run_job_snapshot(run.id)
    evaluation = repository.get_evaluation(run.id)
    artifacts = repository.list_artifacts(run.id)
    failed_step = run.failed_step or (run.status if run.status == ApplicationStatus.FAILED else None)
    progress = (
        APPLICATION_STATUS_PROGRESS.get(failed_step, 0)
        if run.status == ApplicationStatus.FAILED
        else APPLICATION_STATUS_PROGRESS[run.status]
    )
    return {
        "id": run.id,
        "jobId": run.job_id,
        "status": run.status.value,
        "failedStep": run.failed_step.value if run.failed_step else None,
        "progress": progress,
        "error": service_payload.get("error"),
        "nextAction": service_payload["nextAction"],
        "coverLetterMode": run.cover_letter_mode,
        "resumePageTarget": run.resume_page_target,
        "createdAt": run.created_at,
        "updatedAt": run.updated_at,
        "approvedAt": run.approved_at,
        "completedAt": run.completed_at,
        "isRunning": active,
        "canApprove": not active and run.status == ApplicationStatus.WAITING_FOR_APPROVAL,
        "canResume": not active
        and run.status in {ApplicationStatus.CREATED, ApplicationStatus.FAILED},
        "canReject": not active
        and run.status
        in {ApplicationStatus.CREATED, ApplicationStatus.WAITING_FOR_APPROVAL},
        "canRender": not active
        and run.status in {ApplicationStatus.RENDERING, ApplicationStatus.VERIFYING},
        "job": (
            {
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "recruitmentType": job.recruitment_type,
            }
            if job is not None
            else None
        ),
        "evaluation": evaluation.model_dump(mode="json") if evaluation is not None else None,
        "artifacts": [
            {
                "kind": artifact.kind,
                "fileName": Path(artifact.path).name,
                "sha256": artifact.sha256,
                "downloadUrl": f"/applications/{run.id}/artifacts/{artifact.kind}",
            }
            for artifact in artifacts
            if artifact.kind
            in {"resume_docx", "resume_pdf", "cover_letter_docx", "cover_letter_pdf"}
        ],
    }


def create_applications_router(
    web_repository: WebRepository,
    manager: ApplicationManager,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["applications"])

    @router.get("/application-profile")
    def get_application_profile() -> dict[str, Any]:
        settings = web_repository.settings
        try:
            profile = load_application_profile(settings.application.profile_path)
        except ApplicationProfileError:
            return {
                "ready": False,
                "verificationStatus": "missing_or_invalid",
                "message": "私有申请画像不存在或校验失败，请在本机检查 application.profile_path",
            }
        payload = profile_summary(profile)
        return {
            "ready": payload["verificationStatus"] == "confirmed",
            **payload,
        }

    @router.get("/applications")
    def list_applications() -> list[dict[str, Any]]:
        repository = _repository(manager)
        return [
            _application_json(repository, run, active=manager.is_active(run.id))
            for run in repository.list_runs(limit=200)
        ]

    @router.get("/applications/{application_id}")
    def get_application(application_id: str) -> dict[str, Any]:
        repository = _repository(manager)
        run = repository.get_run(application_id)
        if run is None:
            raise HTTPException(404, "申请任务不存在")
        return _application_json(repository, run, active=manager.is_active(run.id))

    @router.get("/jobs/{job_id}/applications")
    def list_job_applications(job_id: str) -> list[dict[str, Any]]:
        repository = _repository(manager)
        return [
            _application_json(repository, run, active=manager.is_active(run.id))
            for run in repository.list_runs(job_id=job_id, limit=50)
        ]

    @router.post("/jobs/{job_id}/applications", status_code=202)
    def create_application(job_id: str) -> dict[str, Any]:
        try:
            run = manager.create(job_id)
        except ApplicationConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"ok": True, "applicationId": run.id}

    @router.post("/applications/{application_id}/approve", status_code=202)
    def approve_application(application_id: str) -> dict[str, Any]:
        try:
            run = manager.approve(application_id)
        except ApplicationConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"ok": True, "applicationId": run.id}

    @router.post("/applications/{application_id}/resume", status_code=202)
    def resume_application(application_id: str) -> dict[str, Any]:
        try:
            run = manager.resume(application_id)
        except ApplicationConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"ok": True, "applicationId": run.id}

    @router.post("/applications/{application_id}/render", status_code=202)
    def render_application(application_id: str) -> dict[str, Any]:
        try:
            run = manager.render(application_id)
        except ApplicationConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"ok": True, "applicationId": run.id}

    @router.post("/applications/{application_id}/reject")
    def reject_application(application_id: str) -> dict[str, Any]:
        try:
            run = manager.reject(application_id)
        except ApplicationConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"ok": True, "applicationId": run.id}

    @router.get("/applications/{application_id}/artifacts/{kind}")
    def download_artifact(application_id: str, kind: str):  # type: ignore[no-untyped-def]
        allowed = {
            "resume_docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "resume_pdf": "application/pdf",
            "cover_letter_docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "cover_letter_pdf": "application/pdf",
        }
        if kind not in allowed:
            raise HTTPException(404, "申请材料文件不存在")
        repository = _repository(manager)
        run = repository.get_run(application_id)
        if run is None:
            raise HTTPException(404, "申请任务不存在")
        artifact = next(
            (item for item in repository.list_artifacts(application_id) if item.kind == kind),
            None,
        )
        if artifact is None:
            raise HTTPException(404, "申请材料文件不存在")
        root = web_repository.settings.application.output_dir.expanduser().resolve()
        path = Path(artifact.path).expanduser().resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(409, "申请材料文件路径无效或文件已丢失")
        if file_sha256(path) != artifact.sha256:
            raise HTTPException(409, "申请材料文件已被外部修改，请重新生成或验证")
        return FileResponse(
            path,
            media_type=allowed[kind],
            filename=path.name,
        )

    return router
