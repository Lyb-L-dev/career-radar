"""监控服务逐公司入库行为测试。"""

import re
from pathlib import Path

import career_radar.pipeline as pipeline_module
from career_radar.crawler import FetchedPage
from career_radar.models import (
    AppConfig,
    AtsSourceConfig,
    CompanyConfig,
    CompanyRunResult,
    CrawlerConfig,
    JobPosting,
    LLMConfig,
    MatchLevel,
    PageAnalysis,
    Settings,
)
from career_radar.notifications import NotificationError
from career_radar.pipeline import (
    AnalysisBudget,
    AnalysisBudgetExceeded,
    CompanyMonitor,
    MonitoringCancelled,
    MonitorService,
    _job_matches_company_scope,
    _page_matches_company_scope,
)
from career_radar.storage import JobStorage


class DummyFetcher:
    """服务测试不访问网络，只满足上下文管理协议。"""

    def __init__(self, _config: CrawlerConfig) -> None:
        pass

    def __enter__(self) -> "DummyFetcher":
        return self

    def __exit__(self, *_args: object) -> None:
        pass


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(
            database_path=tmp_path / "jobs.db",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        ),
        crawler=CrawlerConfig(
            request_delay_min_seconds=0,
            request_delay_max_seconds=0,
            user_agent="Career Radar Test User Agent",
        ),
        llm=LLMConfig(provider="openai", model="test"),
        companies=[
            CompanyConfig(name="甲公司", url="https://a.example/jobs"),
            CompanyConfig(name="乙公司", url="https://b.example/jobs"),
        ],
    )


def test_monitor_service_stores_each_company_before_next_callback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr(pipeline_module, "create_provider", lambda _config: object())
    monkeypatch.setattr(pipeline_module, "PageFetcher", DummyFetcher)

    def fake_crawl(  # type: ignore[no-untyped-def]
        self, company, on_page_progress=None, should_cancel=None
    ):
        return CompanyRunResult(
            company=company.name,
            pages_visited=1,
            jobs=[
                JobPosting(
                    company=company.name,
                    title="初级开发工程师",
                    description="完整 JD 正文",
                    source_url=f"{company.url}/1",
                )
            ],
        )

    monkeypatch.setattr(pipeline_module.CompanyMonitor, "crawl", fake_crawl)
    stored_counts: list[int] = []

    def completed(_result, _events):  # type: ignore[no-untyped-def]
        stored_counts.append(len(JobStorage(settings.app.database_path).load_all_jobs()))

    result = MonitorService(settings).run(
        disable_email=True,
        on_company_complete=completed,
    )

    assert stored_counts == [1, 2]
    assert result.new_jobs == 2


def test_monitor_service_prunes_expired_reports_after_each_real_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    settings.app.report_retention_days = 7
    settings.app.output_dir.mkdir(parents=True)
    expired = settings.app.output_dir / "2020-01-01-jobs.md"
    unrelated = settings.app.output_dir / "notes.md"
    expired.write_text("old", encoding="utf-8")
    unrelated.write_text("keep", encoding="utf-8")

    monkeypatch.setattr(pipeline_module, "create_provider", lambda _config: object())
    monkeypatch.setattr(pipeline_module, "PageFetcher", DummyFetcher)
    monkeypatch.setattr(
        pipeline_module.CompanyMonitor,
        "crawl",
        lambda self, company, on_page_progress=None, should_cancel=None: CompanyRunResult(
            company=company.name
        ),
    )

    result = MonitorService(settings).run(disable_email=True)

    assert result.companies_processed == 2
    assert not expired.exists()
    assert unrelated.is_file()


def test_report_retention_failure_is_recorded_without_aborting_scan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(pipeline_module, "create_provider", lambda _config: object())
    monkeypatch.setattr(pipeline_module, "PageFetcher", DummyFetcher)
    monkeypatch.setattr(
        pipeline_module.CompanyMonitor,
        "crawl",
        lambda self, company, on_page_progress=None, should_cancel=None: CompanyRunResult(
            company=company.name
        ),
    )
    monkeypatch.setattr(
        pipeline_module,
        "prune_expired_reports",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("locked")),
    )

    result = MonitorService(settings).run(disable_email=True)

    assert result.companies_processed == 2
    assert any("历史日报自动清理失败" in error for error in result.errors)


def test_monitor_service_stops_before_the_next_company(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    cancelled = False
    crawled: list[str] = []

    monkeypatch.setattr(pipeline_module, "create_provider", lambda _config: object())
    monkeypatch.setattr(pipeline_module, "PageFetcher", DummyFetcher)

    def fake_crawl(  # type: ignore[no-untyped-def]
        self, company, on_page_progress=None, should_cancel=None
    ):
        crawled.append(company.name)
        return CompanyRunResult(
            company=company.name,
            pages_visited=1,
            jobs=[
                JobPosting(
                    company=company.name,
                    title="初级开发工程师",
                    description="完整 JD 正文",
                    source_url=f"{company.url}/1",
                )
            ],
        )

    def completed(_result, _events):  # type: ignore[no-untyped-def]
        nonlocal cancelled
        cancelled = True

    monkeypatch.setattr(pipeline_module.CompanyMonitor, "crawl", fake_crawl)

    try:
        MonitorService(settings).run(
            disable_email=True,
            on_company_complete=completed,
            should_cancel=lambda: cancelled,
        )
    except MonitoringCancelled:
        pass
    else:
        raise AssertionError("expected cooperative cancellation")

    assert crawled == ["甲公司"]
    assert len(JobStorage(settings.app.database_path).load_all_jobs()) == 1


def test_group_recruitment_page_requires_explicit_subsidiary_attribution() -> None:
    company = CompanyConfig(
        name="目标子公司",
        url="https://group.example/jobs",
        recruitment_channel="group_recruitment",
        parent_company="示例集团",
        attribution_keywords=["目标子公司", "目标品牌"],
    )

    assert _page_matches_company_scope(
        company,
        "目标子公司 2026 届校园招聘岗位说明",
    )
    assert _page_matches_company_scope(
        company,
        "目标 品牌 招聘软件工程师",
    )
    assert not _page_matches_company_scope(
        company,
        "集团总部及另一家子公司招聘岗位",
    )
    assert _job_matches_company_scope(
        company,
        JobPosting(
            title="软件工程师",
            description="所属单位：目标子公司；负责业务系统开发。",
        ),
    )
    assert not _job_matches_company_scope(
        company,
        JobPosting(
            title="软件工程师",
            description="负责集团总部业务系统开发。",
        ),
    )


class _IncrementalFetcher:
    def __init__(self, *, supports_304: bool) -> None:
        self.supports_304 = supports_304
        self.calls: list[dict[str, str]] = []

    def fetch(
        self,
        url: str,
        conditional_headers: dict[str, str] | None = None,
    ) -> FetchedPage:
        headers = conditional_headers or {}
        self.calls.append(headers)
        if self.supports_304 and headers.get("If-None-Match") == '"page-v1"':
            return FetchedPage(
                url,
                url,
                "",
                False,
                304,
                not_modified=True,
                etag='"page-v1"',
            )
        return FetchedPage(
            url,
            url,
            "<html><title>招聘</title><body>2026 届校园招聘</body></html>",
            False,
            200,
            etag='"page-v1"' if self.supports_304 else None,
        )


class _CountingAnalyzer:
    def __init__(self) -> None:
        self.calls = 0

    def analyze_page(self, *_args, **_kwargs) -> PageAnalysis:  # type: ignore[no-untyped-def]
        self.calls += 1
        return PageAnalysis(
            page_type="career_home",
            contains_recruitment_info=True,
            jobs=[],
            follow_links=[],
        )


def _run_incremental_scan(
    tmp_path: Path,
    *,
    supports_304: bool,
) -> tuple[_IncrementalFetcher, _CountingAnalyzer, list[dict[str, object]]]:
    settings = _settings(tmp_path)
    storage = JobStorage(settings.app.database_path)
    storage.initialize()
    fetcher = _IncrementalFetcher(supports_304=supports_304)
    analyzer = _CountingAnalyzer()
    monitor = CompanyMonitor(  # type: ignore[arg-type]
        settings,
        fetcher,
        analyzer,
        storage,
    )
    events: list[dict[str, object]] = []
    company = settings.companies[0]
    monitor.crawl(company, lambda _name, event: events.append(event))
    monitor.crawl(company, lambda _name, event: events.append(event))
    return fetcher, analyzer, events


def test_incremental_scan_reuses_analysis_on_http_304(tmp_path: Path) -> None:
    fetcher, analyzer, events = _run_incremental_scan(
        tmp_path,
        supports_304=True,
    )

    assert analyzer.calls == 1
    assert fetcher.calls[-1]["If-None-Match"] == '"page-v1"'
    assert events[-1]["cacheStatus"] == "not_modified"
    assert events[-1]["llmExtracted"] is False


def test_incremental_scan_reuses_analysis_when_content_hash_is_unchanged(
    tmp_path: Path,
) -> None:
    _fetcher, analyzer, events = _run_incremental_scan(
        tmp_path,
        supports_304=False,
    )

    assert analyzer.calls == 1
    assert events[-1]["cacheStatus"] == "content_unchanged"
    assert events[-1]["llmExtracted"] is False


def test_company_entry_wait_selector_applies_only_to_start_page(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    company = settings.companies[0]
    company.entry_wait_selector = ".job-list"
    seen: list[tuple[str, str | None]] = []

    class Fetcher:
        def fetch(
            self,
            url: str,
            _headers: dict[str, str] | None = None,
            *,
            wait_selector: str | None = None,
        ) -> FetchedPage:
            seen.append((url, wait_selector))
            html = (
                '<a href="/jobs/1001">查看职位</a>'
                if url == company.url
                else "<main>岗位职责：开发系统</main>"
            )
            return FetchedPage(url, url, html, False, 200)

    class Analyzer:
        def analyze_page(self, _company, url, _document, *_args, **_kwargs) -> PageAnalysis:
            return PageAnalysis(
                page_type="career_home" if url == company.url else "job_detail",
                contains_recruitment_info=True,
            )

    monitor = CompanyMonitor(settings, Fetcher(), Analyzer())  # type: ignore[arg-type]
    monitor.crawl(company)

    assert seen == [
        ("https://a.example/jobs", ".job-list"),
        ("https://a.example/jobs/1001", None),
    ]


def test_analysis_budget_enforces_a_hard_per_run_limit() -> None:
    budget = AnalysisBudget(1)
    budget.consume()

    try:
        budget.consume()
    except AnalysisBudgetExceeded as exc:
        assert "上限 1" in str(exc)
    else:
        raise AssertionError("expected DeepSeek page analysis budget to stop the run")


def test_monitor_service_sends_apprise_notifications_for_high_match_jobs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    settings.apprise.enabled = True
    settings.apprise.urls = ["tgram://bot:token/chat"]

    monkeypatch.setattr(pipeline_module, "create_provider", lambda _config: object())
    monkeypatch.setattr(pipeline_module, "PageFetcher", DummyFetcher)

    def fake_crawl(  # type: ignore[no-untyped-def]
        self, company, on_page_progress=None, should_cancel=None
    ):
        return CompanyRunResult(
            company=company.name,
            pages_visited=1,
            jobs=[
                JobPosting(
                    company=company.name,
                    title="初级开发工程师",
                    description="完整 JD 正文",
                    source_url=f"{company.url}/1",
                    match_level=MatchLevel.HIGH,
                )
            ],
        )

    monkeypatch.setattr(pipeline_module.CompanyMonitor, "crawl", fake_crawl)
    sent: list[tuple] = []
    monkeypatch.setattr(
        pipeline_module,
        "send_job_notifications",
        lambda config, events, date_text: sent.append((config, events, date_text)),
    )

    result = MonitorService(settings).run()

    assert result.apprise_sent is True
    assert len(sent) == 1
    assert len(sent[0][1]) == 2
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", sent[0][2])


def test_monitor_service_records_apprise_failure_without_aborting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    settings.apprise.enabled = True
    settings.apprise.urls = ["tgram://bot:token/chat"]

    monkeypatch.setattr(pipeline_module, "create_provider", lambda _config: object())
    monkeypatch.setattr(pipeline_module, "PageFetcher", DummyFetcher)

    def fake_crawl(  # type: ignore[no-untyped-def]
        self, company, on_page_progress=None, should_cancel=None
    ):
        return CompanyRunResult(
            company=company.name,
            pages_visited=1,
            jobs=[
                JobPosting(
                    company=company.name,
                    title="初级开发工程师",
                    description="完整 JD 正文",
                    source_url=f"{company.url}/1",
                    match_level=MatchLevel.HIGH,
                )
            ],
        )

    monkeypatch.setattr(pipeline_module.CompanyMonitor, "crawl", fake_crawl)
    monkeypatch.setattr(
        pipeline_module,
        "send_job_notifications",
        lambda *_args: (_ for _ in ()).throw(NotificationError("推送失败")),
    )

    result = MonitorService(settings).run()

    assert result.apprise_sent is False
    assert any("推送失败" in error for error in result.errors)


def test_monitor_service_uses_ats_source_instead_of_html_crawl(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    settings.companies[0].ats_source = AtsSourceConfig(
        type="greenhouse",
        tenant="acme",
    )

    monkeypatch.setattr(pipeline_module, "create_provider", lambda _config: object())
    monkeypatch.setattr(pipeline_module, "PageFetcher", DummyFetcher)
    crawled: list[str] = []
    monkeypatch.setattr(
        pipeline_module.CompanyMonitor,
        "crawl",
        lambda self, company, on_page_progress=None, should_cancel=None: crawled.append(
            company.name
        )
        or CompanyRunResult(company=company.name),
    )
    fetched: list[str] = []

    def fake_fetch_ats(self, company, on_page_progress=None, should_cancel=None):
        fetched.append(company.name)
        return CompanyRunResult(
            company=company.name,
            pages_visited=1,
            jobs=[
                JobPosting(
                    company=company.name,
                    title="ATS 岗位",
                    description="完整 JD 正文",
                    source_url="https://boards.greenhouse.io/acme/101",
                )
            ],
        )

    monkeypatch.setattr(pipeline_module.CompanyMonitor, "fetch_ats", fake_fetch_ats)

    result = MonitorService(settings).run(disable_email=True)

    assert fetched == ["甲公司"]
    assert crawled == ["乙公司"]
    assert result.new_jobs == 1
