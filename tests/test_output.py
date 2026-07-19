"""Markdown 完整 JD 与 CSV Excel 安全输出测试。"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from career_radar.models import (
    DifficultyLevel,
    JobPosting,
    MatchLevel,
    ProfileFitLevel,
    StoredJobEvent,
)
from career_radar.output import ReportWriter


def test_report_contains_full_jd_and_csv_bom(tmp_path: Path) -> None:
    description = "完整 JD：" + "职责与要求。" * 500
    job = JobPosting(
        company="测试公司",
        title="=HYPERLINK(恶意公式)",
        description=description,
        source_url="https://example.com/jobs/1",
        match_level=MatchLevel.HIGH,
        profile_fit_level=ProfileFitLevel.MEDIUM,
        profile_fit_reason="基础技能匹配，但尚无实习经历",
        difficulty_level=DifficultyLevel.HIGH,
        difficulty_score=7,
        difficulty_reason="要求一段相关项目或实习经历",
    )
    event = StoredJobEvent(
        event_type="new",
        job=job,
        entity_key="key",
        fingerprint="fingerprint",
        detected_at="2026-07-17T08:00:00+08:00",
    )
    writer = ReportWriter(tmp_path)
    markdown, csv_path = writer.write_daily(
        [event], [], datetime(2026, 7, 17, 8, tzinfo=ZoneInfo("Asia/Shanghai")), write_empty=False
    )

    assert markdown is not None and description in markdown.read_text(encoding="utf-8")
    assert "能力匹配" in markdown.read_text(encoding="utf-8")
    assert "7/10" in markdown.read_text(encoding="utf-8")
    assert csv_path is not None and csv_path.read_bytes().startswith(b"\xef\xbb\xbf")
    csv_text = csv_path.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK" in csv_text
    assert "difficulty_score" in csv_text
    assert ",7," in csv_text
