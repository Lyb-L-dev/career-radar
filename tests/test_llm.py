"""供应商无关分析器的 URL 白名单、长页面切片和结果合并测试。"""

from types import SimpleNamespace

import openai
import pytest

from career_radar.discovery import parse_html
from career_radar.llm import (
    DeepSeekProvider,
    FatalLLMError,
    LLMProvider,
    PageAnalyzer,
    RetryableLLMError,
    _request_error,
)
from career_radar.models import (
    DifficultyLevel,
    FollowLink,
    JobPosting,
    LLMConfig,
    MatchLevel,
    PageAnalysis,
    ProfileFitLevel,
)


class FakeProvider(LLMProvider):
    """返回确定结果，测试不访问真实 LLM API。"""

    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, user_prompt: str) -> PageAnalysis:
        self.calls += 1
        return PageAnalysis(
            page_type="job_detail",
            contains_recruitment_info=True,
            jobs=[
                JobPosting(
                    title="算法工程师",
                    description=f"第 {self.calls} 段 JD",
                    apply_url="https://evil.example/fake",
                    match_level=MatchLevel.HIGH,
                    match_reason="明确面向 2026 届",
                )
            ],
            follow_links=[],
        )


class StaticProvider(LLMProvider):
    """返回测试预先构造的单页结果。"""

    def __init__(self, result: PageAnalysis) -> None:
        self.result = result

    def analyze(self, user_prompt: str) -> PageAnalysis:
        return self.result.model_copy(deep=True)


def test_page_analyzer_only_retries_retryable_errors() -> None:
    expected = PageAnalysis(page_type="no_jobs", contains_recruitment_info=False)

    class FlakyProvider(LLMProvider):
        def __init__(self) -> None:
            self.calls = 0

        def analyze(self, user_prompt: str) -> PageAnalysis:
            self.calls += 1
            if self.calls < 3:
                raise RetryableLLMError("服务端暂时不可用")
            return expected

    provider = FlakyProvider()
    delays: list[float] = []
    analyzer = PageAnalyzer(
        LLMConfig(provider="openai", model="test", max_retries=3),
        provider,
        sleeper=delays.append,
    )

    assert analyzer._call_with_retry("test") == expected
    assert provider.calls == 3
    assert delays == [1, 2]


def test_page_analyzer_fails_immediately_for_fatal_error() -> None:
    class FatalProvider(LLMProvider):
        def __init__(self) -> None:
            self.calls = 0

        def analyze(self, user_prompt: str) -> PageAnalysis:
            self.calls += 1
            raise FatalLLMError("API Key 无效")

    provider = FatalProvider()
    delays: list[float] = []
    analyzer = PageAnalyzer(
        LLMConfig(provider="openai", model="test", max_retries=3),
        provider,
        sleeper=delays.append,
    )

    with pytest.raises(FatalLLMError, match="API Key"):
        analyzer._call_with_retry("test")
    assert provider.calls == 1
    assert delays == []


@pytest.mark.parametrize(
    ("status", "code", "expected_type"),
    [
        (401, "invalid_api_key", FatalLLMError),
        (404, "model_not_found", FatalLLMError),
        (429, "rate_limit_exceeded", RetryableLLMError),
        (429, "insufficient_quota", FatalLLMError),
        (503, "server_error", RetryableLLMError),
    ],
)
def test_request_error_classification(status: int, code: str, expected_type: type[Exception]) -> None:
    class SDKError(Exception):
        status_code = status
        body = {"error": {"code": code}}

    assert isinstance(_request_error("测试供应商", SDKError("boom")), expected_type)


def test_analyzer_chunks_rejects_hallucination_and_recovers_page_apply_url() -> None:
    provider = FakeProvider()
    config = LLMConfig(
        provider="openai",
        model="test",
        max_input_chars=10_000,
        chunk_overlap_chars=100,
        max_output_tokens=2000,
        max_retries=1,
    )
    analyzer = PageAnalyzer(config, provider)
    html = f'<a href="/apply/1">申请</a><p>{"岗位正文" * 4000}</p>'
    document = parse_html(html, "https://example.com/jobs/1")

    analysis = analyzer.analyze_page("测试公司", "https://example.com/jobs/1", document, 20)

    assert provider.calls > 1
    assert analysis.jobs[0].company == "测试公司"
    assert analysis.jobs[0].source_url == "https://example.com/jobs/1"
    # 模型虚构的跨站 URL 被丢弃，但页面真实存在的申请锚点会被确定性补回。
    assert analysis.jobs[0].apply_url == "https://example.com/apply/1"
    assert "第 1 段" in analysis.jobs[0].description


def test_dense_multi_job_page_is_chunked_even_below_global_limit() -> None:
    class CountingProvider(LLMProvider):
        def __init__(self) -> None:
            self.calls = 0

        def analyze(self, user_prompt: str) -> PageAnalysis:
            self.calls += 1
            return PageAnalysis(
                page_type="job_list",
                contains_recruitment_info=True,
                jobs=[],
            )

    provider = CountingProvider()
    analyzer = PageAnalyzer(
        LLMConfig(provider="openai", model="test", max_input_chars=20_000),
        provider,
    )
    block = (
        "数据开发工程师\n工作描述\n"
        + "负责数据平台采集、清洗、入库与接口开发。" * 60
        + "\n职位要求\n熟悉 Python 和 SQL。\n"
    )
    document = parse_html(f"<p>{block * 8}</p>", "https://example.com/jobs")

    analyzer.analyze_page("测试公司", "https://example.com/jobs", document, 20)

    assert provider.calls > 1


def test_analyzer_preserves_only_email_present_in_page_text() -> None:
    result = PageAnalysis(
        page_type="job_detail",
        contains_recruitment_info=True,
        jobs=[
            JobPosting(title="有效邮箱岗位", apply_url="mailto:jobs@example.com"),
            JobPosting(title="虚构邮箱岗位", apply_url="mailto:fake@example.com"),
        ],
    )
    analyzer = PageAnalyzer(LLMConfig(provider="openai", model="test"), StaticProvider(result))
    document = parse_html("<p>请将简历发送至 jobs@example.com</p>", "https://example.com/job")

    analysis = analyzer.analyze_page("测试公司", "https://example.com/job", document, 20)

    assert analysis.jobs[0].apply_url == "mailto:jobs@example.com"
    assert analysis.jobs[1].apply_url is None


def test_job_list_summary_is_suppressed_when_detail_link_exists() -> None:
    result = PageAnalysis(
        page_type="job_list",
        contains_recruitment_info=True,
        jobs=[JobPosting(title="研发中心招聘启动")],
        follow_links=[
            FollowLink(
                url="https://example.com/jobs/detail",
                kind="job_detail",
                reason="详情页包含具体岗位",
            )
        ],
    )
    analyzer = PageAnalyzer(LLMConfig(provider="openai", model="test"), StaticProvider(result))
    document = parse_html(
        '<a href="/jobs/detail">查看具体岗位</a>',
        "https://example.com/jobs",
    )

    analysis = analyzer.analyze_page("测试公司", "https://example.com/jobs", document, 20)

    assert analysis.jobs == []
    assert analysis.follow_links[0].url == "https://example.com/jobs/detail"


def test_analyzer_forces_heuristic_detail_link_and_suppresses_summary() -> None:
    result = PageAnalysis(
        page_type="job_list",
        contains_recruitment_info=True,
        jobs=[JobPosting(title="数据开发实习生", description="岗位摘要")],
    )
    analyzer = PageAnalyzer(LLMConfig(provider="openai", model="test"), StaticProvider(result))
    document = parse_html(
        '<a href="/jobs/1001">查看职位详情</a>',
        "https://example.com/jobs",
    )

    analysis = analyzer.analyze_page("测试公司", "https://example.com/jobs", document, 20)

    assert analysis.jobs == []
    assert analysis.follow_links[0].kind == "job_detail"
    assert analysis.follow_links[0].url == "https://example.com/jobs/1001"


def test_summary_without_detail_is_marked_incomplete() -> None:
    result = PageAnalysis(
        page_type="job_list",
        contains_recruitment_info=True,
        jobs=[JobPosting(title="数据开发实习生", description="仅有一句岗位摘要")],
    )
    analyzer = PageAnalyzer(LLMConfig(provider="openai", model="test"), StaticProvider(result))
    document = parse_html("<p>仅有一句岗位摘要</p>", "https://example.com/jobs")

    analysis = analyzer.analyze_page("测试公司", "https://example.com/jobs", document, 20)

    assert analysis.jobs[0].jd_complete is False
    assert "未发现" in (analysis.jobs[0].jd_incomplete_reason or "")


def test_official_notice_without_job_link_is_preserved_as_complete() -> None:
    """招聘公告没有独立职位入口是正常形态，不能按岗位摘要丢弃。"""

    result = PageAnalysis(
        page_type="job_detail",
        contains_recruitment_info=True,
        jobs=[
            JobPosting(
                record_type="notice",
                title="某市属国企2026年度公开招聘公告",
                description="招聘对象、资格条件、报名时间、报名方式和考试流程。",
                application_method="按公告要求发送报名材料",
            )
        ],
    )
    provider = StaticProvider(result)
    analyzer = PageAnalyzer(LLMConfig(provider="openai", model="test"), provider)
    document = parse_html("<p>完整招聘公告正文</p>", "https://example.gov.cn/news/1")

    analysis = analyzer.analyze_page(
        "某市属国企",
        "https://example.gov.cn/news/1",
        document,
        20,
        monitor_mode="notices",
    )

    assert len(analysis.jobs) == 1
    assert analysis.jobs[0].record_type == "notice"
    assert analysis.jobs[0].jd_complete is True


def test_apply_endpoint_is_not_mistaken_for_detail_and_concise_jd_is_kept() -> None:
    result = PageAnalysis(
        page_type="job_list",
        contains_recruitment_info=True,
        jobs=[
            JobPosting(
                title="数据平台工程师",
                description="负责数据采集、清洗、入库、接口开发与线上问题排查。" * 4,
                requirements="本科应届毕业生，熟悉 Python、SQL 与 MySQL，具备完整项目经验。",
            )
        ],
        follow_links=[
            FollowLink(
                url="https://example.com/apply/1001",
                kind="job_detail",
                reason="模型误把申请端点当成详情",
            )
        ],
    )
    analyzer = PageAnalyzer(LLMConfig(provider="openai", model="test"), StaticProvider(result))
    document = parse_html(
        '<a href="/apply/1001">立即申请</a>',
        "https://example.com/jobs",
    )

    analysis = analyzer.analyze_page("测试公司", "https://example.com/jobs", document, 20)

    assert len(analysis.jobs) == 1
    assert analysis.jobs[0].jd_complete is True
    assert analysis.follow_links == []


def test_mailto_anchor_and_application_text_are_recovered() -> None:
    result = PageAnalysis(
        page_type="job_detail",
        contains_recruitment_info=True,
        jobs=[JobPosting(title="后端开发工程师", description="完整岗位正文" * 100)],
    )
    analyzer = PageAnalyzer(LLMConfig(provider="openai", model="test"), StaticProvider(result))
    document = parse_html(
        '<p>投递方式</p><a href="mailto:jobs@example.com">立即投递简历</a>',
        "https://example.com/jobs/1",
    )

    analysis = analyzer.analyze_page("测试公司", "https://example.com/jobs/1", document, 20)
    job = analysis.jobs[0]

    assert job.apply_url == "mailto:jobs@example.com"
    assert job.contact_email == "jobs@example.com"
    assert job.application_method


def test_deepseek_uses_json_output_and_validates_schema(monkeypatch) -> None:
    """DeepSeek 适配器必须启用 JSON Output，并把结果交给 Pydantic 校验。"""

    captured: dict[str, object] = {}
    expected = PageAnalysis(
        page_type="job_detail",
        contains_recruitment_info=True,
        jobs=[
            JobPosting(
                title="初级 Python 开发工程师",
                profile_fit_level=ProfileFitLevel.HIGH,
                profile_fit_reason="项目经历与岗位技术栈一致",
                difficulty_level=DifficultyLevel.MEDIUM,
                difficulty_score=5,
                difficulty_reason="要求基础项目经验，但未限制学校层次",
            )
        ],
    )

    class FakeCompletions:
        def create(self, **kwargs: object) -> object:
            captured["request"] = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=expected.model_dump_json())
                    )
                ]
            )

    class FakeClient:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(completions=FakeCompletions())

    def fake_openai(**kwargs: object) -> FakeClient:
        captured["client"] = kwargs
        return FakeClient()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(openai, "OpenAI", fake_openai)
    provider = DeepSeekProvider(
        LLMConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            max_output_tokens=2000,
        )
    )

    result = provider.analyze("请分析这个公开招聘页面并输出 JSON")

    assert result.jobs[0].title == "初级 Python 开发工程师"
    assert result.jobs[0].difficulty_score == 5
    assert captured["client"]["base_url"] == "https://api.deepseek.com"  # type: ignore[index]
    assert captured["client"]["max_retries"] == 0  # type: ignore[index]
    request = captured["request"]
    assert request["response_format"] == {"type": "json_object"}  # type: ignore[index]
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}  # type: ignore[index]


def test_deepseek_thinking_extension_can_be_disabled_for_compatible_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兼容代理不识别 thinking 扩展时，不应把该字段硬塞给 SDK。"""

    captured: dict[str, object] = {}
    expected = PageAnalysis(page_type="no_jobs", contains_recruitment_info=False)

    class FakeCompletions:
        def create(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=expected.model_dump_json()))]
            )

    class FakeClient:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(openai, "OpenAI", lambda **_kwargs: FakeClient())
    provider = DeepSeekProvider(
        LLMConfig(
            provider="deepseek",
            model="compatible-model",
            disable_thinking=False,
        )
    )

    provider.analyze("测试")

    assert "extra_body" not in captured
