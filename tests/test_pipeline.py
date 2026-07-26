"""监控服务逐公司入库行为测试。"""

from pathlib import Path

import career_radar.pipeline as pipeline_module
from career_radar.models import (
    AppConfig,
    CompanyConfig,
    CompanyRunResult,
    CrawlerConfig,
    JobPosting,
    LLMConfig,
    Settings,
)
from career_radar.pipeline import (
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
