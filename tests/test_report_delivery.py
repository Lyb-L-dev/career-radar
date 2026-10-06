"""历史日报邮件重建与筛选测试；发送器始终使用本地替身。"""

from pathlib import Path

from career_radar.models import (
    AppConfig,
    CompanyConfig,
    CrawlerConfig,
    JobPosting,
    LLMConfig,
    MatchLevel,
    ProfileFitLevel,
    Settings,
    SMTPConfig,
)
from career_radar.report_delivery import HistoricalReportDelivery
from career_radar.storage import JobStorage


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(
            database_path=tmp_path / "jobs.db",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        ),
        crawler=CrawlerConfig(user_agent="Career Radar delivery test"),
        llm=LLMConfig(provider="deepseek", model="test-model"),
        smtp=SMTPConfig(
            enabled=True,
            host="smtp.example.com",
            username="sender@example.com",
            from_address="sender@example.com",
            to_addresses=["recipient@example.com"],
        ),
        companies=[CompanyConfig(name="测试公司", url="https://example.com/jobs")],
    )


def _job(description: str, *, profile_fit: ProfileFitLevel) -> JobPosting:
    return JobPosting(
        company="测试公司",
        title="数据开发工程师",
        description=description,
        source_url="https://example.com/jobs/1",
        match_level=MatchLevel.HIGH,
        profile_fit_level=profile_fit,
        difficulty_score=5,
    )


def test_historical_delivery_uses_original_event_version_and_current_filters(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    storage = JobStorage(settings.app.database_path)
    storage.initialize()
    storage.store_jobs(
        [_job("第一天原始 JD", profile_fit=ProfileFitLevel.HIGH)],
        "2026-08-01T08:00:00+08:00",
    )
    storage.store_jobs(
        [_job("第二天更新 JD", profile_fit=ProfileFitLevel.HIGH)],
        "2026-08-02T08:00:00+08:00",
    )
    storage.store_jobs(
        [
            JobPosting(
                company="测试公司",
                title="低匹配岗位",
                description="不会进入通知",
                source_url="https://example.com/jobs/2",
                match_level=MatchLevel.HIGH,
                profile_fit_level=ProfileFitLevel.LOW,
                difficulty_score=5,
            )
        ],
        "2026-08-01T09:00:00+08:00",
    )
    sent: list[tuple[list, str]] = []

    result = HistoricalReportDelivery(
        settings,
        sender=lambda _config, events, date_text: sent.append((events, date_text)),
    ).deliver("2026-08-01")

    assert result.event_count == 1
    assert sent[0][1] == "2026-08-01"
    assert sent[0][0][0].job.description == "第一天原始 JD"
