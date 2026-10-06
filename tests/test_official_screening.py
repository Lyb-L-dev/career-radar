"""资格与能力独立判断；证据、失效和缓存必须可复核。"""

from datetime import date

import pytest

from career_radar.models import CandidateProfile, JobPosting
from career_radar.official_screening import (
    OfficialFitResult,
    _cohort_years,
    evaluate_fit,
    fit_context_hash,
    priority_view,
    qualify,
)

TODAY = date(2026, 10, 5)


def profile(**updates) -> CandidateProfile:
    return CandidateProfile(
        graduation_year=2026, graduation_month="2026-06", education_level="本科",
        education_mode="full_time", school_background="普通本科（二本），非985/211",
        student_status="graduated", formal_work_years=0, skills=["Python"],
        skill_levels={"Python": "熟悉"}, projects=["数据平台：用 Python 实现 API 和数据处理。"],
    ).model_copy(update=updates)


def job(**updates) -> JobPosting:
    return JobPosting(
        company="官网企业", title="2026届 AI 应用开发", recruitment_type="校招",
        description="Python API 开发。", requirements="本科及以上，接受应届生，无需工作经验。",
        source_url="https://example.com/jobs/1", valid_until="2026-12-31",
    ).model_copy(update=updates)


def check(result, dimension):
    return next(c for c in result.checks if c.dimension == dimension)


def test_explicit_qualification_matches_without_penalizing_ordinary_degree():
    result = qualify(job(), profile(), TODAY)
    assert result.verdict == "eligible"
    assert check(result, "degree").verdict == "met"
    assert all(c.job_quote for c in result.checks if c.required and c.verdict != "unknown")


def test_2027_cohort_and_student_requirement_are_hard_conflicts():
    result = qualify(job(title="【27校招】FDE", requirements="全日制本科在读，计算机相关专业优先。"), profile(), TODAY)
    assert result.verdict == "ineligible"
    assert check(result, "cohort").verdict == "unmet"
    assert check(result, "student").verdict == "unmet"
    assert check(result, "degree").verdict == "met"


def test_graduation_month_window_takes_precedence_over_cohort_title():
    result = qualify(job(title="2027届校招", requirements="本科及以上。毕业时间：2026年9月-2027年8月。无需工作经验。"), profile(graduation_month="2026-10"), TODAY)
    assert check(result, "cohort").verdict == "met"
    assert qualify(job(title="2027届校招", requirements="本科。毕业时间：2026年9月-2027年8月。"), profile(), TODAY).verdict == "ineligible"


def test_unknown_candidate_facts_are_not_inferred_from_graduation_year():
    result = qualify(job(title="后端实习", recruitment_type="实习", requirements="全日制本科在读。"), profile(student_status="unknown", education_mode="unknown"), TODAY)
    assert result.verdict == "review"
    assert check(result, "student").verdict == "unknown"
    assert check(result, "education_mode").verdict == "unknown"


def test_full_time_requirement_in_separate_clause_is_checked():
    result = qualify(job(requirements="本科及以上。只接受全日制学历。无需工作经验。"), profile(education_mode="part_time"), TODAY)
    assert result.verdict == "ineligible"
    assert check(result, "education_mode").verdict == "unmet"


def test_internship_not_silently_assumed_to_accept_graduates():
    result = qualify(job(title="AI 实习", recruitment_type="实习", requirements="本科及以上。"), profile(), TODAY)
    assert result.verdict == "review"
    assert check(result, "student").verdict == "unknown"


def test_preferred_education_and_experience_do_not_exclude():
    result = qualify(job(requirements="本科及以上，硕士优先。有3年工作经验优先。"), profile(), TODAY)
    assert check(result, "degree").verdict == "met"
    assert not any(c.verdict == "unmet" for c in result.checks)


def test_doctoral_graduate_degree_does_not_accept_masters():
    result = qualify(job(requirements="博士研究生学历。无需工作经验。"), profile(education_level="硕士研究生"), TODAY)
    assert check(result, "degree").verdict == "unmet"


def test_recent_graduate_wording_does_not_cancel_explicit_enrollment():
    result = qualify(job(requirements="应届本科在读。无需工作经验。"), profile(), TODAY)
    assert check(result, "student").verdict == "unmet"
    alternative = qualify(job(requirements="本科及以上。在校或应届毕业生。无需工作经验。"), profile(), TODAY)
    assert check(alternative, "student").verdict == "met"


def test_conditional_degree_exception_needs_verification():
    result = qualify(job(requirements="硕士及以上，优秀本科可放宽。无需工作经验。"), profile(), TODAY)
    assert check(result, "degree").verdict == "unknown"
    assert "本科可放宽" in check(result, "degree").job_quote
    assert result.verdict == "review"


def test_projects_cannot_be_counted_as_formal_work_years():
    result = qualify(job(requirements="本科及以上。3年以上工作经验。"), profile(projects=["三年个人项目：Python API 开发"]), TODAY)
    assert result.verdict == "ineligible"
    assert check(result, "experience").verdict == "unmet"
    unclear = qualify(job(requirements="本科。至少1年AI相关开发经验。"), profile(), TODAY)
    assert check(unclear, "experience").verdict == "unknown"


def test_expired_deadline_excludes_even_when_other_conditions_match():
    assert qualify(job(valid_until="2026-10-04"), profile(), TODAY).verdict == "ineligible"
    assert check(qualify(job(valid_until=None, requirements="本科。截止日期2026年10月4日。"), profile(), TODAY), "deadline").verdict == "unmet"
    assert check(qualify(job(valid_until=None, requirements="本科。截止日期10月4日。"), profile(), TODAY), "deadline").verdict == "unknown"


def test_school_barrier_requires_explicit_jd_evidence():
    assert not any(c.dimension == "school" for c in qualify(job(), profile(), TODAY).checks)
    assert qualify(job(requirements="本科及以上。仅限985/211院校。"), profile(), TODAY).verdict == "ineligible"
    assert not any(c.verdict == "unmet" for c in qualify(job(requirements="本科及以上。985/211优先。"), profile(), TODAY).checks)


def test_multi_job_notice_needs_per_job_verification_not_blanket_rejection():
    notice = job(record_type="notice", title="校园招聘公告", requirements="算法岗要求博士，工程岗本科。")
    assert qualify(notice, profile(), TODAY).verdict == "review"


def test_multi_cohort_range_and_preferred_year_do_not_falsely_reject():
    assert check(qualify(job(title="2025-2027届校招"), profile(), TODAY), "cohort").verdict == "met"
    assert check(qualify(job(title="2025、2026届校招"), profile(graduation_year=2025), TODAY), "cohort").verdict == "met"
    assert qualify(job(title="校招", requirements="本科及以上，2027届优先。无需工作经验。"), profile(), TODAY).verdict != "ineligible"


def test_deadline_parser_does_not_use_earlier_publication_date():
    current = job(valid_until=None, requirements="本科及以上。2026年9月1日发布 招聘截止2026年11月1日。")
    assert check(qualify(current, profile(), TODAY), "deadline").verdict == "met"


@pytest.mark.parametrize("year", range(2020, 2101))
def test_cohort_parser_supported_year_domain(year):
    assert _cohort_years(f"{year}届 AI 校招") == {year}
    if year < 2100:
        assert _cohort_years(f"【{year % 100}校招】FDE") == {year}
    for end in range(year, min(year + 4, 2100) + 1):
        assert _cohort_years(f"{year}-{end}届校园招聘") == set(range(year, end + 1))


def result(**changes):
    values = dict(direction="ai_application", direction_score=90, evidence_score=80, summary="Python 项目与 API 职责相关",
        matches=[{"requirement": "API 开发", "job_quote": "Python API 开发", "candidate_quote": "数据平台：用 Python 实现 API 和数据处理。", "reason": "已有 API 项目"}],
        gaps=[{"job_quote": "Python API 开发", "detail": "需要展示项目 API 的实现"}], next_steps=["准备可演示的 API 项目"])
    return OfficialFitResult.model_validate({**values, **changes})


class FakeGateway:
    def __init__(self, output):
        self.output = output
        self.prompt = ""

    def generate(self, _model, _system, user):
        self.prompt = user
        return self.output


def test_llm_fit_uses_only_exact_job_and_candidate_evidence():
    gateway = FakeGateway(result(matches=[{"requirement": "研发", "job_quote": "虚构需求", "candidate_quote": "曾在大厂工作3年", "reason": "虚构"}]))
    fit = evaluate_fit(job(), profile(), gateway)
    assert fit.matches == []
    assert fit.evidence_score == 0
    assert fit.grounding_warnings
    assert "allowed_evidence_quotes" in gateway.prompt


def test_ai_score_cannot_override_qualification_and_context_changes_invalidate():
    fit = result()
    assert priority_view(qualify(job(), profile(), TODAY), fit)["tier"] == "high"
    assert priority_view(qualify(job(), profile(), TODAY), result(direction="other", direction_score=100, evidence_score=100))["tier"] == "low"
    assert priority_view(qualify(job(title="2027届 FDE"), profile(), TODAY), fit)["tier"] == "defer"
    assert priority_view(qualify(job(requirements=""), profile(), TODAY), fit)["tier"] == "verify"
    assert fit_context_hash(job(), profile(), "mimo-v2.6-pro") != fit_context_hash(job(), profile(skills=["Python", "Go"]), "mimo-v2.6-pro")
