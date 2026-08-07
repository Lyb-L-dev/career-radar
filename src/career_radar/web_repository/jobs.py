"""岗位查询、搜索、相似度与用户状态。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from ..embeddings import (
    PROVIDER_NAME,
    SIMILAR_JOB_THRESHOLD,
    VECTOR_DIMENSION,
    cosine_similarity,
    feature_hash_vector,
)
from ..models import JobPosting, ProfileFitLevel, Settings
from ..storage import JobStorage
from .common import (
    JOB_SELECT,
    _display_text,
    _job_type,
    _lines,
    _short_text,
    company_id,
)


class JobsMixin:
    def _job_json(
        self,
        row: sqlite3.Row,
        *,
        settings: Settings,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        job = JobPosting.model_validate_json(row["payload_json"])
        configured_company = next(
            (company for company in settings.companies if company.name == job.company),
            None,
        )
        company_type = configured_company.company_type.value if configured_company else "other"
        industry_category = (
            configured_company.industry_category.value if configured_company else "other"
        )
        requirement_lines = _lines(job.requirements)
        description_lines = _lines(job.description)
        candidate_skills = settings.candidate.skills
        jd_haystack = f"{job.description}\n{job.requirements or ''}".casefold()
        has_skills = [skill for skill in candidate_skills if skill.casefold() in jd_haystack]
        contact_email = None
        if job.contact_email:
            contact_email = job.contact_email
        elif job.apply_url and job.apply_url.casefold().startswith("mailto:"):
            contact_email = job.apply_url[7:].split("?", 1)[0]
        apply_method = job.application_method or (
            f"发送简历至 {contact_email}"
            if contact_email
            else ("通过官网申请链接投递" if job.apply_url else "请查看职位来源页面确认投递方式")
        )
        host = urlsplit(job.source_url).netloc or "企业官网"
        latest_event = row["latest_event"] or "new"
        current_update_ignored = (
            latest_event == "updated"
            and row["ignored_content_hash"] == row["content_hash"]
        )
        status = (
            "ignored"
            if current_update_ignored
            else ("updated" if latest_event == "updated" else "new")
        )
        compact_history = history if history is not None else [
            {
                "id": f"latest-{row['entity_key']}",
                "time": row["updated_at"] if latest_event == "updated" else row["first_seen_at"],
                "type": "jd_updated" if latest_event == "updated" else "discovered",
                "summary": (
                    f"{job.company} · {job.title} 的岗位信息已更新"
                    if latest_event == "updated"
                    else f"首次发现 {job.company} · {job.title}"
                ),
            }
        ]
        profile_level = job.profile_fit_level.value
        advice = {
            ProfileFitLevel.HIGH.value: "岗位与当前画像高度相关，建议优先核验有效期并准备针对性材料。",
            ProfileFitLevel.MEDIUM.value: "存在可补足差距，建议根据任职要求完善项目证据后投递。",
            ProfileFitLevel.LOW.value: "与当前目标或能力差距较大，可低优先级保留。",
            ProfileFitLevel.UNKNOWN.value: "公开信息或个人画像不足，建议人工阅读完整 JD。",
        }[profile_level]
        tags = [item for item in (job.recruitment_type, job.target_graduates) if item]
        if job.is_2026_target:
            tags.append("2026 届")
        if not job.jd_complete:
            tags.append("JD 不完整")

        return {
            "id": row["entity_key"],
            "title": job.title,
            "companyId": company_id(job.company),
            "companyName": job.company,
            "companyType": company_type,
            "companyIndustry": industry_category,
            "companyProvince": configured_company.province if configured_company else None,
            "companyCity": configured_company.city if configured_company else None,
            "companyPriority": (
                configured_company.priority.value if configured_company else "medium"
            ),
            "recordType": job.record_type,
            "city": job.location or "地点未提供",
            "type": _job_type(job),
            "status": status,
            "gradYearMatch": job.match_level.value,
            "abilityMatch": profile_level,
            "difficulty": job.difficulty_score,
            "isFavorite": bool(row["is_favorite"]),
            "isApplied": bool(row["is_applied"]),
            "notInterested": bool(row["not_interested"]),
            "hasApplyUrl": bool(job.apply_url),
            "applyUrl": job.apply_url,
            "sourceUrl": job.source_url,
            "publishedAt": job.published_at,
            "firstSeenAt": row["first_seen_at"],
            "lastUpdatedAt": row["updated_at"],
            "recommendReason": job.profile_fit_reason,
            "highlyRecommended": job.match_level.value == "high" and profile_level == "high",
            "tags": list(dict.fromkeys(tags)),
            "overview": _short_text(job.description),
            "responsibilities": description_lines,
            "requirements": requirement_lines,
            "plusPoints": [line for line in requirement_lines if "优先" in line],
            "locationDetail": job.location or "官网未提供具体办公地点",
            "applyMethod": apply_method,
            "jdText": _display_text(job.description),
            "jdComplete": job.jd_complete,
            "jdIncompleteReason": job.jd_incomplete_reason,
            "contactEmail": contact_email,
            "analysis": {
                "conclusion": job.profile_fit_reason,
                "hasSkills": has_skills,
                # 不从关键词反推“缺失技能”，避免重现 LLM 把 JD 技能误算为候选人技能的问题。
                "missingSkills": [],
                "suggestions": [job.difficulty_reason] if job.difficulty_reason else [],
                "advice": advice,
            },
            "difficultyFactors": [
                {
                    "label": "公开 JD 门槛与个人画像差距",
                    "level": job.difficulty_level.value.replace("very_high", "高").replace("high", "高").replace("medium", "中").replace("low", "低"),
                    "note": job.difficulty_reason,
                }
            ],
            "source": {
                "site": host,
                "page": job.source_url,
                "method": "公开页面抓取 + LLM 结构化提取",
                "urlVerified": True,
                "lastVerifiedAt": row["last_seen_at"],
            },
            "history": compact_history,
        }

    def list_jobs(self) -> list[dict[str, Any]]:
        settings = self.settings
        with self.transaction(settings) as connection:
            rows = connection.execute(
                f"{JOB_SELECT} ORDER BY j.updated_at DESC"
            ).fetchall()
        return [self._job_json(row, settings=settings) for row in rows]

    def search_jobs(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """在 SQLite 中筛选岗位，避免搜索时反序列化完整岗位表。"""

        # 转义 LIKE 的通配符，使用户输入的 ``%`` 和 ``_`` 按普通字符搜索。
        escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        settings = self.settings
        with self.transaction(settings) as connection:
            rows = connection.execute(
                f"{JOB_SELECT} "
                "WHERE j.title LIKE ? ESCAPE '\\' "
                "OR j.company LIKE ? ESCAPE '\\' "
                "OR j.payload_json LIKE ? ESCAPE '\\' "
                "ORDER BY j.updated_at DESC "
                "LIMIT ?",
                (pattern, pattern, pattern, limit),
            ).fetchall()
        return [self._job_json(row, settings=settings) for row in rows]

    def get_job(self, entity_key: str) -> dict[str, Any] | None:
        settings = self.settings
        with self.transaction(settings) as connection:
            row = connection.execute(
                f"{JOB_SELECT} WHERE j.entity_key = ?",
                (entity_key,),
            ).fetchone()
            if row is None:
                return None
            history = self._history(connection, entity_key)
        return self._job_json(row, settings=settings, history=history)

    def similar_jobs(self, job_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """按本地语义向量返回与指定岗位最相似的岗位，结果带相似度分数。"""

        settings = self.settings
        storage = JobStorage(settings.app.database_path)
        storage.ensure_job_embeddings(
            PROVIDER_NAME,
            VECTOR_DIMENSION,
            feature_hash_vector,
        )
        vectors = storage.load_job_embeddings()
        target = vectors.get(job_id)
        if target is None:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for job in self.list_jobs():
            vector = vectors.get(job["id"])
            if vector is None or job["id"] == job_id:
                continue
            score = cosine_similarity(target, vector)
            if score >= SIMILAR_JOB_THRESHOLD:
                scored.append((score, job))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {**job, "similarity": round(score, 4)}
            for score, job in scored[:limit]
        ]

    def set_job_state(self, entity_keys: list[str], field: str, value: bool) -> None:
        columns = {
            "favorite": "is_favorite",
            "applied": "is_applied",
            "not_interested": "not_interested",
        }
        column = columns[field]
        now = datetime.now(ZoneInfo(self.settings.app.timezone)).isoformat(timespec="seconds")
        with self.transaction() as connection:
            for entity_key in entity_keys:
                exists = connection.execute(
                    "SELECT 1 FROM jobs WHERE entity_key = ?", (entity_key,)
                ).fetchone()
                if exists is None:
                    continue
                connection.execute(
                    """
                    INSERT INTO web_job_state(entity_key, updated_at)
                    VALUES (?, ?)
                    ON CONFLICT(entity_key) DO NOTHING
                    """,
                    (entity_key, now),
                )
                connection.execute(
                    f"UPDATE web_job_state SET {column} = ?, updated_at = ? WHERE entity_key = ?",
                    (int(value), now, entity_key),
                )

    def ignore_job_update(self, entity_key: str) -> bool:
        """仅忽略岗位当前内容版本；后续内容变化会自动恢复为“已更新”。"""

        now = datetime.now(ZoneInfo(self.settings.app.timezone)).isoformat(timespec="seconds")
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT content_hash FROM jobs WHERE entity_key = ?",
                (entity_key,),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                """
                INSERT INTO web_job_state(
                    entity_key, ignored_content_hash, updated_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(entity_key) DO UPDATE SET
                    ignored_content_hash = excluded.ignored_content_hash,
                    updated_at = excluded.updated_at
                """,
                (entity_key, row["content_hash"], now),
            )
        return True

