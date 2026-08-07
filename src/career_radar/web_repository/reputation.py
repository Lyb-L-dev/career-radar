"""岗位口碑调查扫描与证据。"""

from __future__ import annotations

import json
from typing import Any


class ReputationMixin:
    def save_reputation_scan(self, payload: dict[str, Any]) -> None:
        """原子保存口碑任务和当前证据快照，便于前端轮询及服务重启恢复。"""

        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO job_reputation_scans(
                    scan_id, entity_key, status, payload_json,
                    started_at, updated_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scan_id) DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at,
                    finished_at = excluded.finished_at
                """,
                (
                    payload["id"],
                    payload["jobId"],
                    payload["status"],
                    json.dumps(payload, ensure_ascii=False),
                    payload["startedAt"],
                    payload["updatedAt"],
                    payload.get("finishedAt"),
                ),
            )
            connection.execute(
                "DELETE FROM job_reputation_evidence WHERE scan_id = ?",
                (payload["id"],),
            )
            for item in payload.get("evidence", []):
                connection.execute(
                    """
                    INSERT INTO job_reputation_evidence(
                        scan_id, evidence_id, platform, title, excerpt,
                        source_url, published_at, interaction_count, search_query
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["id"],
                        item["id"],
                        item["platform"],
                        item["title"],
                        item["excerpt"],
                        item.get("url"),
                        item.get("publishedAt"),
                        int(item.get("interactionCount") or 0),
                        item["searchQuery"],
                    ),
                )

    def list_reputation_scans(self) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM job_reputation_scans
                ORDER BY started_at DESC LIMIT 200
                """
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_reputation_scan(self, scan_id: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM job_reputation_scans WHERE scan_id = ?",
                (scan_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def latest_reputation_scan(self, entity_key: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM job_reputation_scans
                WHERE entity_key = ? ORDER BY started_at DESC LIMIT 1
                """,
                (entity_key,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

