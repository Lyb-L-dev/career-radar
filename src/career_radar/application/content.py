"""简历/求职信生成、双重独立审查与终稿修订。"""

from __future__ import annotations

import re

from ..models import JobPosting
from .context import job_llm_context
from .llm import ApplicationLLMGateway
from .models import (
    ApplicationDraftBundle,
    ApplicationProfile,
    ApplicationReview,
    CoverLetterDraft,
    JobFitEvaluation,
    ResumeDraft,
)
from .profile import profile_llm_context
from .prompts import load_prompt, prompt_payload

_COVER_LETTER_PATTERN = re.compile(
    r"求职信|申请信|动机信|cover\s*letter|motivation\s*letter",
    re.IGNORECASE,
)


def should_generate_cover_letter(mode: str, job: JobPosting) -> bool:
    """auto 仅在 JD 明确要求求职信时生成，避免无意义增加费用。"""

    if mode == "always":
        return True
    if mode == "never":
        return False
    text = "\n".join(filter(None, [job.description, job.requirements, job.application_method]))
    return bool(_COVER_LETTER_PATTERN.search(text))


def _assert_known_sources(bundle: ApplicationDraftBundle, profile: ApplicationProfile) -> None:
    """拒绝任何引用画像之外来源的草稿，作为模型审查之外的硬护栏。"""

    known = {source.id for source in profile.sources}
    referenced: set[str] = set()
    resume = bundle.resume
    for item in [*resume.skills, *resume.awards, *resume.leadership]:
        referenced.update(item.source_ids)
    for item in [*resume.education, *resume.experiences, *resume.projects]:
        referenced.update(item.source_ids)
    if bundle.cover_letter is not None:
        referenced.update(bundle.cover_letter.source_ids)
    unknown = referenced - known
    if unknown:
        raise ValueError(f"申请草稿引用了未知画像来源：{sorted(unknown)[0]}")


def _normalize_review(review: ApplicationReview, reviewer: str) -> ApplicationReview:
    """只要存在 error 就不能通过；模型的 passed 只能更保守，不能覆盖错误。"""

    has_error = any(finding.severity == "error" for finding in review.findings)
    return review.model_copy(
        update={"reviewer": reviewer, "passed": review.passed and not has_error}
    )


class ApplicationContentGenerator:
    """每个阶段发起独立调用，避免生成器自我批准。"""

    def __init__(self, gateway: ApplicationLLMGateway) -> None:
        self.gateway = gateway

    def draft(
        self,
        job: JobPosting,
        profile: ApplicationProfile,
        evaluation: JobFitEvaluation,
        *,
        cover_letter_mode: str,
        resume_page_target: int,
    ) -> ApplicationDraftBundle:
        common = {
            "untrusted_job_snapshot": job_llm_context(job),
            "deidentified_candidate_facts": profile_llm_context(profile),
            "job_fit_evaluation": evaluation.model_dump(mode="json"),
        }
        resume = self.gateway.generate(
            ResumeDraft,
            load_prompt("resume_zh"),
            prompt_payload(
                task="生成简历初稿",
                resume_page_target=resume_page_target,
                **common,
            ),
        )
        cover_letter = None
        if should_generate_cover_letter(cover_letter_mode, job):
            cover_letter = self.gateway.generate(
                CoverLetterDraft,
                load_prompt("cover_letter_zh"),
                prompt_payload(task="生成求职信初稿", **common),
            )
        bundle = ApplicationDraftBundle(resume=resume, cover_letter=cover_letter)
        _assert_known_sources(bundle, profile)
        return bundle

    def factual_review(
        self,
        profile: ApplicationProfile,
        drafts: ApplicationDraftBundle,
    ) -> ApplicationReview:
        result = self.gateway.generate(
            ApplicationReview,
            load_prompt("factual_review_zh"),
            prompt_payload(
                task="独立核对初稿中的每项候选人事实",
                deidentified_candidate_facts=profile_llm_context(profile),
                untrusted_application_drafts=drafts.model_dump(mode="json"),
            ),
        )
        return _normalize_review(result, "factual")

    def recruiter_review(
        self,
        job: JobPosting,
        evaluation: JobFitEvaluation,
        drafts: ApplicationDraftBundle,
    ) -> ApplicationReview:
        result = self.gateway.generate(
            ApplicationReview,
            load_prompt("recruiter_review_zh"),
            prompt_payload(
                task="独立评估招聘官可读性与 ATS 匹配",
                untrusted_job_snapshot=job_llm_context(job),
                job_fit_evaluation=evaluation.model_dump(mode="json"),
                untrusted_application_drafts=drafts.model_dump(mode="json"),
            ),
        )
        return _normalize_review(result, "recruiter_ats")

    def revise(
        self,
        job: JobPosting,
        profile: ApplicationProfile,
        drafts: ApplicationDraftBundle,
        factual_review: ApplicationReview,
        recruiter_review: ApplicationReview,
        *,
        resume_page_target: int,
    ) -> ApplicationDraftBundle:
        result = self.gateway.generate(
            ApplicationDraftBundle,
            load_prompt("revise_zh"),
            prompt_payload(
                task="根据两份独立审查生成材料终稿",
                resume_page_target=resume_page_target,
                untrusted_job_snapshot=job_llm_context(job),
                deidentified_candidate_facts=profile_llm_context(profile),
                untrusted_initial_drafts=drafts.model_dump(mode="json"),
                factual_review=factual_review.model_dump(mode="json"),
                recruiter_ats_review=recruiter_review.model_dump(mode="json"),
            ),
        )
        if drafts.cover_letter is None and result.cover_letter is not None:
            raise ValueError("修订阶段不得新增未经批准生成的求职信")
        if drafts.cover_letter is not None and result.cover_letter is None:
            raise ValueError("修订阶段意外丢失求职信")
        _assert_known_sources(result, profile)
        return result
