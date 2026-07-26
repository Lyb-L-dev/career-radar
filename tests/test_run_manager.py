"""Web 扫描任务的协作停止状态机测试。"""

from __future__ import annotations

import copy
import threading
import time
from pathlib import Path
from typing import Any

import career_radar.run_manager as run_manager_module
from career_radar.models import AppConfig, CompanyConfig, CrawlerConfig, LLMConfig, Settings
from career_radar.pipeline import MonitoringCancelled
from career_radar.run_manager import RunManager


class MemoryRunRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.saved: dict[str, dict[str, Any]] = {}
        self.history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(value) for value in self.saved.values()]

    def save_run(self, payload: dict[str, Any]) -> None:
        with self._lock:
            snapshot = copy.deepcopy(payload)
            self.saved[payload["id"]] = snapshot
            self.history.append(snapshot)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppConfig(
            database_path=tmp_path / "jobs.db",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        ),
        crawler=CrawlerConfig(user_agent="Career Radar Test User Agent"),
        llm=LLMConfig(provider="openai", model="test"),
        companies=[
            CompanyConfig(name="甲公司", url="https://a.example/jobs"),
            CompanyConfig(name="乙公司", url="https://b.example/jobs"),
        ],
    )


def test_run_manager_cooperatively_stops_and_marks_unfinished_companies_skipped(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = MemoryRunRepository(_settings(tmp_path))
    running = threading.Event()
    cancellation_seen = threading.Event()
    release = threading.Event()

    class WaitingMonitorService:
        def __init__(self, _settings: Settings) -> None:
            pass

        def run(self, *, should_cancel, **_kwargs):  # type: ignore[no-untyped-def]
            running.set()
            while not should_cancel():
                time.sleep(0.001)
            cancellation_seen.set()
            release.wait(timeout=2)
            raise MonitoringCancelled("test stop")

    monkeypatch.setattr(run_manager_module, "create_provider", lambda _config: object())
    monkeypatch.setattr(run_manager_module, "MonitorService", WaitingMonitorService)
    manager = RunManager(repository)  # type: ignore[arg-type]

    try:
        created = manager.create()
        assert running.wait(timeout=2)

        manager.stop(created["id"])
        manager.stop(created["id"])
        assert cancellation_seen.wait(timeout=2)
        assert repository.saved[created["id"]]["status"] == "stopping"
        assert repository.saved[created["id"]]["canStop"] is False

        release.set()
        deadline = time.monotonic() + 2
        while repository.saved[created["id"]]["status"] != "interrupted":
            if time.monotonic() >= deadline:
                raise AssertionError("run did not reach interrupted state")
            time.sleep(0.005)

        final = repository.saved[created["id"]]
        assert final["canStop"] is False
        assert final["skippedCount"] == 2
        assert final["finishedCompanies"] == 2
        assert {company["status"] for company in final["companies"]} == {"skipped"}
        assert {company["skipReason"] for company in final["companies"]} == {"user_stop"}
        assert any("安全点停止" in log["message"] for log in final["logs"])
    finally:
        release.set()
        manager._executor.shutdown(wait=True)
