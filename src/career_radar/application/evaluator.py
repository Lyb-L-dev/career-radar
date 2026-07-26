"""岗位匹配评估：模型负责判断，程序固定权重并重算总分。"""

from __future__ import annotations

from ..models import JobPosting
from .context import job_llm_context
from .llm import ApplicationLLMGateway
from .models import ApplicationProfile, JobFitEvaluation
from .profile import profile_llm_context
from .prompts import load_prompt, prompt_payload

DIMENSION_WEIGHTS = {
    "skills": 30,
    "projects_experience": 25,
    "education_graduation": 20,
    "career": 15,
    "logistics": 10,
}


def _verdict(score: int, ineligible: bool) -> str:
    if ineligible:
        return "ineligible"
    if score >= 75:
        return "strong"
    if score >= 60:
        return "good"
    if score >= 45:
        return "moderate"
    return "weak"


class JobApplicationEvaluator:
    """执行一次隔离的岗位分析调用，并确定性规范化评分。"""

    def __init__(self, gateway: ApplicationLLMGateway) -> None:
        self.gateway = gateway

    def evaluate(self, job: JobPosting, profile: ApplicationProfile) -> JobFitEvaluation:
        result = self.gateway.generate(
            JobFitEvaluation,
            load_prompt("evaluate_zh"),
            prompt_payload(
                task="评估岗位与候选人的匹配程度，不生成申请材料",
                untrusted_job_snapshot=job_llm_context(job),
                deidentified_candidate_facts=profile_llm_context(profile),
                fixed_dimension_weights=DIMENSION_WEIGHTS,
            ),
        )
        normalized_dimensions = [
            item.model_copy(update={"weight": DIMENSION_WEIGHTS[item.name]})
            for item in result.dimensions
        ]
        overall_score = round(
            sum(item.score * DIMENSION_WEIGHTS[item.name] for item in normalized_dimensions)
            / 100
        )
        ineligible = any(item.verdict == "fail" for item in result.eligibility)
        return result.model_copy(
            update={
                "dimensions": normalized_dimensions,
                "overall_score": overall_score,
                "verdict": _verdict(overall_score, ineligible),
            }
        )
