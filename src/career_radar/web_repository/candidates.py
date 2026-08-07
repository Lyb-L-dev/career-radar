"""候选企业库状态与来源管理。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .common import _UNSET


class CandidatesMixin:
    def candidate_states(self) -> dict[str, dict[str, Any]]:
        """读取候选企业的人工审批状态；静态官方名单本身不写入数据库。"""

        with self.transaction() as connection:
            rows = connection.execute("SELECT * FROM company_candidate_state").fetchall()
        return {row["candidate_id"]: dict(row) for row in rows}

    def set_candidate_state(
        self,
        candidate_ids: list[str],
        *,
        decision: str,
        official_website: str | None | object = _UNSET,
        careers_url: str | None | object = _UNSET,
        company_type: str | None | object = _UNSET,
        industry_category: str | None | object = _UNSET,
        recruitment_channel_status: str | object = _UNSET,
        parent_company: str | None | object = _UNSET,
        group_recruitment_url: str | None | object = _UNSET,
        attribution_keywords: list[str] | None | object = _UNSET,
        note: str | None | object = _UNSET,
    ) -> None:
        """幂等保存审批与招聘渠道；未传字段保留，显式 ``None`` 可清空。"""

        now = datetime.now(ZoneInfo(self.settings.app.timezone)).isoformat(timespec="seconds")
        with self.transaction() as connection:
            for candidate_id in candidate_ids:
                previous = connection.execute(
                    "SELECT * FROM company_candidate_state WHERE candidate_id = ?",
                    (candidate_id,),
                ).fetchone()
                values = {
                    "official_website": official_website,
                    "careers_url": careers_url,
                    "company_type": company_type,
                    "industry_category": industry_category,
                    "recruitment_channel_status": recruitment_channel_status,
                    "parent_company": parent_company,
                    "group_recruitment_url": group_recruitment_url,
                    "attribution_keywords_json": (
                        json.dumps(attribution_keywords, ensure_ascii=False)
                        if attribution_keywords is not _UNSET
                        and attribution_keywords is not None
                        else attribution_keywords
                    ),
                    "note": note,
                }
                for key in values:
                    if values[key] is _UNSET:
                        values[key] = previous[key] if previous is not None else None
                if values["recruitment_channel_status"] is None:
                    values["recruitment_channel_status"] = "official_site_pending"
                connection.execute(
                    """
                    INSERT INTO company_candidate_state(
                        candidate_id, decision, official_website, careers_url,
                        company_type, industry_category, recruitment_channel_status,
                        parent_company, group_recruitment_url,
                        attribution_keywords_json, note, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(candidate_id) DO UPDATE SET
                        decision = excluded.decision,
                        official_website = excluded.official_website,
                        careers_url = excluded.careers_url,
                        company_type = excluded.company_type,
                        industry_category = excluded.industry_category,
                        recruitment_channel_status = excluded.recruitment_channel_status,
                        parent_company = excluded.parent_company,
                        group_recruitment_url = excluded.group_recruitment_url,
                        attribution_keywords_json = excluded.attribution_keywords_json,
                        note = excluded.note,
                        updated_at = excluded.updated_at
                    """,
                    (
                        candidate_id,
                        decision,
                        values["official_website"],
                        values["careers_url"],
                        values["company_type"],
                        values["industry_category"],
                        values["recruitment_channel_status"],
                        values["parent_company"],
                        values["group_recruitment_url"],
                        values["attribution_keywords_json"],
                        values["note"],
                        now,
                    ),
                )

    def list_candidate_sources(self, candidate_id: str) -> list[dict[str, Any]]:
        """按时间倒序返回人工登记的招聘来源，不读取或暴露本地文件。"""

        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT source_id, candidate_id, source_kind, verification_status,
                       material_type, title, source_url, content, published_at,
                       parent_company, imported_job_id, created_at, updated_at
                FROM company_recruitment_sources
                WHERE candidate_id = ?
                ORDER BY created_at DESC, source_id DESC
                """,
                (candidate_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_candidate_source(self, source: dict[str, Any]) -> None:
        """保存一条人工核验来源；第三方线索与官方证据由调用层严格区分。"""

        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO company_recruitment_sources(
                    source_id, candidate_id, source_kind, verification_status,
                    material_type, title, source_url, content, published_at,
                    parent_company, imported_job_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    verification_status = excluded.verification_status,
                    material_type = excluded.material_type,
                    title = excluded.title,
                    source_url = excluded.source_url,
                    content = excluded.content,
                    published_at = excluded.published_at,
                    parent_company = excluded.parent_company,
                    imported_job_id = COALESCE(
                        excluded.imported_job_id,
                        company_recruitment_sources.imported_job_id
                    ),
                    updated_at = excluded.updated_at
                """,
                (
                    source["source_id"],
                    source["candidate_id"],
                    source["source_kind"],
                    source["verification_status"],
                    source["material_type"],
                    source["title"],
                    source.get("source_url"),
                    source.get("content"),
                    source.get("published_at"),
                    source.get("parent_company"),
                    source.get("imported_job_id"),
                    source["created_at"],
                    source["updated_at"],
                ),
            )

    def set_candidate_source_imported_job(
        self,
        source_id: str,
        entity_key: str,
    ) -> None:
        """记录人工材料已进入招聘通知列表，重复提交时可安全阻止。"""

        now = datetime.now(ZoneInfo(self.settings.app.timezone)).isoformat(timespec="seconds")
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE company_recruitment_sources
                SET imported_job_id = ?, updated_at = ?
                WHERE source_id = ?
                """,
                (entity_key, now, source_id),
            )

