"""Small, evidence-backed parsers for public official recruitment pages.

Each parser owns one known page shape. Unknown sites continue through the normal
LLM pipeline; a successful parser never claims that a candidate matches the
user's skills without a separate evaluation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlsplit

from bs4 import BeautifulSoup

from .models import JobPosting, MatchLevel, ProfileFitLevel
from .url_utils import canonicalize_url

EXTRACTOR_VERSION = "official-html-v4"
_MEITU_JOB_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I)


@dataclass(frozen=True, slots=True)
class OfficialExtraction:
    jobs: list[JobPosting]
    list_complete: bool
    follow_urls: list[str] = field(default_factory=list)
    page_type: str = "job_list"


def _next_f_chunks(soup: BeautifulSoup) -> list[str]:
    """Decode Next.js flight script strings without executing page JavaScript."""

    chunks: list[str] = []
    prefix = "self.__next_f.push("
    for script in soup.find_all("script"):
        text = (script.string or "").strip()
        if not text.startswith(prefix) or not text.endswith(")"):
            continue
        try:
            value = json.loads(text[len(prefix) : -1])
        except json.JSONDecodeError:
            continue
        if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str):
            chunks.append(value[1])
    return chunks


def _flight_json(chunks: list[str], marker: str) -> Any:
    for chunk in chunks:
        position = chunk.find(marker)
        if position < 0:
            continue
        try:
            value, _end = json.JSONDecoder().raw_decode(chunk[position + len(marker) :])
        except json.JSONDecodeError:
            continue
        return value
    return None


def _meitu_jobs(page_url: str, html: str, company_name: str) -> OfficialExtraction | None:
    parts = urlsplit(page_url)
    if parts.hostname != "hr.meitu.com":
        return None
    soup = BeautifulSoup(html, "html.parser")
    chunks = _next_f_chunks(soup)

    if parts.path in {"", "/"} and any(
        key == "recruitmentType" and value == "campus"
        for key, value in parse_qsl(parts.query)
    ):
        listings = _flight_json(chunks, '"initJobList":')
        if not isinstance(listings, list) or not listings:
            return None
        follow_urls = []
        for item in listings:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("jobId") or "")
            if _MEITU_JOB_ID.fullmatch(job_id) and str(item.get("title") or "").strip():
                follow_urls.append(f"https://hr.meitu.com/jobCampus/{job_id}")
        if not follow_urls:
            return None
        return OfficialExtraction(
            jobs=[],
            list_complete=len(follow_urls) == len(listings),
            follow_urls=list(dict.fromkeys(follow_urls)),
        )

    if not parts.path.startswith("/jobCampus/"):
        return None
    job_id = parts.path.removeprefix("/jobCampus/")
    if not _MEITU_JOB_ID.fullmatch(job_id):
        return None
    info = _flight_json(chunks, '"jobInfo":')
    if not isinstance(info, dict) or str(info.get("jobId") or "") != job_id:
        return None
    title = str(info.get("title") or "").strip()
    if not title:
        return None
    description = ""
    for section in soup.select('div[class*="content_section__"]'):
        heading = section.select_one('[class*="sectionTitle__"]')
        if heading and heading.get_text(" ", strip=True) == "职位描述":
            description = section.get_text("\n", strip=True)
            break
    # The section itself is explicitly labelled 职位描述. English and mixed-language
    # JDs often omit Chinese subsection headings while still providing full text.
    complete = len(description) >= 80
    locations = info.get("locations")
    location = (
        "、".join(str(value) for value in locations if value)
        if isinstance(locations, list)
        else str(locations or "").strip()
    )
    jobs = [
        JobPosting(
            company=company_name,
            title=title,
            location=location or None,
            description=description,
            recruitment_type=str(info.get("modeName") or "") or None,
            published_at=str(info.get("publishedAt") or "") or None,
            source_url=canonicalize_url(page_url),
            jd_complete=complete,
            jd_incomplete_reason=None if complete else "官网详情未显示足够的职位描述正文",
            match_level=MatchLevel.MEDIUM,
            match_reason="官网标注校园招聘，具体届别仍需核对",
            profile_fit_level=ProfileFitLevel.UNKNOWN,
            profile_fit_reason="已从官网直接提取，尚未进行能力匹配评估",
            difficulty_reason="已从官网直接提取，尚未评估投递难度",
        )
    ]
    return OfficialExtraction(jobs=jobs, list_complete=True, page_type="job_detail")


def extract_official_jobs(
    page_url: str,
    html: str,
    company_name: str,
) -> OfficialExtraction | None:
    """Return known official job cards, or None when this page needs other analysis."""

    meitu = _meitu_jobs(page_url, html, company_name)
    if meitu is not None:
        return meitu

    parts = urlsplit(page_url)
    if parts.hostname != "careers.emqx.com" or parts.path != "/zh/alljobs":
        return None

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".all-jobs .job-box")
    if not cards:
        return None

    jobs: list[JobPosting] = []
    for card in cards:
        anchor = card.select_one('a[href*="/job?id="]')
        body = card.select_one(".job-contents")
        if anchor is None or body is None:
            continue
        title = anchor.get_text(" ", strip=True)
        url = canonicalize_url(urljoin(page_url, str(anchor.get("href") or "")))
        if not title or urlsplit(url).hostname != "careers.emqx.com":
            continue
        detail_parts = urlsplit(url)
        if detail_parts.path != "/zh/job" or not detail_parts.query:
            continue
        description = body.get_text("\n", strip=True)
        if not description:
            continue
        complete = len(description) >= 80
        accepts_graduates = "在校/应届" in description or "应届生" in description
        jobs.append(
            JobPosting(
                company=company_name,
                title=title,
                description=description,
                recruitment_type="校招" if accepts_graduates else None,
                source_url=url,
                jd_complete=complete,
                jd_incomplete_reason=None if complete else "官网列表中的 JD 正文过短",
                match_level=MatchLevel.MEDIUM if accepts_graduates else MatchLevel.LOW,
                match_reason=(
                    "官网写明接受在校/应届，具体毕业届别待核对"
                    if accepts_graduates
                    else "官网未明确标注目标毕业届别"
                ),
                profile_fit_level=ProfileFitLevel.UNKNOWN,
                profile_fit_reason="已从官网直接提取，尚未进行能力匹配评估",
                difficulty_reason="已从官网直接提取，尚未评估投递难度",
            )
        )
    return OfficialExtraction(jobs=jobs, list_complete=len(jobs) == len(cards))
