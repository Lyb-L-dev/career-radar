"""申请任务用例层；第一阶段不访问 LLM。"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from .models import (
    ApplicationConfig,
    ApplicationRun,
    ApplicationStatus,
    ProfileVerificationStatus,
)
from .profile import load_application_profile
from .repository import ApplicationRepository


class ApplicationService:
    """协调岗位快照、私有画像和可恢复状态机。"""

    def __init__(
        self,
        repository: ApplicationRepository,
        config: ApplicationConfig,
        timezone: str,
    ) -> None:
        self.repository = repository
        self.config = config
        self.timezone = timezone

    def now(self) -> str:
        """返回统一时区的任务时间，供 API 后台管理器复用。"""

        return datetime.now(ZoneInfo(self.timezone)).isoformat(timespec="seconds")

    def create(self, job_id: str) -> ApplicationRun:
        """冻结岗位和画像事实，建立尚未进行 LLM 评估的任务。"""

        if not self.config.enabled:
            raise ValueError("申请材料功能已在配置中关闭")
        self.repository.initialize()
        snapshot = self.repository.get_job_snapshot(job_id)
        if snapshot is None:
            raise ValueError("岗位不存在，无法创建申请任务")
        job_content_hash, job = snapshot
        if job.record_type != "job":
            raise ValueError("招聘公告不是具体岗位，暂不能生成定制申请材料")
        if not job.jd_complete:
            raise ValueError("该岗位的 JD 尚不完整，请先获取详情页后再生成申请材料")
        profile_path = self.config.profile_path.expanduser().resolve()
        profile = load_application_profile(profile_path)
        if profile.verification_status != ProfileVerificationStatus.CONFIRMED:
            raise ValueError(
                "私有申请画像尚未确认；请核对后把 verification_status 改为 confirmed"
            )
        now = self.now()
        application_id = f"app-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
        run = ApplicationRun(
            id=application_id,
            job_id=job_id,
            job_content_hash=job_content_hash,
            profile_hash=profile.content_hash(),
            cover_letter_mode=(
                profile.preferences.cover_letter_mode or self.config.cover_letter_mode
            ),
            resume_page_target=(
                profile.preferences.resume_page_target or self.config.default_resume_pages
            ),
            created_at=now,
            updated_at=now,
        )
        return self.repository.create_run(run, job, profile, str(profile_path))

    def get(self, application_id: str) -> ApplicationRun:
        run = self.repository.get_run(application_id)
        if run is None:
            raise ValueError("申请任务不存在")
        return run

    def transition(self, application_id: str, target: ApplicationStatus) -> ApplicationRun:
        return self.repository.transition(application_id, target, self.now())

    def reject(self, application_id: str) -> ApplicationRun:
        run = self.get(application_id)
        if run.status not in {
            ApplicationStatus.CREATED,
            ApplicationStatus.WAITING_FOR_APPROVAL,
        }:
            raise ValueError("只能拒绝尚未开始生成材料的申请任务")
        return self.repository.transition(application_id, ApplicationStatus.REJECTED, self.now())

    def resume(self, application_id: str) -> ApplicationRun:
        return self.repository.resume_failed(application_id, self.now())

    @staticmethod
    def public_json(run: ApplicationRun) -> dict[str, object]:
        """运行摘要不包含岗位正文、画像内容或任何联系方式。"""

        payload = run.model_dump(mode="json")
        if payload.get("error"):
            # Provider/文档工具的原始异常可能包含输入片段，只在本机数据库保存。
            payload["error"] = "申请任务执行失败，请查看本机日志或从失败步骤恢复"
        payload["nextAction"] = {
            ApplicationStatus.CREATED.value: "等待岗位匹配评估",
            ApplicationStatus.WAITING_FOR_APPROVAL.value: "等待用户批准生成申请材料",
            ApplicationStatus.FAILED.value: "修复错误后从失败步骤恢复",
            ApplicationStatus.RENDERING.value: "内容已通过双审，等待生成 DOCX/PDF",
            ApplicationStatus.VERIFYING.value: "文档已生成，等待完整性和页数校验",
            ApplicationStatus.READY.value: "人工审核生成文件后再前往官网投递",
        }.get(run.status.value, "由申请工作流继续处理")
        return payload
