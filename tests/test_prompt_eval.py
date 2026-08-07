"""提示词回归评测测试（注入假供应商，不调用真实 LLM）。"""

from career_radar.llm import LLMProvider
from career_radar.models import (
    AppConfig,
    CompanyConfig,
    CrawlerConfig,
    JobPosting,
    LLMConfig,
    PageAnalysis,
    Settings,
)
from career_radar.prompt_eval import (
    BUILTIN_CASES,
    EvalCase,
    run_prompt_eval,
)


def _settings() -> Settings:
    return Settings(
        app=AppConfig(),
        crawler=CrawlerConfig(
            request_delay_min_seconds=0,
            request_delay_max_seconds=0,
            user_agent="Career Radar Test User Agent",
        ),
        llm=LLMConfig(provider="openai", model="test"),
        companies=[CompanyConfig(name="评测公司", url="https://example.com/")],
    )


class FakeProvider(LLMProvider):
    def __init__(self, analysis: PageAnalysis) -> None:
        self.analysis = analysis

    def analyze(self, user_prompt: str) -> PageAnalysis:
        return self.analysis.model_copy(deep=True)


def _jd_analysis() -> PageAnalysis:
    return PageAnalysis(
        page_type="job_detail",
        contains_recruitment_info=True,
        jobs=[
            JobPosting(
                title="后端开发工程师",
                location="福州",
                description=(
                    "岗位职责：负责公司核心业务系统开发，参与微服务架构建设。"
                ),
                requirements="2026 届本科及以上，熟悉 Python 与 MySQL。",
            )
        ],
        follow_links=[],
    )


def test_run_prompt_eval_marks_passing_case() -> None:
    case = EvalCase(
        name="通过样例",
        page_text="职位名称：后端开发工程师",
        expected_page_type="job_detail",
        expected_title="后端开发工程师",
        expected_location="福州",
        expected_keywords=("Python", "微服务"),
    )

    report = run_prompt_eval(
        _settings(),
        provider=FakeProvider(_jd_analysis()),
        cases=[case],
    )

    assert report.results[0].passed
    assert report.results[0].failures == []
    assert report.all_passed()
    assert "通过样例" in report.markdown()


def test_run_prompt_eval_reports_failures() -> None:
    case = EvalCase(
        name="失败样例",
        page_text="欢迎访问官网",
        expected_page_type="job_detail",
        expected_title="后端开发工程师",
    )
    empty = PageAnalysis(page_type="no_jobs", contains_recruitment_info=False)

    report = run_prompt_eval(
        _settings(),
        provider=FakeProvider(empty),
        cases=[case],
    )

    result = report.results[0]
    assert not result.passed
    assert any("页面类型" in failure for failure in result.failures)
    assert any("未提取到标题" in failure for failure in result.failures)
    assert not report.all_passed()


def test_builtin_cases_are_well_formed() -> None:
    names = [case.name for case in BUILTIN_CASES]

    assert len(names) == len(set(names))
    assert all(case.name and case.page_text for case in BUILTIN_CASES)


def test_limit_restricts_case_count() -> None:
    report = run_prompt_eval(
        _settings(),
        provider=FakeProvider(_jd_analysis()),
        cases=list(BUILTIN_CASES),
        limit=1,
    )

    assert len(report.results) == 1
