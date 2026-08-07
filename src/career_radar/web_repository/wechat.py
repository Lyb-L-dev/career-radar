"""微信公众号招聘账号、扫描与文章。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


class WechatMixin:
    def list_wechat_accounts(self, candidate_id: str) -> list[dict[str, Any]]:
        """返回某候选企业登记的公众号；账号标识是公开身份信息。"""

        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT * FROM company_wechat_accounts
                WHERE candidate_id = ?
                ORDER BY enabled DESC, updated_at DESC, account_name
                """,
                (candidate_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["enabled"] = bool(item["enabled"])
            item["attribution_keywords"] = json.loads(
                item.pop("attribution_keywords_json")
            )
            result.append(item)
        return result

    def get_wechat_account(self, account_id: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM company_wechat_accounts WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        item["attribution_keywords"] = json.loads(
            item.pop("attribution_keywords_json")
        )
        return item

    def save_wechat_account(self, account: dict[str, Any]) -> None:
        """新增或更新经过人工确认的公众号绑定。"""

        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO company_wechat_accounts(
                    account_id, candidate_id, account_name, account_identifier,
                    biz_id, scope, parent_company, attribution_keywords_json,
                    verification_status, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    account_name = excluded.account_name,
                    account_identifier = excluded.account_identifier,
                    biz_id = excluded.biz_id,
                    scope = excluded.scope,
                    parent_company = excluded.parent_company,
                    attribution_keywords_json = excluded.attribution_keywords_json,
                    verification_status = excluded.verification_status,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    account["account_id"],
                    account["candidate_id"],
                    account["account_name"],
                    account.get("account_identifier"),
                    account.get("biz_id"),
                    account["scope"],
                    account.get("parent_company"),
                    json.dumps(
                        account.get("attribution_keywords") or [],
                        ensure_ascii=False,
                    ),
                    account["verification_status"],
                    int(bool(account["enabled"])),
                    account["created_at"],
                    account["updated_at"],
                ),
            )

    def delete_wechat_account(self, account_id: str, candidate_id: str) -> bool:
        """删除账号绑定；历史文章保留并自动解除外键关联。"""

        with self.transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM company_wechat_accounts
                WHERE account_id = ? AND candidate_id = ?
                """,
                (account_id, candidate_id),
            )
        return cursor.rowcount == 1

    def save_wechat_scan(self, payload: dict[str, Any]) -> None:
        """持久化公众号扫描进度，服务重启后仍可查看最后结果。"""

        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO wechat_recruitment_scans(
                    scan_id, candidate_id, status, payload_json,
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
                    payload["candidateId"],
                    payload["status"],
                    json.dumps(payload, ensure_ascii=False),
                    payload["startedAt"],
                    payload["updatedAt"],
                    payload.get("finishedAt"),
                ),
            )

    def get_wechat_scan(self, scan_id: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM wechat_recruitment_scans WHERE scan_id = ?",
                (scan_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def latest_wechat_scan(self, candidate_id: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM wechat_recruitment_scans
                WHERE candidate_id = ?
                ORDER BY started_at DESC LIMIT 1
                """,
                (candidate_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def recover_interrupted_wechat_scans(self) -> int:
        """服务重启时把无法继续的进程内任务标记为中断。"""

        now = datetime.now(ZoneInfo(self.settings.app.timezone)).isoformat(
            timespec="seconds"
        )
        recovered = 0
        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT scan_id, payload_json
                FROM wechat_recruitment_scans
                WHERE status IN ('pending', 'running')
                """
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload_json"])
                payload["status"] = "interrupted"
                payload["updatedAt"] = now
                payload["finishedAt"] = now
                errors = payload.setdefault("errors", [])
                errors.append("服务重启，原公众号扫描已中断，可重新发起扫描")
                connection.execute(
                    """
                    UPDATE wechat_recruitment_scans
                    SET status = 'interrupted', payload_json = ?,
                        updated_at = ?, finished_at = ?
                    WHERE scan_id = ?
                    """,
                    (
                        json.dumps(payload, ensure_ascii=False),
                        now,
                        now,
                        row["scan_id"],
                    ),
                )
                recovered += 1
        return recovered

    def save_wechat_article(self, article: dict[str, Any]) -> str:
        """按候选企业+原文 URL 去重并检测正文或分类变化。"""

        with self.transaction() as connection:
            previous = connection.execute(
                """
                SELECT content_hash, classification, verification_status
                FROM wechat_recruitment_articles
                WHERE candidate_id = ? AND source_url = ?
                """,
                (article["candidate_id"], article["source_url"]),
            ).fetchone()
            event = "new"
            if previous is not None:
                event = (
                    "unchanged"
                    if (
                        previous["content_hash"] == article["content_hash"]
                        and previous["classification"] == article["classification"]
                        and previous["verification_status"]
                        == article["verification_status"]
                    )
                    else "updated"
                )
            connection.execute(
                """
                INSERT INTO wechat_recruitment_articles(
                    article_id, candidate_id, account_id, title, account_name,
                    account_identifier, biz_id, source_url, summary, content,
                    published_at, classification, verification_status, reason,
                    content_hash, source_id, imported_job_id,
                    first_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id, source_url) DO UPDATE SET
                    account_id = excluded.account_id,
                    title = excluded.title,
                    account_name = excluded.account_name,
                    account_identifier = excluded.account_identifier,
                    biz_id = excluded.biz_id,
                    summary = excluded.summary,
                    content = excluded.content,
                    published_at = excluded.published_at,
                    classification = excluded.classification,
                    verification_status = excluded.verification_status,
                    reason = excluded.reason,
                    content_hash = excluded.content_hash,
                    source_id = COALESCE(
                        excluded.source_id,
                        wechat_recruitment_articles.source_id
                    ),
                    imported_job_id = COALESCE(
                        excluded.imported_job_id,
                        wechat_recruitment_articles.imported_job_id
                    ),
                    updated_at = excluded.updated_at
                """,
                (
                    article["article_id"],
                    article["candidate_id"],
                    article.get("account_id"),
                    article["title"],
                    article.get("account_name"),
                    article.get("account_identifier"),
                    article.get("biz_id"),
                    article["source_url"],
                    article.get("summary"),
                    article["content"],
                    article.get("published_at"),
                    article["classification"],
                    article["verification_status"],
                    article["reason"],
                    article["content_hash"],
                    article.get("source_id"),
                    article.get("imported_job_id"),
                    article["first_seen_at"],
                    article["updated_at"],
                ),
            )
        return event

    def set_wechat_article_imports(
        self,
        article_id: str,
        *,
        source_id: str,
        imported_job_id: str | None,
    ) -> None:
        now = datetime.now(ZoneInfo(self.settings.app.timezone)).isoformat(timespec="seconds")
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE wechat_recruitment_articles
                SET source_id = ?, imported_job_id = COALESCE(?, imported_job_id),
                    updated_at = ?
                WHERE article_id = ?
                """,
                (source_id, imported_job_id, now, article_id),
            )

    def list_wechat_articles(
        self,
        candidate_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """管理端只返回文章摘要，不公开数据库字段或大段正文。"""

        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT article_id, candidate_id, account_id, title, account_name,
                       source_url, summary, published_at, classification,
                       verification_status, reason, source_id, imported_job_id,
                       first_seen_at, updated_at
                FROM wechat_recruitment_articles
                WHERE candidate_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (candidate_id, max(1, min(limit, 100))),
            ).fetchall()
        return [dict(row) for row in rows]

