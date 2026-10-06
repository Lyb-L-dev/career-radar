"""Shared in-process resource coordination for background workflows."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime


class TaskCoordinatorClosed(RuntimeError):
    """The API is shutting down and no new resource reservation is accepted."""


@dataclass(frozen=True, slots=True)
class ActiveTask:
    task_type: str
    task_id: str
    resources: tuple[str, ...]
    started_at: str


class TaskCoordinator:
    """Atomically reserve named resources across all background managers.

    Managers retain their domain-specific executors and recovery logic. This
    coordinator only prevents expensive/shared local resources from being used
    concurrently by otherwise independent workflows.
    """

    def __init__(self, limits: dict[str, int] | None = None) -> None:
        self._limits = {
            "browser": 1,
            "opencli": 1,
            "llm": 1,
            "document": 1,
            **(limits or {}),
        }
        if any(limit < 1 for limit in self._limits.values()):
            raise ValueError("任务资源并发上限必须至少为 1")
        self._condition = threading.Condition()
        self._usage: dict[str, int] = {}
        self._active: dict[tuple[str, str], ActiveTask] = {}
        self._closed = False

    def _available(self, resources: tuple[str, ...]) -> bool:
        return all(
            self._usage.get(resource, 0) < self._limits.get(resource, 1)
            for resource in resources
        )

    @contextmanager
    def acquire(
        self,
        task_type: str,
        task_id: str,
        resources: set[str] | tuple[str, ...],
    ) -> Iterator[None]:
        """Wait for and atomically reserve every requested resource."""

        requested = tuple(sorted(set(resources)))
        key = (task_type, task_id)
        with self._condition:
            while not self._closed and not self._available(requested):
                self._condition.wait()
            if self._closed:
                raise TaskCoordinatorClosed("API 服务正在关闭，未启动新的后台任务")
            for resource in requested:
                self._usage[resource] = self._usage.get(resource, 0) + 1
            self._active[key] = ActiveTask(
                task_type=task_type,
                task_id=task_id,
                resources=requested,
                started_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        try:
            yield
        finally:
            with self._condition:
                reservation = self._active.pop(key, None)
                if reservation is not None:
                    for resource in reservation.resources:
                        remaining = self._usage.get(resource, 0) - 1
                        if remaining > 0:
                            self._usage[resource] = remaining
                        else:
                            self._usage.pop(resource, None)
                self._condition.notify_all()

    def snapshot(self) -> dict[str, object]:
        """Return non-sensitive task/resource state for local diagnostics."""

        with self._condition:
            return {
                "accepting": not self._closed,
                "resources": dict(self._usage),
                "active": [
                    {
                        "taskType": item.task_type,
                        "taskId": item.task_id,
                        "resources": list(item.resources),
                        "startedAt": item.started_at,
                    }
                    for item in self._active.values()
                ],
            }

    def shutdown(self) -> None:
        """Reject queued acquisitions while allowing active holders to finish."""

        with self._condition:
            self._closed = True
            self._condition.notify_all()
