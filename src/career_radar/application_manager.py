"""在 FastAPI 进程内串行执行申请评估、材料生成和文档渲染。"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from .application.content import ApplicationContentGenerator
from .application.document_renderer import ApplicationDocumentRenderer
from .application.document_verifier import ApplicationDocumentVerifier
from .application.document_workflow import ApplicationDocumentWorkflow
from .application.evaluator import JobApplicationEvaluator
from .application.llm import DeepSeekApplicationGateway
from .application.models import ApplicationRun, ApplicationStatus
from .application.repository import ApplicationRepository
from .application.service import ApplicationService
from .application.workflow import ApplicationWorkflow
from .web_repository import WebRepository

LOGGER = logging.getLogger(__name__)


class ApplicationConflictError(RuntimeError):
    """同一申请任务已经在当前 API 进程中执行。"""


class ApplicationManager:
    """后台单线程管理器，避免多次点击造成重复 LLM 调用和文件竞争。"""

    def __init__(self, web_repository: WebRepository) -> None:
        self.web_repository = web_repository
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="career-radar-application",
        )
        self._lock = threading.Lock()
        self._active_ids: set[str] = set()
        self._recover_orphaned_runs()

    def _recover_orphaned_runs(self) -> None:
        """API 重启后把旧进程遗留的执行中状态转成可恢复失败。"""

        _settings, repository, service = self._dependencies()
        running_statuses = {
            ApplicationStatus.EVALUATING,
            ApplicationStatus.DRAFTING,
            ApplicationStatus.FACTUAL_REVIEW,
            ApplicationStatus.RECRUITER_REVIEW,
            ApplicationStatus.REVISING,
            ApplicationStatus.RENDERING,
            ApplicationStatus.VERIFYING,
        }
        for run in repository.list_runs(limit=1_000):
            if run.status in running_statuses:
                repository.mark_failed(
                    run.id,
                    "本地 API 进程在任务执行中重启，请从已保存的失败步骤恢复",
                    service.now(),
                )

    def _dependencies(self):
        settings = self.web_repository.settings
        repository = ApplicationRepository(settings.app.database_path)
        repository.initialize()
        service = ApplicationService(repository, settings.application, settings.app.timezone)
        return settings, repository, service

    def repository(self) -> ApplicationRepository:
        settings = self.web_repository.settings
        repository = ApplicationRepository(settings.app.database_path)
        repository.initialize()
        return repository

    def is_active(self, application_id: str) -> bool:
        """判断任务是否正在当前 API 进程的后台线程中执行。"""

        with self._lock:
            return application_id in self._active_ids

    def _application_workflow(
        self,
        settings,
        repository: ApplicationRepository,
    ) -> ApplicationWorkflow:
        gateway = DeepSeekApplicationGateway(settings.llm)
        return ApplicationWorkflow(
            repository,
            JobApplicationEvaluator(gateway),
            ApplicationContentGenerator(gateway),
            settings.app.timezone,
        )

    @staticmethod
    def _document_workflow(settings, repository: ApplicationRepository):
        return ApplicationDocumentWorkflow(
            repository,
            ApplicationDocumentRenderer(settings.application),
            ApplicationDocumentVerifier(settings.application),
            settings.app.timezone,
        )

    def _submit(self, application_id: str, action: str) -> None:
        with self._lock:
            if application_id in self._active_ids:
                raise ApplicationConflictError("该申请任务正在执行，请勿重复操作")
            self._active_ids.add(application_id)
        try:
            self._executor.submit(self._execute, application_id, action)
        except Exception:
            with self._lock:
                self._active_ids.discard(application_id)
            raise

    def create(self, job_id: str) -> ApplicationRun:
        _settings, repository, service = self._dependencies()
        snapshot = repository.get_job_snapshot(job_id)
        if snapshot is None:
            raise ValueError("岗位不存在，无法创建申请任务")
        _content_hash, job = snapshot
        if job.record_type != "job":
            raise ValueError("招聘公告不是具体岗位，暂不能生成定制申请材料")
        if not job.jd_complete:
            raise ValueError("该岗位的 JD 尚不完整，请先获取详情页后再生成申请材料")
        existing = repository.list_runs(job_id=job_id, limit=20)
        blocking = next(
            (
                run
                for run in existing
                if run.status
                not in {
                    ApplicationStatus.READY,
                    ApplicationStatus.REJECTED,
                    ApplicationStatus.FAILED,
                }
            ),
            None,
        )
        if blocking is not None:
            raise ApplicationConflictError(
                f"该岗位已有未结束的申请任务：{blocking.id}"
            )
        run = service.create(job_id)
        run = service.transition(run.id, ApplicationStatus.EVALUATING)
        self._submit(run.id, "evaluate")
        return run

    def approve(self, application_id: str) -> ApplicationRun:
        _settings, _repository, service = self._dependencies()
        run = service.get(application_id)
        if run.status != ApplicationStatus.WAITING_FOR_APPROVAL:
            raise ValueError("只有等待批准的任务才能生成申请材料")
        run = service.transition(application_id, ApplicationStatus.DRAFTING)
        self._submit(application_id, "content")
        return run

    def render(self, application_id: str) -> ApplicationRun:
        _settings, _repository, service = self._dependencies()
        run = service.get(application_id)
        if run.status not in {ApplicationStatus.RENDERING, ApplicationStatus.VERIFYING}:
            raise ValueError("当前任务没有等待渲染或验证的终稿")
        self._submit(application_id, "document")
        return run

    def resume(self, application_id: str) -> ApplicationRun:
        _settings, repository, service = self._dependencies()
        run = service.get(application_id)
        if run.status == ApplicationStatus.FAILED:
            run = repository.resume_failed(application_id, service.now())
        if run.status in {
            ApplicationStatus.CREATED,
            ApplicationStatus.EVALUATING,
        }:
            action = "evaluate"
        elif run.status in {
            ApplicationStatus.DRAFTING,
            ApplicationStatus.FACTUAL_REVIEW,
            ApplicationStatus.RECRUITER_REVIEW,
            ApplicationStatus.REVISING,
        }:
            action = "content"
        elif run.status in {ApplicationStatus.RENDERING, ApplicationStatus.VERIFYING}:
            action = "document"
        else:
            raise ValueError(f"状态 {run.status.value} 不能恢复")
        self._submit(application_id, action)
        return run

    def reject(self, application_id: str) -> ApplicationRun:
        with self._lock:
            if application_id in self._active_ids:
                raise ApplicationConflictError("任务正在执行，不能拒绝")
        _settings, _repository, service = self._dependencies()
        return service.reject(application_id)

    def _mark_unhandled_failure(
        self,
        repository: ApplicationRepository,
        application_id: str,
        exc: Exception,
        timezone: str,
    ) -> None:
        run = repository.get_run(application_id)
        if run is None or run.status not in {
            ApplicationStatus.EVALUATING,
            ApplicationStatus.DRAFTING,
            ApplicationStatus.FACTUAL_REVIEW,
            ApplicationStatus.RECRUITER_REVIEW,
            ApplicationStatus.REVISING,
            ApplicationStatus.RENDERING,
            ApplicationStatus.VERIFYING,
        }:
            return
        service = ApplicationService(repository, self.web_repository.settings.application, timezone)
        repository.mark_failed(application_id, str(exc), service.now())

    def _execute(self, application_id: str, action: str) -> None:
        settings = None
        repository = None
        try:
            settings, repository, _service = self._dependencies()
            if action == "evaluate":
                self._application_workflow(settings, repository).evaluate(application_id)
            elif action == "content":
                run = self._application_workflow(settings, repository).resume(application_id)
                if run.status == ApplicationStatus.RENDERING:
                    self._document_workflow(settings, repository).run(application_id)
            elif action == "document":
                self._document_workflow(settings, repository).run(application_id)
            else:
                raise ValueError(f"未知申请后台动作：{action}")
        except Exception as exc:
            LOGGER.exception("申请任务后台执行失败：%s", application_id)
            if settings is not None and repository is not None:
                try:
                    self._mark_unhandled_failure(
                        repository,
                        application_id,
                        exc,
                        settings.app.timezone,
                    )
                except Exception:
                    LOGGER.exception("申请任务失败状态写入失败：%s", application_id)
        finally:
            with self._lock:
                self._active_ids.discard(application_id)
