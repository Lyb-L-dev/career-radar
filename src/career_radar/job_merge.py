"""岗位身份判断与结构化字段合并的共享规则。

列表摘要/详情页、长页面切片和 SQLite 历史记录使用不同的正文策略，但公司、
职位、地点、URL 冲突及匹配等级的判断必须保持一致，避免三个模块各自漂移。
"""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit

from .models import JobPosting, MatchLevel, ProfileFitLevel
from .url_utils import canonicalize_url

TextMergeStrategy = Literal["richer", "overlap"]


def normalized(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def _http_url(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
        return None
    return canonicalize_url(value)


def job_urls(job: JobPosting) -> set[str]:
    """返回可作为公开岗位身份依据的详情/申请 HTTP(S) URL。"""

    return {
        url
        for url in (_http_url(job.source_url), _http_url(job.apply_url))
        if url
    }


def _locations_compatible(
    first: str | None,
    second: str | None,
    *,
    allow_missing: bool,
) -> bool:
    first_value = normalized(first)
    second_value = normalized(second)
    if not first_value or not second_value:
        return allow_missing or first_value == second_value
    # “上海”与“上海市徐汇区”可视为同一详情页的精度变化；北京/上海不能合并。
    return (
        first_value == second_value
        or first_value in second_value
        or second_value in first_value
    )


def is_same_job(
    first: JobPosting,
    second: JobPosting,
    *,
    allow_missing_location: bool = True,
    require_shared_url: bool = True,
) -> bool:
    """保守判断两个结构化记录是否为同一岗位。

    两侧都存在且不同的申请链接是强冲突证据，即使它们来自同一个列表页也不能合并。
    详情/申请 URL 有交集则允许地点出现精度变化；没有 URL 时依赖职位与地点。
    """

    if first.record_type != second.record_type:
        return False
    if normalized(first.company) and normalized(second.company):
        if normalized(first.company) != normalized(second.company):
            return False
    if normalized(first.title) != normalized(second.title):
        return False
    if not _locations_compatible(
        first.location,
        second.location,
        allow_missing=allow_missing_location,
    ):
        return False

    first_apply = _http_url(first.apply_url)
    second_apply = _http_url(second.apply_url)
    if first_apply and second_apply and first_apply != second_apply:
        return False

    first_urls = job_urls(first)
    second_urls = job_urls(second)
    if first_urls and second_urls:
        return bool(first_urls & second_urls) or not require_shared_url
    return True


def _join_overlapping_text(first: str | None, second: str | None) -> str | None:
    if not first:
        return second
    if not second:
        return first
    if second in first:
        return first
    if first in second:
        return second
    max_overlap = min(len(first), len(second), 5000)
    for length in range(max_overlap, 39, -1):
        if first[-length:] == second[:length]:
            return first + second[length:]
    return f"{first}\n{second}"


def _match_rank(level: MatchLevel) -> int:
    return {MatchLevel.LOW: 0, MatchLevel.MEDIUM: 1, MatchLevel.HIGH: 2}[level]


def _profile_rank(level: ProfileFitLevel) -> int:
    return {
        ProfileFitLevel.UNKNOWN: -1,
        ProfileFitLevel.LOW: 0,
        ProfileFitLevel.MEDIUM: 1,
        ProfileFitLevel.HIGH: 2,
    }[level]


def merge_job_postings(
    first: JobPosting,
    second: JobPosting,
    *,
    text_strategy: TextMergeStrategy = "richer",
) -> JobPosting:
    """合并岗位元数据；正文可选择“较完整版本”或“按切片顺序拼接”。"""

    first_score = len(first.description) + len(first.requirements or "")
    second_score = len(second.description) + len(second.requirements or "")
    if text_strategy == "richer":
        primary, other = (second, first) if second_score > first_score else (first, second)
        data = primary.model_dump()
    else:
        primary, other = first, second
        data = first.model_dump()
        data["description"] = _join_overlapping_text(
            first.description, second.description
        ) or ""
        data["requirements"] = _join_overlapping_text(
            first.requirements, second.requirements
        )

    for field in (
        "location",
        "requirements",
        "recruitment_type",
        "is_2026_target",
        "target_graduates",
        "published_at",
        "valid_until",
        "apply_url",
        "contact_email",
        "application_method",
        "source_url",
        "match_reason",
        "profile_fit_reason",
        "difficulty_reason",
    ):
        if data.get(field) in (None, "") and getattr(other, field) not in (None, ""):
            data[field] = getattr(other, field)

    if _match_rank(other.match_level) > _match_rank(primary.match_level):
        data["match_level"] = other.match_level
        if other.match_reason:
            data["match_reason"] = other.match_reason
    if _profile_rank(other.profile_fit_level) > _profile_rank(primary.profile_fit_level):
        data["profile_fit_level"] = other.profile_fit_level
        data["profile_fit_reason"] = other.profile_fit_reason
    if len(other.difficulty_reason) > len(primary.difficulty_reason):
        data["difficulty_level"] = other.difficulty_level
        data["difficulty_score"] = other.difficulty_score
        data["difficulty_reason"] = other.difficulty_reason

    data["jd_complete"] = primary.jd_complete or other.jd_complete
    if data["jd_complete"]:
        data["jd_incomplete_reason"] = None
    elif not data.get("jd_incomplete_reason"):
        data["jd_incomplete_reason"] = other.jd_incomplete_reason
    return JobPosting.model_validate(data)


def preserve_richer_previous_content(
    incoming: JobPosting,
    previous: JobPosting,
) -> JobPosting:
    """防止短暂抽取退化覆盖历史完整 JD，同时保留本轮已核实的新元数据。"""

    previous_score = len(previous.description) + len(previous.requirements or "")
    incoming_score = len(incoming.description) + len(incoming.requirements or "")
    if previous_score <= incoming_score:
        return incoming
    data = incoming.model_dump()
    data.update(
        description=previous.description,
        requirements=previous.requirements,
        jd_complete=previous.jd_complete,
        jd_incomplete_reason=previous.jd_incomplete_reason,
    )
    for field in ("contact_email", "application_method", "apply_url"):
        if not data.get(field) and getattr(previous, field):
            data[field] = getattr(previous, field)
    return JobPosting.model_validate(data)
