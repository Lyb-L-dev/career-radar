"""Automation-center preview and explicit-confirmation tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from career_radar.automation import AutomationError, AutomationService


def _service(
    tmp_path: Path,
    calls: list[list[str]],
) -> AutomationService:
    config = tmp_path / "config.yaml"
    config.write_text("companies: []", encoding="utf-8")
    script = tmp_path / "scripts" / "manage_windows_task.ps1"
    script.parent.mkdir()
    script.write_text("# test script", encoding="utf-8")

    def runner(command, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(command)
        action = command[command.index("-Action") + 1]
        installed = action != "Remove"
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "installed": installed,
                    "taskName": AutomationService.TASK_NAME,
                    "state": "Ready" if installed else "not_installed",
                    "nextRunAt": "2026-07-28T08:00:00+08:00" if installed else None,
                    "lastRunAt": None,
                    "lastResult": None,
                },
                ensure_ascii=False,
            ),
            stderr="",
        )

    return AutomationService(
        config,
        runner=runner,
        system_name="Windows",
    )


def test_automation_preview_is_non_mutating_and_hides_local_paths(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    service = _service(tmp_path, calls)

    preview = service.preview("08:30")

    assert preview["supported"] is True
    assert preview["dailyRunTime"] == "08:30"
    assert calls == []
    assert str(tmp_path) not in json.dumps(preview, ensure_ascii=False)


def test_automation_install_and_remove_require_explicit_confirmation(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []
    service = _service(tmp_path, calls)

    with pytest.raises(AutomationError, match="确认"):
        service.install("08:00", confirmed=False)
    assert calls == []

    installed = service.install("08:00", confirmed=True)
    removed = service.remove("08:00", confirmed=True)

    assert installed["installed"] is True
    assert removed["installed"] is False
    assert [call[call.index("-Action") + 1] for call in calls] == [
        "Install",
        "Remove",
    ]


def test_automation_status_uses_read_only_status_action(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    service = _service(tmp_path, calls)

    status = service.status("08:00")

    assert status["installed"] is True
    assert calls[0][calls[0].index("-Action") + 1] == "Status"
