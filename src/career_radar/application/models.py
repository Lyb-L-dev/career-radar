"""申请材料领域模型和状态迁移规则。"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApplicationConfig(BaseModel):
    """申请工作流的私有文件路径与默认输出策略。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    profile_path: Path = Path("private/application_profile.yaml")
    output_dir: Path = Path("private/application_outputs")
    resume_template_path: Path = Path("private/master_resume.docx")
    default_resume_pages: int = Field(default=1, ge=1, le=3)
    cover_letter_mode: Literal["auto", "always", "never"] = "auto"
    pdf_mode: Literal["auto", "always", "never"] = "auto"
    libreoffice_command: str = Field(default="soffice", min_length=1, max_length=500)


class ProfileVerificationStatus(str, Enum):
    """私有画像是否已由用户核对。"""

    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"


class ProfileSource(BaseModel):
    """画像事实的来源；路径只保存在 gitignored 私有文件中。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    kind: Literal["resume_docx", "career_radar_profile", "user_confirmed"]
    path: str | None = None
    imported_at: str
    visually_verified: bool = False
    note: str | None = None


class ContactProfile(BaseModel):
    """生成材料所需的身份和联系方式，不会并入公开候选人画像。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=5, max_length=40)
    email: str = Field(min_length=3, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    github: str | None = Field(default=None, max_length=500)
    linkedin: str | None = Field(default=None, max_length=500)


class EducationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str
    degree: str
    major: str
    start_date: str
    end_date: str
    gpa: str | None = None
    courses: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ExperienceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    role: str
    start_date: str
    end_date: str
    location: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ProjectProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    start_date: str | None = None
    end_date: str | None = None
    description: str
    responsibilities: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class SkillProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    level: Literal["了解", "熟悉", "熟练"]
    evidence: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class AwardProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    period: str | None = None
    source_ids: list[str] = Field(default_factory=list)


class LeadershipProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    organization: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    details: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ApplicationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    accepted_work_types: list[str] = Field(default_factory=lambda: ["校招", "实习"])
    accept_relocation: bool = True
    cover_letter_mode: Literal["auto", "always", "never"] | None = None
    resume_page_target: int | None = Field(default=None, ge=1, le=3)
    constraints: list[str] = Field(default_factory=list)
    excluded_directions: list[str] = Field(default_factory=list)


class ApplicationProfile(BaseModel):
    """生成申请材料的完整私有事实库。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    verification_status: ProfileVerificationStatus = ProfileVerificationStatus.NEEDS_REVIEW
    contact: ContactProfile
    education: list[EducationProfile] = Field(default_factory=list)
    experiences: list[ExperienceProfile] = Field(default_factory=list)
    projects: list[ProjectProfile] = Field(default_factory=list)
    skills: list[SkillProfile] = Field(default_factory=list)
    awards: list[AwardProfile] = Field(default_factory=list)
    leadership: list[LeadershipProfile] = Field(default_factory=list)
    preferences: ApplicationPreferences = Field(default_factory=ApplicationPreferences)
    sources: list[ProfileSource] = Field(min_length=1)
    review_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_references(self) -> ApplicationProfile:
        """所有事实来源必须指向已声明来源，避免产生无法追溯的简历内容。"""

        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("申请画像 sources.id 不能重复")
        known = set(source_ids)
        items = [
            *self.education,
            *self.experiences,
            *self.projects,
            *self.skills,
            *self.awards,
            *self.leadership,
        ]
        for item in items:
            unknown = set(item.source_ids) - known
            if unknown:
                raise ValueError(f"申请画像引用了未知来源：{sorted(unknown)[0]}")
        return self

    def content_hash(self) -> str:
        """生成稳定画像哈希，用于证明某次申请采用了哪个事实版本。"""

        payload = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ApplicationStatus(str, Enum):
    CREATED = "created"
    EVALUATING = "evaluating"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    DRAFTING = "drafting"
    FACTUAL_REVIEW = "factual_review"
    RECRUITER_REVIEW = "recruiter_review"
    REVISING = "revising"
    RENDERING = "rendering"
    VERIFYING = "verifying"
    READY = "ready"
    REJECTED = "rejected"
    FAILED = "failed"


APPLICATION_STATUS_PROGRESS: dict[ApplicationStatus, int] = {
    ApplicationStatus.CREATED: 5,
    ApplicationStatus.EVALUATING: 15,
    ApplicationStatus.WAITING_FOR_APPROVAL: 25,
    ApplicationStatus.DRAFTING: 40,
    ApplicationStatus.FACTUAL_REVIEW: 55,
    ApplicationStatus.RECRUITER_REVIEW: 65,
    ApplicationStatus.REVISING: 75,
    ApplicationStatus.RENDERING: 85,
    ApplicationStatus.VERIFYING: 95,
    ApplicationStatus.READY: 100,
    ApplicationStatus.REJECTED: 100,
    ApplicationStatus.FAILED: 0,
}


WORKFLOW_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.CREATED: {ApplicationStatus.EVALUATING, ApplicationStatus.REJECTED},
    ApplicationStatus.EVALUATING: {
        ApplicationStatus.WAITING_FOR_APPROVAL,
        ApplicationStatus.FAILED,
    },
    ApplicationStatus.WAITING_FOR_APPROVAL: {
        ApplicationStatus.DRAFTING,
        ApplicationStatus.REJECTED,
    },
    ApplicationStatus.DRAFTING: {
        ApplicationStatus.FACTUAL_REVIEW,
        ApplicationStatus.FAILED,
    },
    ApplicationStatus.FACTUAL_REVIEW: {
        ApplicationStatus.RECRUITER_REVIEW,
        ApplicationStatus.FAILED,
    },
    ApplicationStatus.RECRUITER_REVIEW: {
        ApplicationStatus.REVISING,
        ApplicationStatus.FAILED,
    },
    ApplicationStatus.REVISING: {
        ApplicationStatus.RENDERING,
        ApplicationStatus.FAILED,
    },
    ApplicationStatus.RENDERING: {
        ApplicationStatus.VERIFYING,
        ApplicationStatus.FAILED,
    },
    ApplicationStatus.VERIFYING: {
        ApplicationStatus.READY,
        ApplicationStatus.FAILED,
    },
    ApplicationStatus.READY: set(),
    ApplicationStatus.REJECTED: set(),
    ApplicationStatus.FAILED: set(),
}


def validate_status_transition(current: ApplicationStatus, target: ApplicationStatus) -> None:
    """拒绝跳过审批或审稿步骤的非法状态变化。"""

    if target not in WORKFLOW_TRANSITIONS[current]:
        raise ValueError(f"不允许申请任务从 {current.value} 进入 {target.value}")


class ApplicationRun(BaseModel):
    """一次岗位申请材料任务的非敏感运行摘要。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    job_id: str
    job_content_hash: str
    profile_hash: str
    status: ApplicationStatus = ApplicationStatus.CREATED
    failed_step: ApplicationStatus | None = None
    error: str | None = None
    cover_letter_mode: Literal["auto", "always", "never"] = "auto"
    resume_page_target: int = Field(default=1, ge=1, le=3)
    created_at: str
    updated_at: str
    approved_at: str | None = None
    completed_at: str | None = None


class EligibilityCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    verdict: Literal["pass", "fail", "unknown"]
    reason: str
    evidence: str | None = None


class FitDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["skills", "projects_experience", "education_graduation", "career", "logistics"]
    score: int = Field(ge=0, le=100)
    weight: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class RequirementCoverage(BaseModel):
    """JD 单项要求与画像证据之间的可审计对应关系。"""

    model_config = ConfigDict(extra="forbid")

    requirement: str
    priority: Literal["required", "preferred", "unknown"] = "unknown"
    status: Literal["matched", "partial", "gap", "unknown"]
    candidate_evidence: list[str] = Field(default_factory=list)
    honest_bridge: str | None = None


class JobFitEvaluation(BaseModel):
    """第二阶段 DeepSeek 必须返回的结构化岗位评估契约。"""

    model_config = ConfigDict(extra="forbid")

    eligibility: list[EligibilityCheck] = Field(default_factory=list)
    dimensions: list[FitDimension] = Field(min_length=5, max_length=5)
    overall_score: int = Field(ge=0, le=100)
    difficulty_score: int = Field(ge=1, le=10)
    verdict: Literal["strong", "good", "moderate", "weak", "ineligible"]
    recommendation: str
    requirement_coverage: list[RequirementCoverage] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_all_dimensions(self) -> JobFitEvaluation:
        expected = {"skills", "projects_experience", "education_graduation", "career", "logistics"}
        actual = {item.name for item in self.dimensions}
        if actual != expected or len(self.dimensions) != len(actual):
            raise ValueError("岗位评估必须包含五个不重复的固定维度")
        return self


class SourcedTextDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    source_ids: list[str] = Field(min_length=1)


class ResumeEducationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str
    degree: str
    major: str
    period: str
    highlights: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(min_length=1)


class ResumeExperienceDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    role: str
    period: str
    location: str | None = None
    bullets: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(min_length=1)


class ResumeProjectDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    period: str | None = None
    summary: str
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(min_length=1)


class ResumeDraft(BaseModel):
    """不含联系方式的简历正文，联系方式仅在文档渲染阶段本地注入。"""

    model_config = ConfigDict(extra="forbid")

    headline: str
    professional_summary: str
    skills: list[SourcedTextDraft] = Field(default_factory=list)
    education: list[ResumeEducationDraft] = Field(default_factory=list)
    experiences: list[ResumeExperienceDraft] = Field(default_factory=list)
    projects: list[ResumeProjectDraft] = Field(default_factory=list)
    awards: list[SourcedTextDraft] = Field(default_factory=list)
    leadership: list[SourcedTextDraft] = Field(default_factory=list)
    omitted_items: list[str] = Field(default_factory=list)
    grounding_warnings: list[str] = Field(default_factory=list)


class CoverLetterDraft(BaseModel):
    """中文求职信正文；不允许模型填写候选人联系方式。"""

    model_config = ConfigDict(extra="forbid")

    subject: str
    salutation: str
    paragraphs: list[str] = Field(min_length=2, max_length=8)
    closing: str
    requirement_bridges: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(min_length=1)


class ApplicationDraftBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume: ResumeDraft
    cover_letter: CoverLetterDraft | None = None


class DraftDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["resume", "cover_letter"]
    version: int = Field(ge=1)
    content: str
    grounded_source_ids: list[str] = Field(default_factory=list)


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["info", "warning", "error"]
    category: Literal["grounding", "requirement", "ats", "style", "company_claim", "layout"]
    document_kind: Literal["resume", "cover_letter", "both"]
    message: str
    suggested_change: str | None = None
    source_ids: list[str] = Field(default_factory=list)


class ApplicationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: Literal["factual", "recruiter_ats"]
    passed: bool
    findings: list[ReviewFinding] = Field(default_factory=list)
    summary: str


class ApplicationArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    application_id: str
    kind: Literal["evaluation", "resume_docx", "resume_pdf", "cover_letter_docx", "cover_letter_pdf", "review_report", "verification"]
    path: str
    sha256: str
    created_at: str


class VerificationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["warning", "error"]
    code: str
    document_kind: Literal["resume", "cover_letter", "all"]
    message: str


class DocumentVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_kind: Literal["resume", "cover_letter"]
    docx_sha256: str
    docx_bytes: int = Field(ge=1)
    pdf_sha256: str | None = None
    pdf_bytes: int | None = Field(default=None, ge=1)
    pdf_page_count: int | None = Field(default=None, ge=1)
    expected_text_checks: int = Field(ge=0)
    issues: list[VerificationIssue] = Field(default_factory=list)


class ApplicationVerification(BaseModel):
    """文档结构、文本完整性和可用 PDF 页数的本地校验报告。"""

    model_config = ConfigDict(extra="forbid")

    application_id: str
    passed: bool
    documents: list[DocumentVerification] = Field(min_length=1)
    generated_at: str
