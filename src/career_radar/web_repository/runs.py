"""运行摘要与页面访问记录。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .common import company_id


class RunsMixin:
    def save_run(self, payload: dict[str, Any]) -> None:
        now = datetime.now(ZoneInfo(self.settings.app.timezone)).isoformat(timespec="seconds")
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO web_runs(run_id, status, payload_json, started_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    payload["id"],
                    payload["status"],
                    json.dumps(payload, ensure_ascii=False),
                    payload["startedAt"],
                    now,
                ),
            )

    def save_page_visit(
        self,
        run_id: str,
        company_name: str,
        event: dict[str, Any],
    ) -> None:
        """页面完成或失败后立即写入审计表，不等待整轮扫描结束。"""

        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO web_page_visits(
                    run_id, company_id, company_name, requested_url, final_url,
                    page_type, method, http_status, content_length, llm_extracted,
                    cache_status, jobs_found, status, error, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    company_id(company_name),
                    company_name,
                    event.get("requestedUrl") or event.get("currentPage") or "",
                    event.get("finalUrl") or event.get("currentPage") or "",
                    event.get("pageType"),
                    event.get("method") or "requests",
                    event.get("httpStatus"),
                    int(event.get("contentLength") or 0),
                    int(bool(event.get("llmExtracted"))),
                    event.get("cacheStatus"),
                    int(event.get("jobsFound") or 0),
                    event.get("status") or "failed",
                    event.get("error"),
                    event.get("fetchedAt")
                    or datetime.now(ZoneInfo(self.settings.app.timezone)).isoformat(
                        timespec="seconds"
                    ),
                ),
            )

    def list_runs(self) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM web_runs ORDER BY started_at DESC LIMIT 200"
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM web_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

