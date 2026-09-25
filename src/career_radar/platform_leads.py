"""BOSS job leads: offline import, provenance, and explainable triage.

These records stay outside the official-job tables and notification pipeline.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .models import CandidateProfile

_BOSS_HOSTS = {"zhipin.com", "www.zhipin.com"}
_JOB_PATH = re.compile(r"^/job_detail/([A-Za-z0-9_-]{1,128})\.html$")
_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_FOCUS = (
    "fde",
    "forward deployed",
    "ai应用",
    "ai 应用",
    "大模型应用",
    "agent工程师",
    "agent 工程师",
    "智能体",
    "llm应用",
    "llm 应用",
    "ai工程师",
    "ai 工程师",
)
_AI_CONTEXT = ("人工智能", "大模型", "llm", "agent", "智能体", "ai应用", "ai 应用")
_ENGINEERING = ("开发", "研发", "工程", "python", "编程", "代码", "api", "部署", "系统集成")
_EARLY = ("应届", "校招", "校园", "在校", "实习", "毕业生")
_JUNIOR = ("经验不限", "不限经验", "1年以内", "一年以内", "0-1年", "0—1年")
_SENIOR = re.compile(r"(?:3\s*[-~—至]\s*5|[3-9]\s*年(?:以上|及以上)|至少\s*[3-9]\s*年)")
_EXPLICIT_SCHOOL = re.compile(
    r"(?<!不)(?<!无)(?<!没有)(?:仅限|必须|要求|只招|限)\s*(?:985|211|双一流)"
)
_LOGIN_MARKERS = ("登录查看完整内容", "安全验证", "请先登录", "验证码")
_MAX_IMPORT_BYTES = 5_000_000
_MAX_ROWS = 2_000


class BossExportError(ValueError):
    """Import file has an unsupported shape or invalid job identity."""


@dataclass(frozen=True, slots=True)
class BossLead:
    external_id: str
    title: str
    company: str
    location: str
    salary: str
    tags: str
    description: str
    source_url: str
    skills: str = ""
    boss_active_status: str = ""

    @property
    def id(self) -> str:
        digest = hashlib.sha256(self.external_id.encode("utf-8")).hexdigest()[:24]
        return f"boss-{digest}"

    @property
    def jd_complete(self) -> bool:
        return len(self.description.strip()) >= 120 and not any(
            marker in self.description for marker in _LOGIN_MARKERS
        )


def _field(raw: dict[str, Any], *keys: str, limit: int = 20_000) -> str:
    for key in keys:
        value = raw.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            result = str(value).strip()
            if result:
                return result[:limit]
    return ""


def _external_id(raw: dict[str, Any]) -> str:
    value = _field(raw, "job_id", "encrypt_job_id", "encryptJobId", limit=256)
    if value and _JOB_ID.fullmatch(value):
        return value
    link = _field(raw, "job_link", "link", "source_url", limit=1000)
    parts = urlsplit(link)
    if parts.scheme == "https" and parts.hostname in _BOSS_HOSTS:
        match = _JOB_PATH.fullmatch(parts.path)
        if match:
            return match.group(1)
    return ""


def _normalize(raw: dict[str, Any], index: int) -> BossLead:
    external_id = _external_id(raw)
    title = _field(raw, "title", "jobName", limit=300)
    if not external_id or not title:
        raise BossExportError(f"第 {index} 条缺少可识别的 BOSS 职位 ID 或职位名称")
    description = _field(raw, "jd", "description", limit=100_000)
    if any(marker in description for marker in _LOGIN_MARKERS):
        description = ""
    tags = _field(raw, "tags_list", "tags", "jobExperience", limit=1000)
    if isinstance(raw.get("tags"), list):
        tags = " | ".join(str(item)[:100] for item in raw["tags"][:20])
    degree = _field(raw, "jobDegree", limit=100)
    if degree and degree not in tags:
        tags = f"{tags} | {degree}".strip(" |")
    return BossLead(
        external_id=external_id,
        title=title,
        company=_field(raw, "company", "boss_name", "brandName", limit=300),
        location=_field(raw, "location", "cityName", limit=300),
        salary=_field(raw, "salary", "salaryDesc", limit=100),
        tags=tags,
        description=description,
        source_url=f"https://www.zhipin.com/job_detail/{external_id}.html",
        skills=_field(raw, "skills", "skill_tags", limit=1000),
        boss_active_status=_field(raw, "boss_active_status", limit=100),
    )


def _richer(first: BossLead, second: BossLead) -> BossLead:
    data = asdict(first)
    for key, value in asdict(second).items():
        if value and (key != "description" or len(value) >= len(data[key])):
            data[key] = value
    return BossLead(**data)


def parse_boss_export(content: str) -> list[BossLead]:
    """Accept list/detail JSON exported by eatmoreduck/boss-zhipin-scraper."""
    if len(content.encode("utf-8")) > _MAX_IMPORT_BYTES:
        raise BossExportError("BOSS 导入文件超过 5 MB，请分批导入")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise BossExportError("不是有效的 JSON 文件") from exc
    rows = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise BossExportError("文件需包含非空 jobs 数组或岗位数组")
    if len(rows) > _MAX_ROWS:
        raise BossExportError("单次最多导入 2000 条岗位，请分批导入")
    merged: dict[str, BossLead] = {}
    for index, raw in enumerate(rows, 1):
        if not isinstance(raw, dict):
            raise BossExportError(f"第 {index} 条不是岗位对象")
        lead = _normalize(raw, index)
        merged[lead.external_id] = (
            _richer(merged[lead.external_id], lead) if lead.external_id in merged else lead
        )
    return list(merged.values())


def triage_boss_lead(lead: BossLead, profile: CandidateProfile, first_seen: str) -> dict[str, Any]:
    """Rank reading priority, never label the number as a hiring probability."""
    title = lead.title.casefold()
    detail = lead.description.casefold()
    tags = lead.tags.casefold()
    combined = f"{title} {detail}"
    reasons: list[str] = []
    blockers: list[str] = []
    score = 0

    focus_title = any(term in title for term in _FOCUS)
    ai_title = any(term in title for term in _AI_CONTEXT)
    engineering = any(term in combined for term in _ENGINEERING)
    if focus_title:
        score += 30
        reasons.append("职位名称符合 AI 应用或 FDE 方向")
    elif ai_title and engineering:
        score += 22
        reasons.append("职位名称和职责包含 AI 工程内容")
    elif any(term in detail for term in _FOCUS) and engineering:
        score += 15
        reasons.append("JD 包含 AI 工程内容，职位名称需再确认")
    else:
        reasons.append("与 AI/FDE 目标方向相关性较低")

    degree = profile.education_level
    if "博士" in tags and "博士" not in degree and "本科" not in tags:
        blockers.append("平台学历标签要求博士")
    elif (
        "硕士" in tags
        and not any(level in degree for level in ("硕士", "博士"))
        and "本科" not in tags
    ):
        blockers.append("平台学历标签要求硕士")
    if _EXPLICIT_SCHOOL.search(combined) and any(
        marker in profile.school_background
        for marker in ("普通", "非985", "非 985", "非211", "非 211")
    ):
        blockers.append("JD 明确限定学校背景")
    if _SENIOR.search(tags):
        blockers.append("平台经验标签要求多年工作经验")
    if any(term in tags for term in _EARLY) or any(term in title for term in _EARLY):
        score += 25
        reasons.append("校招、应届或实习岗位优先")
    elif any(term in tags for term in _JUNIOR):
        score += 20
        reasons.append("经验要求适合初级求职者")
    elif "1-3年" in tags or "1-3 年" in tags:
        score += 8
        reasons.append("初级社招，可核对实际经验要求")
    else:
        reasons.append("届别和经验要求需阅读 JD 核对")

    haystack = f"{title} {detail} {lead.skills}".casefold()
    profile_skills = [skill for skill in profile.skills if skill.strip()]
    matched = [skill for skill in profile_skills if skill.casefold() in haystack]
    if profile_skills and matched:
        score += min(25, round(25 * len(matched) / min(3, len(profile_skills))))
        reasons.append(f"JD 命中已填写的技能：{', '.join(matched[:3])}")
    elif profile_skills:
        reasons.append("暂未命中画像技能；请按完整 JD 人工判断")
    else:
        reasons.append("画像技能尚未填写")

    if lead.jd_complete:
        score += 10
    else:
        reasons.append("完整 JD 尚未取得，先确认详情")
    try:
        days_old = (datetime.now(UTC) - datetime.fromisoformat(first_seen)).days
    except ValueError:
        days_old = 99
    if days_old <= 7:
        score += 10
        reasons.append("最近首次见到；不是平台发布日期")

    if blockers:
        category = "excluded"
    elif not lead.jd_complete:
        category = "review"
    elif score >= 65:
        category = "priority"
    else:
        category = "lower"
    return {"score": score, "category": category, "reasons": reasons, "blockers": blockers}


class BossLeadRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS platform_job_leads (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL CHECK(source = 'boss'),
                    external_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    is_favorite INTEGER NOT NULL DEFAULT 0,
                    is_applied INTEGER NOT NULL DEFAULT 0,
                    is_hidden INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(source, external_id)
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_platform_leads_seen "
                "ON platform_job_leads(last_seen_at DESC)"
            )

    def import_leads(self, leads: list[BossLead]) -> dict[str, int]:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        result = {"total": len(leads), "new": 0, "updated": 0, "unchanged": 0}
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            for lead in leads:
                existing = connection.execute(
                    "SELECT payload_json FROM platform_job_leads WHERE id = ?", (lead.id,)
                ).fetchone()
                if existing:
                    lead = _richer(BossLead(**json.loads(existing["payload_json"])), lead)
                    changed = json.loads(existing["payload_json"]) != asdict(lead)
                    result["updated" if changed else "unchanged"] += 1
                    connection.execute(
                        "UPDATE platform_job_leads SET payload_json = ?, last_seen_at = ? "
                        "WHERE id = ?",
                        (json.dumps(asdict(lead), ensure_ascii=False), now, lead.id),
                    )
                else:
                    result["new"] += 1
                    connection.execute(
                        "INSERT INTO platform_job_leads "
                        "(id, source, external_id, payload_json, first_seen_at, last_seen_at) "
                        "VALUES (?, 'boss', ?, ?, ?, ?)",
                        (
                            lead.id,
                            lead.external_id,
                            json.dumps(asdict(lead), ensure_ascii=False),
                            now,
                            now,
                        ),
                    )
        return result

    def list_leads(self, profile: CandidateProfile) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT * FROM platform_job_leads ORDER BY last_seen_at DESC"
            ).fetchall()
        items = []
        for row in rows:
            lead = BossLead(**json.loads(row["payload_json"]))
            items.append(
                {
                    **asdict(lead),
                    "id": row["id"],
                    "source": "boss",
                    "sourceLabel": "BOSS直聘 · 平台线索",
                    "jdComplete": lead.jd_complete,
                    "firstSeenAt": row["first_seen_at"],
                    "lastSeenAt": row["last_seen_at"],
                    "isFavorite": bool(row["is_favorite"]),
                    "isApplied": bool(row["is_applied"]),
                    "isHidden": bool(row["is_hidden"]),
                    **triage_boss_lead(lead, profile, row["first_seen_at"]),
                }
            )
        category_order = {"priority": 0, "review": 1, "lower": 2, "excluded": 3}
        items.sort(
            key=lambda item: (
                item["isHidden"],
                item["isApplied"],
                category_order[item["category"]],
                -item["score"],
            )
        )
        return items

    def set_state(self, lead_id: str, field: str, value: bool) -> bool:
        fields = {"favorite": "is_favorite", "applied": "is_applied", "hidden": "is_hidden"}
        column = fields.get(field)
        if column is None:
            raise ValueError("未知岗位状态")
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                f"UPDATE platform_job_leads SET {column} = ? WHERE id = ?",
                (int(value), lead_id),
            )
            return cursor.rowcount > 0
