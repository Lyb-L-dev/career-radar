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

from .boss_ai import screening_context_hash
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
_RESUME_TECH_ROLE = re.compile(
    r"python|后端|服务端|数据开发|大数据|数据工程|数据分析|商业智能|bi开发|测试开发|自动化测试|全栈|机器学习|算法应用|软件开发|数字化研发|数据平台|流式计算",
    re.I,
)
_EARLY = ("应届", "校招", "校园", "在校", "实习", "毕业生")
_JUNIOR = ("经验不限", "不限经验", "1年以内", "一年以内", "0-1年", "0—1年")
_SENIOR = re.compile(r"(?:3\s*[-~—至]\s*5|[3-9]\s*年(?:以上|及以上)|至少\s*[3-9]\s*年)")
_EXPLICIT_SCHOOL = re.compile(
    r"(?<!不)(?<!无)(?<!没有)(?:仅限|必须|要求|只招|限)\s*(?:985|211|双一流)"
)
_STUDENT_REQUIRED = re.compile(
    r"(?<!不)(?<!无)(?<!没有)(?:岗位要求|任职资格|招聘对象|必须|仅限|要求|面向).{0,80}"
    r"(?:在校生|在读(?:大[一二三四]|本科|研究生)|在校(?:大[一二三四]|本科|研究生))",
    re.S,
)
_EXPLICIT_GRAD_YEAR = re.compile(r"(?:毕业时间|毕业年份|毕业年度)\s*[:：]?\s*(20\d{2})(?:年|届)")
_GRAD_COHORT = re.compile(r"(?<!\d)(20\d{2})届(?:校招|应届|毕业生|秋招|春招)?")
_GRAD_YEAR_RANGE = re.compile(r"(?<!\d)(20\d{2})\s*[、/~-]\s*(20\d{2})届")
_UNCLEAR_COMPANY = re.compile(
    r"^(?:某(?:知名|大型|互联网|人工智能|科技|企业|公司)|保密|匿名|未公开)"
)
_LOGIN_MARKERS = ("登录查看完整内容", "安全验证", "请先登录", "验证码")
_MAX_IMPORT_BYTES = 5_000_000
_MAX_ROWS = 2_000


class BossExportError(ValueError):
    """Import file has an unsupported shape or invalid job identity."""


@dataclass(frozen=True, slots=True)
class BossPreferences:
    current_student: bool | None = None
    accept_internship: bool = True


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

    @property
    def company_identified(self) -> bool:
        name = self.company.strip()
        return bool(name) and not bool(_UNCLEAR_COMPANY.search(name))


def _field(raw: dict[str, Any], *keys: str, limit: int = 20_000) -> str:
    for key in keys:
        value = raw.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            result = str(value).strip()
            if result:
                return result[:limit]
    return ""


def _external_id(raw: dict[str, Any]) -> str:
    # 上游 scraper 的 job_id 是链接的 MD5 摘要，不是 BOSS 页面真实 ID。
    # 有可信原始链接时必须先从链接取 ID，才能生成可打开的职位来源地址。
    link = _field(raw, "job_link", "link", "source_url", limit=1000)
    parts = urlsplit(link)
    if parts.scheme == "https" and parts.hostname in _BOSS_HOSTS:
        match = _JOB_PATH.fullmatch(parts.path)
        if match:
            return match.group(1)
    value = _field(raw, "encrypt_job_id", "encryptJobId", "job_id", limit=256)
    if value and _JOB_ID.fullmatch(value):
        return value
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
        if value and (key != "description" or second.jd_complete or len(value) > len(data[key])):
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


def triage_boss_lead(
    lead: BossLead,
    profile: CandidateProfile,
    first_seen: str,
    preferences: BossPreferences | None = None,
) -> dict[str, Any]:
    """Rank reading priority, never label the number as a hiring probability."""
    preferences = preferences or BossPreferences(accept_internship=profile.accept_internship)
    title = lead.title.casefold()
    detail = lead.description.casefold()
    tags = lead.tags.casefold()
    combined = f"{title} {detail} {tags}"
    reasons: list[str] = []
    blockers: list[str] = []
    score = 0

    focus_title = any(term in title for term in _FOCUS)
    ai_title = any(term in title for term in _AI_CONTEXT)
    engineering = any(term in combined for term in _ENGINEERING)
    if focus_title:
        score += 30
        reasons.append("职位名称符合 AI 应用或 FDE 方向")
    elif _RESUME_TECH_ROLE.search(title):
        score += 25
        reasons.append("职位名称属于后端、数据、测试或全栈等技术方向")
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
    grad_years = {int(value) for value in _EXPLICIT_GRAD_YEAR.findall(lead.description)}
    grad_years.update(
        int(value) for value in _GRAD_COHORT.findall(f"{lead.title} {lead.description} {lead.tags}")
    )
    for first, second in _GRAD_YEAR_RANGE.findall(f"{lead.title} {lead.description} {lead.tags}"):
        grad_years.update((int(first), int(second)))
    if grad_years and profile.graduation_year not in grad_years:
        blockers.append(
            f"岗位明确要求 {', '.join(map(str, sorted(grad_years)))} 届，你是 {profile.graduation_year} 届"
        )
    student_requirement = any(
        "优先" not in lead.description[match.end() : match.end() + 8]
        for match in _STUDENT_REQUIRED.finditer(lead.description)
    )
    if preferences.current_student is False and ("在校生" in tags or student_requirement):
        blockers.append("岗位要求当前在校，但你已毕业")
    if not preferences.accept_internship and (
        "实习" in title or "实习" in tags or "实习生" in lead.description[:120]
    ):
        blockers.append("岗位是实习性质，你已选择只看可投正式岗")
    if not lead.company_identified:
        reasons.append("招聘公司名称未公开，先核对招聘方")
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
    elif not lead.company_identified:
        category = "review"
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
                    ai_context_hash TEXT,
                    ai_result_json TEXT,
                    ai_checked_at TEXT,
                    UNIQUE(source, external_id)
                )"""
            )
            existing_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(platform_job_leads)")
            }
            for column in ("ai_context_hash", "ai_result_json", "ai_checked_at"):
                if column not in existing_columns:
                    connection.execute(f"ALTER TABLE platform_job_leads ADD COLUMN {column} TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_platform_leads_seen "
                "ON platform_job_leads(last_seen_at DESC)"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS platform_lead_preferences (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    current_student INTEGER,
                    accept_internship INTEGER NOT NULL
                )"""
            )

    def get_preferences(self, default_accept_internship: bool = True) -> BossPreferences:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT current_student, accept_internship FROM platform_lead_preferences WHERE id = 1"
            ).fetchone()
        if row is None:
            return BossPreferences(accept_internship=default_accept_internship)
        return BossPreferences(
            current_student=(
                bool(row["current_student"]) if row["current_student"] is not None else None
            ),
            accept_internship=bool(row["accept_internship"]),
        )

    def set_preferences(self, preferences: BossPreferences) -> None:
        current = None if preferences.current_student is None else int(preferences.current_student)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO platform_lead_preferences(id, current_student, accept_internship) "
                "VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "current_student = excluded.current_student, "
                "accept_internship = excluded.accept_internship",
                (current, int(preferences.accept_internship)),
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

    def list_leads(self, profile: CandidateProfile, model: str = "") -> list[dict[str, Any]]:
        preferences = self.get_preferences(profile.accept_internship)
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT * FROM platform_job_leads ORDER BY last_seen_at DESC"
            ).fetchall()
        items = []
        for row in rows:
            lead = BossLead(**json.loads(row["payload_json"]))
            current_ai_hash = (
                screening_context_hash(lead, profile, model, preferences) if model else None
            )
            ai_current = bool(row["ai_result_json"] and row["ai_context_hash"] == current_ai_hash)
            items.append(
                {
                    **asdict(lead),
                    "id": row["id"],
                    "source": "boss",
                    "sourceLabel": "BOSS直聘 · 平台线索",
                    "jdComplete": lead.jd_complete,
                    "aiScreenable": lead.jd_complete
                    and lead.company_identified
                    and len(lead.description) <= 8_000,
                    "companyIdentified": lead.company_identified,
                    "firstSeenAt": row["first_seen_at"],
                    "lastSeenAt": row["last_seen_at"],
                    "isFavorite": bool(row["is_favorite"]),
                    "isApplied": bool(row["is_applied"]),
                    "isHidden": bool(row["is_hidden"]),
                    "aiResult": json.loads(row["ai_result_json"]) if ai_current else None,
                    "aiCheckedAt": row["ai_checked_at"] if ai_current else None,
                    "aiNeedsRefresh": bool(row["ai_result_json"] and not ai_current),
                    **triage_boss_lead(lead, profile, row["first_seen_at"], preferences),
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

    def get_ai_source(self, lead_id: str) -> tuple[BossLead, str, str | None, str | None] | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT payload_json, first_seen_at, ai_context_hash, ai_result_json "
                "FROM platform_job_leads WHERE id = ?",
                (lead_id,),
            ).fetchone()
        if row is None:
            return None
        return (
            BossLead(**json.loads(row["payload_json"])),
            row["first_seen_at"],
            row["ai_context_hash"],
            row["ai_result_json"],
        )

    def save_ai_result(
        self,
        lead_id: str,
        expected_hash: str,
        result: dict[str, Any],
        profile: CandidateProfile,
        model: str,
        preferences: BossPreferences,
    ) -> bool:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM platform_job_leads WHERE id = ?", (lead_id,)
            ).fetchone()
            if row is None:
                return False
            lead = BossLead(**json.loads(row["payload_json"]))
            preference_row = connection.execute(
                "SELECT current_student, accept_internship FROM platform_lead_preferences WHERE id = 1"
            ).fetchone()
            current_preferences = (
                BossPreferences(
                    current_student=(
                        bool(preference_row["current_student"])
                        if preference_row["current_student"] is not None
                        else None
                    ),
                    accept_internship=bool(preference_row["accept_internship"]),
                )
                if preference_row
                else BossPreferences(accept_internship=profile.accept_internship)
            )
            if (
                current_preferences != preferences
                or screening_context_hash(lead, profile, model, current_preferences)
                != expected_hash
            ):
                return False
            connection.execute(
                "UPDATE platform_job_leads SET ai_context_hash = ?, ai_result_json = ?, "
                "ai_checked_at = ? WHERE id = ?",
                (
                    expected_hash,
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                    datetime.now(UTC).isoformat(timespec="seconds"),
                    lead_id,
                ),
            )
            return True

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
