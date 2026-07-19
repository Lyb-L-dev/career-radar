"""SQLite 去重、变化检测和指定指纹组成测试。"""

import sqlite3
from pathlib import Path

import pytest

from career_radar.models import JobPosting, MatchLevel
from career_radar.storage import JobStorage, compute_job_hashes


def _job(description: str) -> JobPosting:
    return JobPosting(
        company="测试公司",
        title="后端开发工程师",
        location="上海",
        description=description,
        requirements="本科，计算机相关专业",
        recruitment_type="校招",
        is_2026_target=True,
        target_graduates="2026 届",
        published_at="2026-07-17",
        apply_url="https://example.com/apply/1001",
        source_url="https://example.com/jobs/1001",
        match_level=MatchLevel.HIGH,
        match_reason="明确写明 2026 届",
    )


def test_new_unchanged_and_updated(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "jobs.db")
    storage.initialize()

    first = storage.store_jobs([_job("负责 API 开发")], "2026-07-17T08:00:00+08:00")
    same = storage.store_jobs([_job("负责 API 开发")], "2026-07-18T08:00:00+08:00")
    changed = storage.store_jobs(
        [_job("负责 API 开发，并维护分布式系统")],
        "2026-07-19T08:00:00+08:00",
    )

    assert first[0].event_type == "new"
    assert same[0].event_type == "unchanged"
    assert changed[0].event_type == "updated"
    assert len(storage.load_all_jobs()) == 1


def test_fingerprint_changes_when_required_components_change() -> None:
    original = compute_job_hashes(_job("A" * 120))
    changed_prefix = compute_job_hashes(_job("B" + "A" * 119))
    assert original[1] != changed_prefix[1]
    assert original[2] != changed_prefix[2]


def test_source_identity_is_stable_when_llm_location_wording_changes(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "jobs.db")
    storage.initialize()
    first_job = _job("完整 JD 正文")
    changed_location = first_job.model_copy(update={"location": "上海市徐汇区"})

    first = storage.store_jobs([first_job], "2026-07-18T08:00:00+08:00")
    second = storage.store_jobs([changed_location], "2026-07-19T08:00:00+08:00")

    assert first[0].event_type == "new"
    assert second[0].event_type == "updated"
    assert len(storage.load_all_jobs()) == 1


def test_shorter_reextract_keeps_previous_complete_jd(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "jobs.db")
    storage.initialize()
    complete = _job("完整职责与要求" * 100)
    shorter = _job("短摘要").model_copy(
        update={"requirements": None, "jd_complete": False}
    )

    storage.store_jobs([complete], "2026-07-18T08:00:00+08:00")
    storage.store_jobs([shorter], "2026-07-19T08:00:00+08:00")
    saved = storage.load_all_jobs()[0]

    assert saved.description == complete.description
    assert saved.requirements == complete.requirements
    assert saved.jd_complete is True


@pytest.mark.parametrize(
    ("first_updates", "second_updates"),
    [
        (
            {"source_url": "https://example.com/jobs/1001", "apply_url": None},
            {"source_url": "https://example.com/jobs/2002", "apply_url": None},
        ),
        (
            {"source_url": "", "apply_url": None, "location": "上海"},
            {"source_url": "", "apply_url": None, "location": "北京"},
        ),
        (
            {
                "source_url": "https://example.com/jobs",
                "apply_url": "https://example.com/apply/1001",
            },
            {
                "source_url": "https://example.com/jobs",
                "apply_url": "https://example.com/apply/2002",
            },
        ),
    ],
    ids=["different-detail-url", "different-location-without-url", "different-apply-url"],
)
def test_same_title_but_distinct_identity_stays_separate(
    tmp_path: Path,
    first_updates: dict[str, object],
    second_updates: dict[str, object],
) -> None:
    storage = JobStorage(tmp_path / "jobs.db")
    storage.initialize()
    first = _job("第一个岗位的完整 JD").model_copy(update=first_updates)
    second = _job("第二个岗位的完整 JD").model_copy(update=second_updates)

    events = storage.store_jobs([first, second], "2026-07-18T08:00:00+08:00")

    assert [event.event_type for event in events] == ["new", "new"]
    assert len(storage.load_all_jobs()) == 2


def test_list_summary_and_detail_with_same_apply_url_merge_into_one_job(
    tmp_path: Path,
) -> None:
    storage = JobStorage(tmp_path / "jobs.db")
    storage.initialize()
    summary = _job("列表摘要").model_copy(
        update={
            "source_url": "https://example.com/jobs",
            "jd_complete": False,
            "jd_incomplete_reason": "列表只有摘要",
        }
    )
    detail = _job("详情页完整职责" * 50).model_copy(
        update={"source_url": "https://example.com/jobs/1001"}
    )

    first = storage.store_jobs([summary], "2026-07-18T08:00:00+08:00")
    second = storage.store_jobs([detail], "2026-07-19T08:00:00+08:00")
    saved = storage.load_all_jobs()

    assert first[0].event_type == "new"
    assert second[0].event_type == "updated"
    assert len(saved) == 1
    assert saved[0].description == detail.description
    assert saved[0].source_url == detail.source_url
    assert saved[0].jd_complete is True


def _insert_legacy_job(
    connection: sqlite3.Connection,
    job: JobPosting,
    detected_at: str,
) -> str:
    entity_key, fingerprint, prefix_hash, content_hash = compute_job_hashes(job)
    connection.execute(
        """
        INSERT INTO jobs(
            entity_key, fingerprint, jd_prefix_hash, content_hash,
            company, title, published_at, match_level, apply_url,
            source_url, payload_json, first_seen_at, last_seen_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity_key,
            fingerprint,
            prefix_hash,
            content_hash,
            job.company,
            job.title,
            job.published_at,
            job.match_level.value,
            job.apply_url,
            job.source_url,
            job.model_dump_json(),
            detected_at,
            detected_at,
            detected_at,
        ),
    )
    return entity_key


def test_legacy_duplicate_cleanup_merges_user_state(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "jobs.db")
    storage.initialize()
    summary = _job("列表摘要").model_copy(update={"source_url": "https://example.com/jobs"})
    detail = _job("详情正文" * 20).model_copy(
        update={"source_url": "https://example.com/jobs/1001"}
    )
    with storage.transaction() as connection:
        summary_key = _insert_legacy_job(
            connection, summary, "2026-07-17T08:00:00+08:00"
        )
        detail_key = _insert_legacy_job(
            connection, detail, "2026-07-18T08:00:00+08:00"
        )
        connection.execute(
            "INSERT INTO web_job_state(entity_key, is_favorite, updated_at) VALUES (?, 1, ?)",
            (summary_key, "2026-07-18T08:00:00+08:00"),
        )
        connection.execute(
            "INSERT INTO web_job_state(entity_key, is_applied, updated_at) VALUES (?, 1, ?)",
            (detail_key, "2026-07-18T08:00:00+08:00"),
        )

    storage.store_jobs([detail], "2026-07-19T08:00:00+08:00")

    with storage.transaction() as connection:
        jobs_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        state = connection.execute(
            "SELECT is_favorite, is_applied FROM web_job_state"
        ).fetchone()
    assert jobs_count == 1
    assert tuple(state) == (1, 1)


def test_schema_contains_page_visit_and_candidate_state_tables(tmp_path: Path) -> None:
    database = tmp_path / "jobs.db"
    JobStorage(database).initialize()

    with sqlite3.connect(database) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='web_page_visits'"
        ).fetchone()
        candidate_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='company_candidate_state'"
        ).fetchone()
        reputation_scan_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='job_reputation_scans'"
        ).fetchone()
        reputation_evidence_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='job_reputation_evidence'"
        ).fetchone()
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert table == ("web_page_visits",)
    assert candidate_table == ("company_candidate_state",)
    assert reputation_scan_table == ("job_reputation_scans",)
    assert reputation_evidence_table == ("job_reputation_evidence",)
    assert version == 5
