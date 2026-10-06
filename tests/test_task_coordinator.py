"""Shared background resource coordination tests."""

from __future__ import annotations

import threading

import pytest

from career_radar.task_coordinator import TaskCoordinator, TaskCoordinatorClosed


def test_tasks_with_shared_resource_are_serialized() -> None:
    coordinator = TaskCoordinator()
    first_acquired = threading.Event()
    release_first = threading.Event()
    second_acquired = threading.Event()

    def first() -> None:
        with coordinator.acquire("scan", "one", {"llm"}):
            first_acquired.set()
            release_first.wait(timeout=2)

    def second() -> None:
        with coordinator.acquire("application", "two", {"llm"}):
            second_acquired.set()

    first_thread = threading.Thread(target=first)
    second_thread = threading.Thread(target=second)
    first_thread.start()
    assert first_acquired.wait(timeout=2)
    second_thread.start()
    assert not second_acquired.wait(timeout=0.05)

    release_first.set()
    assert second_acquired.wait(timeout=2)
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)
    assert coordinator.snapshot()["active"] == []


def test_tasks_with_distinct_resources_can_run_together() -> None:
    coordinator = TaskCoordinator()
    barrier = threading.Barrier(3)

    def worker(task_id: str, resource: str) -> None:
        with coordinator.acquire("test", task_id, {resource}):
            barrier.wait(timeout=2)

    threads = [
        threading.Thread(target=worker, args=("one", "opencli")),
        threading.Thread(target=worker, args=("two", "browser")),
    ]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=2)
    for thread in threads:
        thread.join(timeout=2)


def test_shutdown_rejects_queued_and_new_acquisitions() -> None:
    coordinator = TaskCoordinator()
    first_acquired = threading.Event()
    release_first = threading.Event()
    queued_rejected = threading.Event()

    def holder() -> None:
        with coordinator.acquire("scan", "holder", {"llm"}):
            first_acquired.set()
            release_first.wait(timeout=2)

    def waiter() -> None:
        try:
            with coordinator.acquire("scan", "waiter", {"llm"}):
                pytest.fail("queued task must not acquire after shutdown")
        except TaskCoordinatorClosed:
            queued_rejected.set()

    holder_thread = threading.Thread(target=holder)
    waiter_thread = threading.Thread(target=waiter)
    holder_thread.start()
    assert first_acquired.wait(timeout=2)
    waiter_thread.start()
    coordinator.shutdown()
    assert queued_rejected.wait(timeout=2)

    with pytest.raises(TaskCoordinatorClosed, match="正在关闭"):
        with coordinator.acquire("scan", "one", {"llm"}):
            pass

    release_first.set()
    holder_thread.join(timeout=2)
    waiter_thread.join(timeout=2)
