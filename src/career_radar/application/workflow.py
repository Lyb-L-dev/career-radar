"""可恢复的申请内容工作流；每个阶段完成后立即持久化。"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .content import ApplicationContentGenerator
from .evaluator import JobApplicationEvaluator
from .models import ApplicationRun, ApplicationStatus
from .prompts import PROMPT_VERSION
from .repository import ApplicationRepository

LOGGER = logging.getLogger(__name__)


class ApplicationWorkflow:
    """执行评估、审批后的生成、双审和修订，不负责文档渲染或投递。"""

    def __init__(
        self,
        repository: ApplicationRepository,
        evaluator: JobApplicationEvaluator,
        generator: ApplicationContentGenerator,
        timezone: str,
    ) -> None:
        self.repository = repository
        self.evaluator = evaluator
        self.generator = generator
        self.timezone = timezone

    def _now(self) -> str:
        return datetime.now(ZoneInfo(self.timezone)).isoformat(timespec="seconds")

    def _context(self, application_id: str):
        run = self.repository.get_run(application_id)
        job = self.repository.get_run_job_snapshot(application_id)
        profile = self.repository.get_profile_snapshot(application_id)
        if run is None or job is None or profile is None:
            raise ValueError("申请任务或其冻结快照不完整")
        return run, job, profile

    def _fail(self, application_id: str, exc: Exception) -> ApplicationRun:
        LOGGER.exception("申请任务 %s 在当前步骤失败", application_id)
        return self.repository.mark_failed(application_id, str(exc), self._now())

    def evaluate(self, application_id: str) -> ApplicationRun:
        run = self.repository.get_run(application_id)
        if run is None:
            raise ValueError("申请任务不存在")
        if run.status == ApplicationStatus.CREATED:
            run = self.repository.transition(
                application_id, ApplicationStatus.EVALUATING, self._now()
            )
        if run.status != ApplicationStatus.EVALUATING:
            raise ValueError("只有 created/evaluating 状态可以执行岗位评估")
        try:
            _run, job, profile = self._context(application_id)
            evaluation = self.repository.get_evaluation(application_id)
            if evaluation is None:
                evaluation = self.evaluator.evaluate(job, profile)
                self.repository.save_evaluation(
                    application_id, evaluation, PROMPT_VERSION, self._now()
                )
            return self.repository.transition(
                application_id, ApplicationStatus.WAITING_FOR_APPROVAL, self._now()
            )
        except Exception as exc:
            return self._fail(application_id, exc)

    def approve_and_generate(self, application_id: str) -> ApplicationRun:
        run = self.repository.get_run(application_id)
        if run is None:
            raise ValueError("申请任务不存在")
        if run.status != ApplicationStatus.WAITING_FOR_APPROVAL:
            raise ValueError("只有完成评估并等待批准的任务才能生成材料")
        self.repository.transition(application_id, ApplicationStatus.DRAFTING, self._now())
        return self._continue_content(application_id)

    def _continue_content(self, application_id: str) -> ApplicationRun:
        try:
            while True:
                run, job, profile = self._context(application_id)
                evaluation = self.repository.get_evaluation(application_id)
                if evaluation is None:
                    raise ValueError("缺少岗位评估，不能生成申请材料")

                if run.status == ApplicationStatus.DRAFTING:
                    drafts = self.repository.get_draft_bundle(application_id, 1)
                    if drafts is None:
                        drafts = self.generator.draft(
                            job,
                            profile,
                            evaluation,
                            cover_letter_mode=run.cover_letter_mode,
                            resume_page_target=run.resume_page_target,
                        )
                        self.repository.save_draft_bundle(
                            application_id, drafts, 1, self._now()
                        )
                    self.repository.transition(
                        application_id, ApplicationStatus.FACTUAL_REVIEW, self._now()
                    )
                    continue

                if run.status == ApplicationStatus.FACTUAL_REVIEW:
                    drafts = self.repository.get_draft_bundle(application_id, 1)
                    if drafts is None:
                        raise ValueError("缺少简历初稿")
                    review = self.repository.get_review(application_id, "factual", 1)
                    if review is None:
                        review = self.generator.factual_review(profile, drafts)
                        self.repository.save_review(application_id, review, 1, self._now())
                    self.repository.transition(
                        application_id, ApplicationStatus.RECRUITER_REVIEW, self._now()
                    )
                    continue

                if run.status == ApplicationStatus.RECRUITER_REVIEW:
                    drafts = self.repository.get_draft_bundle(application_id, 1)
                    if drafts is None:
                        raise ValueError("缺少简历初稿")
                    review = self.repository.get_review(application_id, "recruiter_ats", 1)
                    if review is None:
                        review = self.generator.recruiter_review(job, evaluation, drafts)
                        self.repository.save_review(application_id, review, 1, self._now())
                    self.repository.transition(
                        application_id, ApplicationStatus.REVISING, self._now()
                    )
                    continue

                if run.status == ApplicationStatus.REVISING:
                    final_drafts = self.repository.get_draft_bundle(application_id, 2)
                    if final_drafts is None:
                        drafts = self.repository.get_draft_bundle(application_id, 1)
                        factual = self.repository.get_review(application_id, "factual", 1)
                        recruiter = self.repository.get_review(
                            application_id, "recruiter_ats", 1
                        )
                        if drafts is None or factual is None or recruiter is None:
                            raise ValueError("修订所需的初稿或双审结果不完整")
                        final_drafts = self.generator.revise(
                            job,
                            profile,
                            drafts,
                            factual,
                            recruiter,
                            resume_page_target=run.resume_page_target,
                        )
                        self.repository.save_draft_bundle(
                            application_id, final_drafts, 2, self._now()
                        )
                    return self.repository.transition(
                        application_id, ApplicationStatus.RENDERING, self._now()
                    )

                if run.status == ApplicationStatus.RENDERING:
                    return run
                raise ValueError(f"状态 {run.status.value} 不能继续内容生成")
        except Exception as exc:
            return self._fail(application_id, exc)

    def resume(self, application_id: str) -> ApplicationRun:
        run = self.repository.get_run(application_id)
        if run is None:
            raise ValueError("申请任务不存在")
        if run.status == ApplicationStatus.FAILED:
            run = self.repository.resume_failed(application_id, self._now())
        if run.status in {ApplicationStatus.CREATED, ApplicationStatus.EVALUATING}:
            return self.evaluate(application_id)
        if run.status == ApplicationStatus.WAITING_FOR_APPROVAL:
            return run
        if run.status in {
            ApplicationStatus.DRAFTING,
            ApplicationStatus.FACTUAL_REVIEW,
            ApplicationStatus.RECRUITER_REVIEW,
            ApplicationStatus.REVISING,
            ApplicationStatus.RENDERING,
        }:
            return self._continue_content(application_id)
        raise ValueError(f"状态 {run.status.value} 不支持恢复")
