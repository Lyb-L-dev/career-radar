"""FastAPI 管理端使用的 SQLite 查询与前端字段适配层。

爬虫核心继续使用 ``JobPosting`` 和原有表结构；本模块只负责把数据转换为
React 管理端的稳定 JSON 形状，并保存收藏/已投递等纯本地用户状态。
"""

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
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .config import load_settings
from .models import CompanyConfig, JobPosting, ProfileFitLevel, Settings
from .storage import JobStorage

_UNSET = object()


def company_id(name: str) -> str:
    """公司名在 YAML 中唯一，因此可生成无需额外数据库列的稳定前端 ID。"""

    digest = hashlib.sha256(name.casefold().strip().encode("utf-8")).hexdigest()[:12]
    return f"c-{digest}"


_SECTION_TITLES = {"岗位职责", "职位描述", "任职要求", "任职资格", "岗位要求"}
_STANDALONE_NUMBER = re.compile(
    r"^(?:[（(]?(?:\d{1,3}|[一二三四五六七八九十]+)[）)]?[、.．:：]?)$"
)
_PUNCTUATION_ONLY = re.compile(r"^[，。；：、,.!?！？;:（）()【】\[\]·…—～~]+$")


def _coalesced_lines(value: str | None) -> list[str]:
    """合并网页排版产生的孤立序号、标点和被拆开的句子。

    该处理只用于 Web 展示，SQLite 中的完整 JD 原文保持不变。
    """

    if not value:
        return []
    result: list[str] = []
    pending_prefix = ""
    for raw in value.splitlines():
        line = raw.strip().lstrip("-• ")
        if not line:
            continue
        if _STANDALONE_NUMBER.fullmatch(line):
            pending_prefix += line
            if line[-1].isdigit() or line.endswith((")", "）")):
                pending_prefix += " "
            continue
        if _PUNCTUATION_ONLY.fullmatch(line):
            if result:
                result[-1] += line
            else:
                pending_prefix += line
            continue
        if result and line[0] in "，。；：、,.!?！？;:）)】]":
            result[-1] += line
            continue
        result.append(f"{pending_prefix}{line}")
        pending_prefix = ""
    if pending_prefix and result:
        result[-1] += pending_prefix
    return result


def _lines(value: str | None, limit: int = 80) -> list[str]:
    """把 JD 段落转成列表，过滤纯章节标题并修复碎片行。"""

    result: list[str] = []
    for line in _coalesced_lines(value):
        if line.strip("【】[] ") in _SECTION_TITLES:
            continue
        result.append(line)
        if len(result) >= limit:
            break
    return result


def _display_text(value: str | None) -> str:
    """生成适合 ``white-space: pre-wrap`` 展示的 JD，原始值仍保存在数据库。"""

    return "\n".join(_coalesced_lines(value))


_INDUSTRY_LABELS = {
    "internet": "互联网",
    "gaming": "游戏",
    "pet": "宠物",
    "enterprise_software": "企业软件",
    "ai_data": "AI 与数据",
    "iot": "物联网",
    "fintech": "金融科技",
    "telecom": "通信",
    "energy": "能源电力",
    "manufacturing": "智能制造",
    "consumer": "消费品",
    "other": "其他",
}


def _job_type(job: JobPosting) -> str:
    if job.record_type == "notice":
        return "notice"
    text = (job.recruitment_type or "").casefold()
    if "实习" in text or "intern" in text:
        return "internship"
    if any(term in text for term in ("校招", "校园", "应届", "管培", "campus", "graduate")):
        return "campus"
    return "fulltime"


def _short_text(value: str, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact if len(compact) <= limit else f"{compact[:limit].rstrip()}…"


class WebRepository:
    """围绕单个 ``config.yaml`` 的只读业务查询和少量 Web 状态写入。"""

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
        status = "updated" if latest_event == "updated" else "new"
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
                """
                SELECT j.*,
                       COALESCE(s.is_favorite, 0) AS is_favorite,
                       COALESCE(s.is_applied, 0) AS is_applied,
                       COALESCE(s.not_interested, 0) AS not_interested,
                       (SELECT h.event_type FROM job_history h
                        WHERE h.entity_key = j.entity_key ORDER BY h.id DESC LIMIT 1) AS latest_event
                FROM jobs j
                LEFT JOIN web_job_state s ON s.entity_key = j.entity_key
                ORDER BY j.updated_at DESC
                """
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
                """
                SELECT j.*,
                       COALESCE(s.is_favorite, 0) AS is_favorite,
                       COALESCE(s.is_applied, 0) AS is_applied,
                       COALESCE(s.not_interested, 0) AS not_interested,
                       (SELECT h.event_type FROM job_history h
                        WHERE h.entity_key = j.entity_key ORDER BY h.id DESC LIMIT 1) AS latest_event
                FROM jobs j
                LEFT JOIN web_job_state s ON s.entity_key = j.entity_key
                WHERE j.title LIKE ? ESCAPE '\\'
                   OR j.company LIKE ? ESCAPE '\\'
                   OR j.payload_json LIKE ? ESCAPE '\\'
                ORDER BY j.updated_at DESC
                LIMIT ?
                """,
                (pattern, pattern, pattern, limit),
            ).fetchall()
        return [self._job_json(row, settings=settings) for row in rows]

    def get_job(self, entity_key: str) -> dict[str, Any] | None:
        settings = self.settings
        with self.transaction(settings) as connection:
            row = connection.execute(
                """
                SELECT j.*,
                       COALESCE(s.is_favorite, 0) AS is_favorite,
                       COALESCE(s.is_applied, 0) AS is_applied,
                       COALESCE(s.not_interested, 0) AS not_interested,
                       (SELECT h.event_type FROM job_history h
                        WHERE h.entity_key = j.entity_key ORDER BY h.id DESC LIMIT 1) AS latest_event
                FROM jobs j LEFT JOIN web_job_state s ON s.entity_key = j.entity_key
                WHERE j.entity_key = ?
                """,
                (entity_key,),
            ).fetchone()
            if row is None:
                return None
            history = self._history(connection, entity_key)
        return self._job_json(row, settings=settings, history=history)

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

    def list_companies(self) -> list[dict[str, Any]]:
        settings = self.settings
        with self.transaction() as connection:
            stats = {
                row["company"]: row
                for row in connection.execute(
                    """
                    SELECT company, COUNT(*) AS job_count,
                           MAX(last_seen_at) AS last_scan_at
                    FROM jobs GROUP BY company
                    """
                ).fetchall()
            }
        render_mode = {"auto": "auto", "never": "static", "always": "dynamic"}[
            settings.crawler.render_mode
        ]
        runs = self.list_runs()
        config_added_at = datetime.fromtimestamp(
            self.config_path.stat().st_ctime,
            ZoneInfo(settings.app.timezone),
        ).isoformat(timespec="seconds")
        result = []
        for company in settings.companies:
            stat = stats.get(company.name)
            run_results: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for run in runs:
                company_run = next(
                    (
                        item
                        for item in run.get("companies", [])
                        if item.get("companyName") == company.name
                    ),
                    None,
                )
                if company_run is not None:
                    run_results.append((run, company_run))
            latest_run, latest_company_run = run_results[0] if run_results else ({}, {})
            latest_status = latest_company_run.get("status")
            last_error = latest_company_run.get("error")
            consecutive_failures = 0
            for _run, company_run in run_results:
                if company_run.get("status") != "failed":
                    break
                consecutive_failures += 1
            if not company.enabled:
                status = "paused"
            elif latest_status in {"running", "waiting"} and latest_run.get("status") in {
                "pending",
                "running",
                "stopping",
            }:
                status = "scanning"
            elif latest_status == "failed":
                status = "robots_blocked" if "robots" in (last_error or "").casefold() else "request_failed"
            elif (
                latest_status == "skipped"
                and latest_company_run.get("skipReason") == "user_stop"
            ):
                status = "active" if stat and stat["last_scan_at"] else "pending_verification"
            elif latest_status == "skipped":
                status = "robots_blocked" if "robots" in (last_error or "").casefold() else "structure_error"
            elif latest_status == "success" or (stat and stat["last_scan_at"]):
                status = "active"
            else:
                status = "pending_verification"
            last_scan_at = (
                latest_run.get("finishedAt")
                or latest_run.get("startedAt")
                or (stat["last_scan_at"] if stat else None)
            )
            result.append(
                {
                    "id": company_id(company.name),
                    "name": company.name,
                    "shortName": company.name.split()[0],
                    "website": company.url,
                    "careersUrl": company.url,
                    "industry": _INDUSTRY_LABELS[company.industry_category.value],
                    "industryCategory": company.industry_category.value,
                    "companyType": company.company_type.value,
                    "province": company.province,
                    "city": company.city,
                    "priority": company.priority.value,
                    "monitorMode": company.monitor_mode.value,
                    "governmentHonors": company.government_honors,
                    "evidenceUrls": company.evidence_urls,
                    "status": status,
                    "renderMode": render_mode,
                    "robotsStatus": "blocked" if status == "robots_blocked" else "unknown",
                    "lastScanAt": last_scan_at,
                    "recentJobCount": stat["job_count"] if stat else 0,
                    "consecutiveFailures": consecutive_failures,
                    "maxPages": company.max_pages or settings.crawler.max_pages_per_company,
                    "recruitmentChannel": company.recruitment_channel.value,
                    "parentCompany": company.parent_company,
                    "attributionKeywords": company.attribution_keywords,
                    "enabled": company.enabled,
                    "note": company.notes,
                    "discoveredEntry": company.url,
                    "lastError": last_error,
                    "addedAt": config_added_at,
                }
            )
        return result

    def find_company(self, identifier: str) -> tuple[int, CompanyConfig] | None:
        for index, company in enumerate(self.settings.companies):
            if company_id(company.name) == identifier:
                return index, company
        return None

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
                    jobs_found, status, error, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    int(event.get("jobsFound") or 0),
                    event.get("status") or "failed",
                    event.get("error"),
                    event.get("fetchedAt")
                    or datetime.now(ZoneInfo(self.settings.app.timezone)).isoformat(
                        timespec="seconds"
                    ),
                ),
            )

    def list_company_pages(
        self,
        identifier: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """返回企业最近的真实页面抓取记录，包含失败页供诊断。"""

        labels = {
            "no_jobs": "非招聘页",
            "career_home": "招聘入口页",
            "job_list": "招聘列表页",
            "job_detail": "职位详情页",
            "mixed": "招聘混合页",
        }
        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT * FROM web_page_visits
                WHERE company_id = ? ORDER BY id DESC LIMIT ?
                """,
                (identifier, limit),
            ).fetchall()
        return [
            {
                "runId": row["run_id"],
                "url": row["final_url"],
                "requestedUrl": row["requested_url"],
                "pageType": labels.get(row["page_type"], "抓取失败页"),
                "method": row["method"],
                "httpStatus": row["http_status"],
                "contentLength": row["content_length"],
                "llmExtracted": bool(row["llm_extracted"]),
                "jobsFound": row["jobs_found"],
                "status": row["status"],
                "error": row["error"],
                "fetchedAt": row["fetched_at"],
            }
            for row in rows
        ]

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
