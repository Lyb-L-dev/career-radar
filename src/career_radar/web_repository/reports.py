"""日报邮件投递状态。"""

from __future__ import annotations

from typing import Any


class ReportsMixin:
    def report_event_summaries(self) -> dict[str, dict[str, Any]]:
        """一次读取真实历史事件，返回按日期去重后的日报统计与岗位 ID。"""

        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT
                    substr(detected_at, 1, 10) AS report_date,
                    event_type,
                    entity_key,
                    json_extract(payload_json, '$.profile_fit_level') AS profile_fit_level
                FROM job_history
                ORDER BY detected_at ASC, id ASC
                """
            ).fetchall()

        summaries: dict[str, dict[str, Any]] = {}
        seen: dict[str, dict[str, set[str]]] = {}
        for row in rows:
            report_date = row["report_date"]
            summary = summaries.setdefault(
                report_date,
                {
                    "newJobIds": [],
                    "updatedJobIds": [],
                    "highMatchJobIds": [],
                },
            )
            date_seen = seen.setdefault(
                report_date,
                {"new": set(), "updated": set(), "high": set()},
            )
            event_type = row["event_type"]
            entity_key = row["entity_key"]
            event_seen = date_seen[event_type]
            if entity_key not in event_seen:
                event_seen.add(entity_key)
                summary[f"{event_type}JobIds"].append(entity_key)
            if row["profile_fit_level"] == "high" and entity_key not in date_seen["high"]:
                date_seen["high"].add(entity_key)
                summary["highMatchJobIds"].append(entity_key)
        return summaries

    def report_sent_dates(self) -> set[str]:
        """从真实运行记录中提取曾成功发送邮件的日期。"""

        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT substr(started_at, 1, 10) AS report_date
                FROM web_runs
                WHERE json_extract(payload_json, '$.emailStatus') = 'sent'
                """
            ).fetchall()
        return {row["report_date"] for row in rows if row["report_date"]}

    def report_email_states(self) -> dict[str, dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT report_date, event_count, sent_at
                FROM report_email_deliveries
                ORDER BY sent_at DESC
                """
            ).fetchall()
        return {
            row["report_date"]: {
                "eventCount": row["event_count"],
                "sentAt": row["sent_at"],
            }
            for row in rows
        }

    def record_report_email_delivery(
        self,
        report_date: str,
        event_count: int,
        sent_at: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO report_email_deliveries(report_date, event_count, sent_at)
                VALUES (?, ?, ?)
                ON CONFLICT(report_date) DO UPDATE SET
                    event_count = excluded.event_count,
                    sent_at = excluded.sent_at
                """,
                (report_date, event_count, sent_at),
            )
