"""同义岗位自动合并测试：换标题重发应合并，不同岗位不应误合并。"""

from pathlib import Path

from career_radar.embeddings import jaccard_similarity
from career_radar.models import JobPosting
from career_radar.storage import JobStorage


def _storage(tmp_path: Path, window_days: int = 90) -> JobStorage:
    storage = JobStorage(
        tmp_path / "dedup.db",
        semantic_duplicate_window_days=window_days,
    )
    storage.initialize()
    return storage


def test_jaccard_separates_duplicates_from_distinct_roles() -> None:
    original = "后端开发工程师 福州 负责核心系统开发 熟悉 Python 微服务 2026届"
    variant = "Java后端开发工程师 福州 负责核心系统开发 熟悉 Python 微服务 2026届"
    distinct = "前端开发工程师 福州 负责页面开发 熟悉 React TypeScript 视觉还原 2026届"

    assert jaccard_similarity(original, variant) >= 0.6
    assert jaccard_similarity(original, distinct) < 0.6


def test_variant_title_repost_merges_into_existing_entity(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    original = JobPosting(
        title="后端开发工程师",
        company="甲公司",
        location="福州",
        description="负责核心系统开发 熟悉 Python 微服务 2026届",
        source_url="https://example.com/jobs/1",
    )
    repost = JobPosting(
        title="Java后端开发工程师",
        company="甲公司",
        location="福州",
        description="负责核心系统开发 熟悉 Python 微服务 2026届",
        source_url="https://example.com/jobs/2",
    )

    first = storage.store_jobs([original], "2026-08-01T08:00:00+08:00")
    second = storage.store_jobs([repost], "2026-08-07T08:00:00+08:00")

    assert first[0].event_type == "new"
    assert second[0].event_type == "updated"
    assert len(storage.load_all_jobs()) == 1


def test_distinct_roles_are_not_merged(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    backend = JobPosting(
        title="后端开发工程师",
        company="甲公司",
        location="福州",
        description="负责核心系统开发 熟悉 Python 微服务 数据库",
        source_url="https://example.com/jobs/1",
    )
    frontend = JobPosting(
        title="前端开发工程师",
        company="甲公司",
        location="福州",
        description="负责页面开发 熟悉 React TypeScript 视觉还原",
        source_url="https://example.com/jobs/2",
    )

    events = storage.store_jobs([backend, frontend], "2026-08-07T08:00:00+08:00")

    assert [event.event_type for event in events] == ["new", "new"]
    assert len(storage.load_all_jobs()) == 2


def test_stale_original_is_not_merged(tmp_path: Path) -> None:
    storage = _storage(tmp_path, window_days=90)
    original = JobPosting(
        title="后端开发工程师",
        company="甲公司",
        location="福州",
        description="负责核心系统开发 熟悉 Python 微服务 2026届",
        source_url="https://example.com/jobs/1",
    )
    repost = JobPosting(
        title="Java后端开发工程师",
        company="甲公司",
        location="福州",
        description="负责核心系统开发 熟悉 Python 微服务 2026届",
        source_url="https://example.com/jobs/2",
    )

    storage.store_jobs([original], "2025-01-01T08:00:00+08:00")
    events = storage.store_jobs([repost], "2026-08-07T08:00:00+08:00")

    assert events[0].event_type == "new"
    assert len(storage.load_all_jobs()) == 2


def test_merge_duplicate_jobs_cleans_existing_database(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "dedup.db")
    storage.initialize()
    original = JobPosting(
        title="后端开发工程师",
        company="甲公司",
        location="福州",
        description="负责核心系统开发 熟悉 Python 微服务 2026届",
        source_url="https://example.com/jobs/1",
    )
    repost = JobPosting(
        title="Java后端开发工程师",
        company="甲公司",
        location="福州",
        description="负责核心系统开发 熟悉 Python 微服务 2026届",
        source_url="https://example.com/jobs/2",
    )
    storage.store_jobs([original], "2026-08-01T08:00:00+08:00")
    storage.store_jobs([repost], "2026-08-02T08:00:00+08:00")
    assert len(storage.load_all_jobs()) == 2

    merged = storage.merge_duplicate_jobs(90)

    assert len(merged) == 1
    assert len(storage.load_all_jobs()) == 1
