"""SQLite 有序迁移机制测试。"""

from pathlib import Path

import pytest

import career_radar.storage as storage_module
from career_radar.storage import (
    MIGRATIONS,
    SCHEMA_VERSION,
    JobStorage,
    Migration,
    _ensure_column,
)


def _user_version(storage: JobStorage) -> int:
    with storage.transaction() as connection:
        return connection.execute("PRAGMA user_version").fetchone()[0]


def test_fresh_database_reaches_current_schema_version(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "fresh.db")

    storage.initialize()

    assert _user_version(storage) == SCHEMA_VERSION
    with storage.transaction() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "jobs" in tables
    assert "job_embeddings" in tables


def test_initialize_is_idempotent(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "twice.db")

    storage.initialize()
    storage.initialize()

    assert _user_version(storage) == SCHEMA_VERSION


def test_unversioned_empty_database_is_healed(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "legacy.db")
    with storage.transaction() as connection:
        connection.execute("CREATE TABLE unrelated_probe (id INTEGER)")

    storage.initialize()

    assert _user_version(storage) == SCHEMA_VERSION
    with storage.transaction() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "jobs" in tables


def test_newer_database_is_rejected(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "newer.db")
    with storage.transaction() as connection:
        connection.execute("PRAGMA user_version = 99")

    with pytest.raises(RuntimeError, match="高于程序支持版本"):
        storage.initialize()


def test_registered_migrations_are_sorted_and_unique() -> None:
    versions = [migration.version for migration in MIGRATIONS]

    assert versions == sorted(versions)
    assert len(versions) == len(set(versions))


def test_migration_applies_once_and_bumps_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = JobStorage(tmp_path / "migrate.db")
    storage.initialize()
    applied: list[int] = []

    def probe_migration(connection) -> None:
        applied.append(1)
        _ensure_column(connection, "jobs", "migration_probe", "TEXT")

    monkeypatch.setattr(
        storage_module,
        "MIGRATIONS",
        list(MIGRATIONS) + [Migration(11, "probe column", probe_migration)],
    )
    monkeypatch.setattr(storage_module, "SCHEMA_VERSION", 11)

    storage.initialize()
    storage.initialize()

    assert applied == [1]
    assert _user_version(storage) == 11
    with storage.transaction() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
    assert "migration_probe" in columns
