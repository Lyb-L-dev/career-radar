"""Safe preview and explicit management of the local OS schedule."""

from __future__ import annotations

import json
import platform
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .public_errors import public_error_message

Runner = Callable[..., subprocess.CompletedProcess[str]]


class AutomationError(RuntimeError):
    """Scheduled-task status or mutation failed."""


class AutomationService:
    TASK_NAME = "Career Radar Daily Monitor"

    def __init__(
        self,
        config_path: Path,
        *,
        runner: Runner = subprocess.run,
        system_name: str | None = None,
    ) -> None:
        self.config_path = config_path.resolve()
        self.project_dir = self.config_path.parent
        self.script = self.project_dir / "scripts" / "manage_windows_task.ps1"
        self.runner = runner
        self.system_name = system_name or platform.system()

    def preview(self, daily_time: str) -> dict[str, Any]:
        self._validate_time(daily_time)
        supported = self.system_name == "Windows" and self.script.is_file()
        return {
            "supported": supported,
            "platform": self.system_name,
            "taskName": self.TASK_NAME,
            "dailyRunTime": daily_time,
            "startWhenAvailable": True,
            "allowOnBattery": True,
            "paidCallsRequireConfirmation": True,
            "message": (
                "将使用当前项目虚拟环境和 config.yaml，每天运行一次公开招聘监控。"
                if supported
                else "当前平台暂不支持从管理端安装，请继续使用 README 中的 cron 配置。"
            ),
        }

    @staticmethod
    def _validate_time(daily_time: str) -> None:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", daily_time):
            raise ValueError("每日运行时间格式无效")

    def _invoke(self, action: str, daily_time: str) -> dict[str, Any]:
        if self.system_name != "Windows" or not self.script.is_file():
            raise AutomationError("当前平台不支持从管理端管理计划任务")
        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.script),
            "-Action",
            action,
            "-DailyTime",
            daily_time,
            "-ConfigPath",
            str(self.config_path),
        ]
        completed = self.runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            raise AutomationError(
                public_error_message(
                    RuntimeError(completed.stderr or completed.stdout),
                    context="Windows 计划任务操作",
                )
            )
        try:
            payload = json.loads(completed.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise AutomationError("计划任务返回了无法识别的状态") from exc
        return {
            **self.preview(daily_time),
            **payload,
        }

    def status(self, daily_time: str) -> dict[str, Any]:
        preview = self.preview(daily_time)
        if not preview["supported"]:
            return {**preview, "installed": False, "state": "unsupported"}
        try:
            return self._invoke("Status", daily_time)
        except AutomationError as exc:
            return {
                **preview,
                "installed": False,
                "state": "unavailable",
                "message": str(exc),
            }

    def install(self, daily_time: str, *, confirmed: bool) -> dict[str, Any]:
        if not confirmed:
            raise AutomationError("请先确认创建 Windows 每日计划任务")
        self._validate_time(daily_time)
        return self._invoke("Install", daily_time)

    def remove(self, daily_time: str, *, confirmed: bool) -> dict[str, Any]:
        if not confirmed:
            raise AutomationError("请先确认移除 Windows 每日计划任务")
        self._validate_time(daily_time)
        return self._invoke("Remove", daily_time)
