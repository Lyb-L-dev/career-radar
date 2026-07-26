"""政府公开名单企业候选库的读取、筛选和个人画像初筛。

候选库与 ``config.yaml`` 中的监控企业严格分离：进入政府名单只是一条质量证据，
没有官网和招聘入口的候选企业不会被爬虫访问，也不会消耗 LLM 配额。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import CandidateProfile


class CompanyCatalogError(ValueError):
    """候选库文件不存在、损坏或结构不兼容。"""


def load_company_catalog(path: Path) -> dict[str, Any]:
    """读取静态候选库；文件未部署时返回可用的空库，避免影响核心爬虫。"""

    if not path.is_file():
        return {
            "schemaVersion": 1,
            "generatedAt": None,
            "total": 0,
            "disclaimer": "尚未生成企业候选库。",
            "sources": [],
            "items": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompanyCatalogError(f"企业候选库读取失败：{exc}") from exc
    if payload.get("schemaVersion") != 1 or not isinstance(payload.get("items"), list):
        raise CompanyCatalogError("企业候选库结构不兼容，请重新运行导入脚本")
    if payload.get("total") != len(payload["items"]):
        raise CompanyCatalogError("企业候选库数量校验失败，请重新运行导入脚本")
    return payload


def find_catalog_candidate(catalog: dict[str, Any], candidate_id: str) -> dict[str, Any] | None:
    return next((item for item in catalog["items"] if item.get("id") == candidate_id), None)


def _location_matches(item: dict[str, Any], preferred_locations: list[str]) -> bool:
    haystack = f"{item.get('province') or ''}{item.get('city') or ''}"
    return any(
        location and (location in haystack or haystack in location)
        for location in preferred_locations
    )


def preliminary_fit(item: dict[str, Any], profile: CandidateProfile) -> tuple[int, str, list[str]]:
    """按地区和名称技术信号计算保守初筛分，不冒充真实岗位录取难度。"""

    score = 52
    quality_signals = list(item.get("qualitySignals") or [])
    reasons = [quality_signals[0] if quality_signals else "进入政府公开的优质企业候选名单"]
    province = item.get("province")
    city = item.get("city")
    if province == "福建":
        score += 18
        reasons.append("福建本地优先")
    if _location_matches(item, profile.preferred_locations):
        score += 14
        reasons.append(f"地区匹配：{city or province}")

    signals = list(item.get("techSignals") or [])
    if signals:
        score += min(18, 10 + (len(signals) - 1) * 4)
        reasons.append(f"企业名称呈现技术方向：{'、'.join(signals)}")

    role_text = " ".join(profile.target_roles).casefold()
    technical_role = any(
        term in role_text
        for term in ("数据", "开发", "软件", "测试", "ai", "人工智能", "算法", "后端", "全栈")
    )
    if technical_role and signals:
        score += 6
        reasons.append("与目标技术岗位存在初步方向交集")

    score = min(100, score)
    level = "high" if score >= 80 else ("medium" if score >= 65 else "low")
    return score, level, reasons


def catalog_response(
    catalog: dict[str, Any],
    *,
    profile: CandidateProfile,
    states: dict[str, dict[str, Any]],
    monitored_names: set[str],
    query: str = "",
    province: str | None = None,
    city: str | None = None,
    fit_level: str | None = None,
    decision: str | None = None,
    channel_status: str | None = None,
    source_key: str | None = None,
    tech_only: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """叠加本地审批状态，完成过滤、排序和分页。"""

    normalized_monitored = {re.sub(r"\s+", "", name).casefold() for name in monitored_names}
    keyword = query.strip().casefold()
    prepared: list[dict[str, Any]] = []
    for raw in catalog["items"]:
        state = states.get(raw["id"], {})
        is_monitored = re.sub(r"\s+", "", raw["name"]).casefold() in normalized_monitored
        item_decision = "monitored" if is_monitored else state.get("decision", "pending")
        score, level, reasons = preliminary_fit(raw, profile)
        item = {
            **raw,
            "fitScore": score,
            "fitLevel": level,
            "fitReasons": reasons,
            "decision": item_decision,
            "monitored": is_monitored,
            "officialWebsite": state.get("official_website") or raw.get("officialWebsite"),
            "careersUrl": state.get("careers_url"),
            "companyType": (
                state.get("company_type") or raw.get("suggestedCompanyType") or "other"
            ),
            "industryCategory": (
                state.get("industry_category") or raw.get("suggestedIndustryCategory") or "other"
            ),
            "recruitmentChannelStatus": state.get("recruitment_channel_status")
            or "official_site_pending",
            "parentCompany": state.get("parent_company"),
            "groupRecruitmentUrl": state.get("group_recruitment_url"),
            "attributionKeywords": (
                json.loads(state["attribution_keywords_json"])
                if state.get("attribution_keywords_json")
                else []
            ),
            "reviewNote": state.get("note"),
            "reviewedAt": state.get("updated_at"),
        }
        searchable = " ".join(
            str(value or "")
            for value in (
                item["name"],
                item.get("province"),
                item.get("city"),
                item.get("sourceTitle"),
                " ".join(item.get("techSignals") or []),
            )
        ).casefold()
        if keyword and keyword not in searchable:
            continue
        if province and item.get("province") != province:
            continue
        if city and item.get("city") != city:
            continue
        if fit_level and level != fit_level:
            continue
        if decision and item_decision != decision:
            continue
        if channel_status and item["recruitmentChannelStatus"] != channel_status:
            continue
        if source_key and source_key not in (item.get("sourceKeys") or [item.get("sourceKey")]):
            continue
        if tech_only and not item.get("techSignals"):
            continue
        prepared.append(item)

    decision_counts = {"pending": 0, "shortlisted": 0, "rejected": 0, "monitored": 0}
    province_counts: dict[str, int] = {}
    high_fit = 0
    tech_related = 0
    for raw in catalog["items"]:
        state = states.get(raw["id"], {})
        monitored = re.sub(r"\s+", "", raw["name"]).casefold() in normalized_monitored
        current_decision = "monitored" if monitored else state.get("decision", "pending")
        decision_counts[current_decision] = decision_counts.get(current_decision, 0) + 1
        province_name = raw.get("province") or "未知"
        province_counts[province_name] = province_counts.get(province_name, 0) + 1
        if preliminary_fit(raw, profile)[1] == "high":
            high_fit += 1
        if raw.get("techSignals"):
            tech_related += 1

    prepared.sort(
        key=lambda item: (
            0 if item["decision"] == "shortlisted" else 1,
            0 if item["province"] == "福建" else 1,
            -item["fitScore"],
            item["name"],
        )
    )
    total = len(prepared)
    start = (page - 1) * page_size
    return {
        "items": prepared[start : start + page_size],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "catalogTotal": len(catalog["items"]),
        "generatedAt": catalog.get("generatedAt"),
        "disclaimer": catalog.get("disclaimer"),
        "sources": catalog.get("sources", []),
        "stats": {
            "total": len(catalog["items"]),
            "fujian": province_counts.get("福建", 0),
            "highFit": high_fit,
            "techRelated": tech_related,
            **decision_counts,
        },
        "provinceCounts": dict(
            sorted(province_counts.items(), key=lambda pair: (-pair[1], pair[0]))
        ),
    }
