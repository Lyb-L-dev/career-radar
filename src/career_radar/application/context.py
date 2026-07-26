"""申请工作流的最小化、不含联系方式的模型上下文。"""

from __future__ import annotations

from ..models import JobPosting


def job_llm_context(job: JobPosting) -> dict[str, object]:
    """保留岗位事实，移除投递邮箱和 URL，模型不需要也不应访问这些字段。"""

    return {
        "record_type": job.record_type,
        "company": job.company,
        "title": job.title,
        "location": job.location,
        "description": job.description,
        "requirements": job.requirements,
        "recruitment_type": job.recruitment_type,
        "is_2026_target": job.is_2026_target,
        "target_graduates": job.target_graduates,
        "published_at": job.published_at,
        "valid_until": job.valid_until,
        "jd_complete": job.jd_complete,
        "jd_incomplete_reason": job.jd_incomplete_reason,
    }
