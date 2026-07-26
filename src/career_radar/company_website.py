"""从公开搜索结果中保守识别企业官网。

政府名单通常只有企业全称。本模块不把搜索排名直接当作事实，而是先排除常见招聘、
工商、百科、社交和政府目录，再要求结果标题与摘要同时命中企业全称。只有达到高置信
阈值且明显领先其他域名时，前端才允许一键加入监控；其余结果必须人工确认。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_THIRD_PARTY_HOSTS = (
    "aiqicha.baidu.com",
    "baike.baidu.com",
    "baidu.com",
    "bosszhipin.com",
    "dav01.com",
    "douyin.com",
    "facebook.com",
    "github.com",
    "google.com",
    "jobui.com",
    "kanzhun.com",
    "lagou.com",
    "liepin.com",
    "linkedin.com",
    "nowcoder.com",
    "qcc.com",
    "qiye.58.com",
    "so.com",
    "sogou.com",
    "tianyancha.com",
    "weibo.com",
    "wikipedia.org",
    "xiaohongshu.com",
    "yahoo.com",
    "zhihu.com",
    "zhipin.com",
    "51job.com",
    "58.com",
)


def _match_key(value: object) -> str:
    """忽略空格、标点和中英文括号，用于企业全称的严格包含判断。"""

    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").casefold())


def _is_third_party(hostname: str) -> bool:
    host = hostname.casefold().removeprefix("www.")
    if host.endswith(".gov.cn") or host == "gov.cn":
        return True
    return any(host == blocked or host.endswith(f".{blocked}") for blocked in _THIRD_PARTY_HOSTS)


def _website_origin(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
        return None
    if _is_third_party(parts.hostname):
        return None
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), "/", "", ""))


def discover_official_website(company_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """对 DuckDuckGo 结果分组评分，返回高置信官网或待人工确认的候选项。"""

    company_key = _match_key(company_name)
    if len(company_key) < 4:
        return {
            "status": "not_found",
            "confidence": "low",
            "website": None,
            "message": "企业名称过短，无法安全自动判定官网。",
            "candidates": [],
        }

    grouped: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        raw_url = str(row.get("url") or "").strip()
        website = _website_origin(raw_url)
        if not website:
            continue
        parts = urlsplit(website)
        host = (parts.hostname or "").casefold().removeprefix("www.")
        title = str(row.get("title") or "").strip()
        snippet = str(row.get("snippet") or "").strip()
        title_match = company_key in _match_key(title)
        snippet_match = company_key in _match_key(snippet)
        # 至少有一处出现企业全称，杜绝只凭“官网”关键词或搜索排名猜测。
        if not title_match and not snippet_match:
            continue
        try:
            rank = max(1, int(row.get("rank") or index + 1))
        except (TypeError, ValueError):
            rank = index + 1
        score = (45 if title_match else 0) + (30 if snippet_match else 0)
        score += max(0, 22 - (rank - 1) * 4)
        if urlsplit(raw_url).path in {"", "/", "/index.html", "/index.htm"}:
            score += 8

        current = grouped.setdefault(
            host,
            {
                "website": website,
                "title": title,
                "snippet": snippet,
                "score": score,
                "rank": rank,
                "titleMatch": title_match,
                "snippetMatch": snippet_match,
                "resultCount": 0,
            },
        )
        current["resultCount"] += 1
        if score > current["score"]:
            current.update(
                {
                    "website": website,
                    "title": title,
                    "snippet": snippet,
                    "score": score,
                    "rank": rank,
                    "titleMatch": title_match,
                    "snippetMatch": snippet_match,
                }
            )

    candidates = list(grouped.values())
    for candidate in candidates:
        candidate["score"] = min(100, candidate["score"] + min(10, 5 * (candidate["resultCount"] - 1)))
    candidates.sort(key=lambda item: (-item["score"], item["rank"], item["website"]))
    public_candidates = [
        {
            "website": item["website"],
            "title": item["title"],
            "snippet": item["snippet"],
            "score": item["score"],
        }
        for item in candidates[:3]
    ]
    if not candidates:
        return {
            "status": "not_found",
            "confidence": "low",
            "website": None,
            "message": "没有找到同时包含企业全称、且不像第三方目录的公开网站。",
            "candidates": [],
        }

    top = candidates[0]
    runner_up_score = candidates[1]["score"] if len(candidates) > 1 else 0
    high_confidence = (
        top["score"] >= 85
        and top["titleMatch"]
        and top["snippetMatch"]
        and (top["score"] - runner_up_score >= 15 or top["score"] >= 98)
    )
    if high_confidence:
        return {
            "status": "found",
            "confidence": "high",
            "website": top["website"],
            "message": "搜索标题和摘要均命中企业全称，且已排除常见第三方平台。",
            "candidates": public_candidates,
        }
    return {
        "status": "ambiguous",
        "confidence": "medium" if top["score"] >= 60 else "low",
        "website": top["website"],
        "message": "找到了可能的官网，但证据不足以自动确认，请人工核对后再加入监控。",
        "candidates": public_candidates,
    }
