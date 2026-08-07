"""web_repository 共享的纯函数与常量（无数据库访问）。"""

from __future__ import annotations

import hashlib
import re

from ..models import JobPosting

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


JOB_SELECT = """
SELECT j.*,
       COALESCE(s.is_favorite, 0) AS is_favorite,
       COALESCE(s.is_applied, 0) AS is_applied,
       COALESCE(s.not_interested, 0) AS not_interested,
       s.ignored_content_hash AS ignored_content_hash,
       (SELECT h.event_type FROM job_history h
        WHERE h.entity_key = j.entity_key ORDER BY h.id DESC LIMIT 1) AS latest_event
FROM jobs j
LEFT JOIN web_job_state s ON s.entity_key = j.entity_key
"""


