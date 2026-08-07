"""基础连接、初始化、历史导入与系统状态。"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..config import load_settings
from ..models import JobPosting, Settings
from ..storage import JobStorage
from .common import company_id


class BaseWebRepository:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path).expanduser().resolve()

    @property
    def settings(self):  # type: ignore[no-untyped-def]
        """每次请求重新加载，使 Web 保存后的 YAML 无需重启即可生效。"""

        return load_settings(self.config_path)

    def initialize(self) -> None:
        JobStorage(self.settings.app.database_path).initialize()
        self._import_legacy_runs()

    def _import_legacy_runs(self) -> None:
        """首次启用 Web 时，把可核验的 CLI 岗位事件导入为历史运行摘要。

        旧 CLI 没有逐公司步骤回调，因此只导入 ``job_history`` 能证明的公司、
        新增/更新数与检测时间，并在日志中明确说明精度边界。
        """

        with self.transaction() as connection:
            if connection.execute("SELECT COUNT(*) FROM web_runs").fetchone()[0]:
                return
            rows = connection.execute(
                """
                SELECT detected_at, event_type, payload_json
                FROM job_history ORDER BY detected_at ASC, id ASC
                """
            ).fetchall()
            batches: dict[str, list[sqlite3.Row]] = {}
            for row in rows:
                batches.setdefault(row["detected_at"], []).append(row)

            for detected_at, batch in batches.items():
                jobs = [JobPosting.model_validate_json(row["payload_json"]) for row in batch]
                companies = list(dict.fromkeys(job.company for job in jobs))
                if not companies:
                    continue
                run_id = f"legacy-{hashlib.sha256(detected_at.encode('utf-8')).hexdigest()[:16]}"
                company_results = []
                for name in companies:
                    company_rows = [
                        (row, job)
                        for row, job in zip(batch, jobs, strict=True)
                        if job.company == name
                    ]
                    new_jobs = sum(row["event_type"] == "new" for row, _job in company_rows)
                    updated_jobs = sum(
                        row["event_type"] == "updated" for row, _job in company_rows
                    )
                    company_results.append(
                        {
                            "companyId": company_id(name),
                            "companyName": name,
                            "status": "success",
                            "steps": [
                                {
                                    "key": "legacy-summary",
                                    "label": "历史 CLI 事件导入",
                                    "status": "success",
                                    "message": "来自真实 SQLite 岗位事件；旧版未保存逐页步骤与耗时",
                                }
                            ],
                            "newJobs": new_jobs,
                            "updatedJobs": updated_jobs,
                        }
                    )
                payload = {
                    "id": run_id,
                    "code": f"CLI-{re.sub(r'[^0-9]', '', detected_at)[:14] or 'HISTORY'}",
                    "trigger": "manual",
                    "status": "completed",
                    "startedAt": detected_at,
                    "finishedAt": detected_at,
                    "durationMs": 0,
                    "totalCompanies": len(companies),
                    "finishedCompanies": len(companies),
                    "successCount": len(companies),
                    "skippedCount": 0,
                    "failedCount": 0,
                    "newJobs": sum(row["event_type"] == "new" for row in batch),
                    "updatedJobs": sum(row["event_type"] == "updated" for row in batch),
                    "emailStatus": "disabled",
                    "sendEmail": False,
                    "canStop": False,
                    "companies": company_results,
                    "logs": [
                        {
                            "time": detected_at,
                            "level": "INFO",
                            "message": "由旧版 CLI 的真实 SQLite 岗位事件导入；无事件的企业无法反推。",
                        }
                    ],
                }
                connection.execute(
                    """
                    INSERT OR IGNORE INTO web_runs(
                        run_id, status, payload_json, started_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        payload["status"],
                        json.dumps(payload, ensure_ascii=False),
                        detected_at,
                        detected_at,
                    ),
                )

    def _connect(self, settings: Settings | None = None) -> sqlite3.Connection:
        settings = settings or self.settings
        JobStorage(settings.app.database_path).initialize()
        connection = sqlite3.connect(settings.app.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def transaction(self, settings: Settings | None = None) -> Iterator[sqlite3.Connection]:
        """提交或回滚后显式关闭连接，保证 Windows 下可立即备份数据库。"""

        connection = self._connect(settings)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _history(self, connection: sqlite3.Connection, entity_key: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT id, event_type, detected_at
            FROM job_history WHERE entity_key = ? ORDER BY id DESC LIMIT 50
            """,
            (entity_key,),
        ).fetchall()
        history = []
        for row in rows:
            event = row["event_type"]
            history.append(
                {
                    "id": f"h-{row['id']}",
                    "time": row["detected_at"],
                    "type": "discovered" if event == "new" else "jd_updated",
                    "summary": "首次发现该岗位" if event == "new" else "岗位结构化内容发生变化",
                }
            )
        return history

    def database_stats(self) -> dict[str, Any]:
        settings = self.settings
        with self.transaction() as connection:
            jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            history = connection.execute("SELECT COUNT(*) FROM job_history").fetchone()[0]
        reports = len(list(settings.app.output_dir.glob("*-jobs.md")))
        logs = len(list(settings.app.log_dir.glob("*.log*")))
        size = settings.app.database_path.stat().st_size if settings.app.database_path.exists() else 0
        return {
            "jobs": jobs,
            "history": history,
            "reports": reports,
            "logs": logs,
            "sizeMb": round(size / 1024 / 1024, 2),
        }

    def notification_states(self) -> dict[str, tuple[bool, bool]]:
        """返回 ``通知 ID -> (已读, 已删除)``，通知正文仍由真实岗位/运行数据生成。"""

        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT notification_id, is_read, is_dismissed FROM web_notification_state"
            ).fetchall()
        return {
            row["notification_id"]: (bool(row["is_read"]), bool(row["is_dismissed"]))
            for row in rows
        }

    def set_notification_state(
        self,
        notification_ids: list[str],
        *,
        is_read: bool | None = None,
        is_dismissed: bool | None = None,
    ) -> None:
        now = datetime.now(ZoneInfo(self.settings.app.timezone)).isoformat(timespec="seconds")
        with self.transaction() as connection:
            for notification_id in notification_ids:
                connection.execute(
                    """
                    INSERT INTO web_notification_state(notification_id, updated_at)
                    VALUES (?, ?) ON CONFLICT(notification_id) DO NOTHING
                    """,
                    (notification_id, now),
                )
                if is_read is not None:
                    connection.execute(
                        "UPDATE web_notification_state SET is_read = ?, updated_at = ? WHERE notification_id = ?",
                        (int(is_read), now, notification_id),
                    )
                if is_dismissed is not None:
                    connection.execute(
                        "UPDATE web_notification_state SET is_dismissed = ?, updated_at = ? WHERE notification_id = ?",
                        (int(is_dismissed), now, notification_id),
                    )

    def environment(self) -> dict[str, Any]:
        settings = self.settings
        stats = self.database_stats()
        return {
            "python": f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "chromium": "已安装" if Path.home().joinpath("AppData/Local/ms-playwright").exists() else "按需检测",
            "dbJobCount": stats["jobs"],
            "jobHistoryCount": stats["history"],
            "emailEnabled": settings.smtp.enabled,
        }
