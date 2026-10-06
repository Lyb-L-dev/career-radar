"""通过 ATS 官方公开接口直接拉取岗位，替代对招聘页的 HTML 遍历。

参考 HA7CH/job-pro 的“按 ATS 家族适配”思路：先支持 Greenhouse、Lever、
Ashby 三个有稳定公开文档的 ATS，以及通用的 JSON Feed（适配自建接口/国企
门户的 XHR 数据），后续可按相同接口增加 Moka、北森、飞书 ATS 等适配器。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict

from .models import AtsSourceConfig, AtsSourceType, CompanyConfig, JobPosting, MatchLevel
from .network_policy import PublicTargetPolicy, UnsafeTargetError

_TENANT_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_MAX_REDIRECTS = 5


class ATSSourceError(RuntimeError):
    """ATS 接口请求、解析或校验失败；只影响当前公司，不中断整批任务。"""


class ATSJob(BaseModel):
    """适配器归一化后的岗位结构。"""

    model_config = ConfigDict(extra="ignore")

    source_id: str = ""
    title: str
    description: str = ""
    requirements: str | None = None
    location: str | None = None
    apply_url: str | None = None
    job_url: str | None = None
    published_at: str | None = None
    recruitment_type: str | None = None
    remote: bool | None = None


def _html_to_text(value: str) -> str:
    """把 ATS 返回的 HTML JD 转成干净文本，便于直接入库和后续 LLM 评估。"""

    soup = BeautifulSoup(value, "html.parser")
    lines = [
        line.strip()
        for line in soup.get_text("\n", strip=True).splitlines()
        if line.strip()
    ]
    return "\n".join(lines)


def _normalize_datetime(value: Any) -> str | None:
    """兼容 ISO 字符串与秒/毫秒时间戳，统一返回 ISO 文本。"""

    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.isoformat() if parsed.year >= 1900 else None
    except ValueError:
        return None


def _tenant(source: AtsSourceConfig) -> str:
    value = (source.tenant or "").strip()
    if not _TENANT_PATTERN.fullmatch(value):
        raise ATSSourceError(f"非法 ATS tenant：{value!r}")
    return value


def _greenhouse_jobs(source: AtsSourceConfig, session: requests.Session) -> list[ATSJob]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{_tenant(source)}/jobs"
    response = session.get(
        url,
        params={"content": "true"},
        timeout=source.request_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    jobs: list[ATSJob] = []
    for item in payload.get("jobs") or []:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        location = item.get("location") or {}
        location_name = str(location.get("name") or "").strip() or None
        absolute_url = item.get("absolute_url")
        jobs.append(
            ATSJob(
                source_id=str(item.get("id") or ""),
                title=title,
                description=_html_to_text(str(item.get("content") or "")),
                location=location_name,
                apply_url=str(absolute_url) if absolute_url else None,
                job_url=str(absolute_url) if absolute_url else None,
                published_at=_normalize_datetime(item.get("updated_at")),
                remote=bool(location_name and "remote" in location_name.casefold()),
            )
        )
    return jobs


def _lever_jobs(source: AtsSourceConfig, session: requests.Session) -> list[ATSJob]:
    url = f"https://api.lever.co/v0/postings/{_tenant(source)}"
    response = session.get(
        url,
        params={"mode": "json"},
        timeout=source.request_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ATSSourceError("Lever 接口返回结构异常：顶层不是数组")
    jobs: list[ATSJob] = []
    for item in payload:
        title = str(item.get("text") or "").strip()
        if not title:
            continue
        categories = item.get("categories") or {}
        location = str(categories.get("location") or item.get("country") or "").strip() or None
        workplace = str(item.get("workplaceType") or "").casefold()
        jobs.append(
            ATSJob(
                source_id=str(item.get("id") or ""),
                title=title,
                description=str(item.get("descriptionPlain") or "").strip(),
                location=location,
                apply_url=str(item.get("applyUrl") or "") or None,
                job_url=str(item.get("hostedUrl") or "") or None,
                published_at=_normalize_datetime(item.get("createdAt")),
                recruitment_type=str(categories.get("commitment") or "").strip() or None,
                remote=bool("remote" in workplace or (location and "remote" in location.casefold())),
            )
        )
    return jobs


def _ashby_jobs(source: AtsSourceConfig, session: requests.Session) -> list[ATSJob]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{_tenant(source)}"
    response = session.get(
        url,
        params={"includeCompensation": "true"},
        timeout=source.request_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    jobs: list[ATSJob] = []
    for item in payload.get("jobs") or []:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        location = str(item.get("location") or "").strip() or None
        employment = str(item.get("employmentType") or "").strip() or None
        jobs.append(
            ATSJob(
                source_id=str(item.get("id") or ""),
                title=title,
                description=str(item.get("descriptionPlain") or "").strip(),
                location=location,
                apply_url=str(item.get("applyUrl") or "") or None,
                job_url=str(item.get("jobUrl") or "") or None,
                published_at=_normalize_datetime(item.get("publishedAt")),
                recruitment_type=employment,
                remote=bool(location and "remote" in location.casefold()),
            )
        )
    return jobs


def _resolve_json_path(data: Any, path: str) -> Any:
    """按点号路径读取嵌套字段，兼容 a.b.c、a.0.b 与 $ 前缀。"""

    if not path:
        return None
    current = data
    parts = path.strip().lstrip("$.").split(".")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def _first_matching_path(data: Any, paths: str | list[str]) -> Any:
    if isinstance(paths, str):
        paths = [item.strip() for item in paths.split(",") if item.strip()]
    for path in paths:
        value = _resolve_json_path(data, path)
        if value is not None and value != "":
            return value
    return None


_DEFAULT_MAPPING: dict[str, list[str]] = {
    "source_id": ["id", "postId", "jobId", "JobAdId"],
    "title": ["title", "name", "position", "jobTitle", "job_title"],
    "description": [
        "description",
        "descriptionPlain",
        "descriptionHtml",
        "content",
        "text",
        "jd",
        "jobDescription",
        "job_description",
    ],
    "requirements": ["requirements", "qualifications", "Require"],
    "location": ["location", "city", "office", "address", "workCity"],
    "apply_url": ["applyUrl", "apply_url", "url", "link", "postingUrl"],
    "job_url": ["jobUrl", "job_url", "url", "link", "hostedUrl"],
    "published_at": [
        "publishedAt",
        "published_at",
        "createdAt",
        "created_at",
        "postDate",
        "post_date",
    ],
    "recruitment_type": [
        "recruitmentType",
        "recruitment_type",
        "employmentType",
        "employment_type",
        "jobType",
        "job_type",
    ],
    "remote": ["remote", "isRemote", "is_remote", "workplaceType", "workplace_type"],
}


def _json_feed_items(source: AtsSourceConfig, payload: Any) -> list[Any]:
    if source.json_success_path is not None:
        status = _resolve_json_path(payload, source.json_success_path)
        if str(status) != str(source.json_success_value):
            raise ATSSourceError("json_feed 业务状态不是配置的成功值")
    items = _resolve_json_path(payload, source.json_items_path or "$")
    if isinstance(items, dict):
        for key in ("jobs", "data", "items", "list", "rows", "result"):
            candidate = items.get(key)
            if isinstance(candidate, list):
                items = candidate
                break
    if not isinstance(items, list):
        raise ATSSourceError(
            f"json_feed 的 items 路径 {source.json_items_path!r} 未指向数组"
        )
    return items


def _json_feed_jobs(
    source: AtsSourceConfig,
    session: requests.Session,
    before_request: Callable[[str], None] | None = None,
) -> list[ATSJob]:
    items: list[Any] = []
    seen_pages: set[str] = set()
    seen_records: set[str] = set()
    expected_total: int | None = None
    body = dict(source.json_body)
    page_limit = source.json_max_pages if source.json_page_field else 1
    initial_page = body.get(source.json_page_field, 0) if source.json_page_field else 0
    for page in range(page_limit):
        if source.json_page_field:
            body[source.json_page_field] = initial_page + page
        if before_request:
            before_request(str(source.json_url))
        if source.json_method == "post":
            payload = _public_post_json(
                session, str(source.json_url), dict(body), source.request_timeout_seconds
            )
        else:
            payload = _public_get_json(session, str(source.json_url), source.request_timeout_seconds)
        current = _json_feed_items(source, payload)
        if not source.json_page_field:
            items.extend(current)
            break
        total = None
        if source.json_total_path:
            total = _resolve_json_path(payload, source.json_total_path)
            if type(total) is not int or total < 0:
                raise ATSSourceError("json_feed 分页总数不是非负整数")
            if expected_total is not None and total != expected_total:
                raise ATSSourceError("json_feed 扫描期间记录总数变化，请重新扫描")
            expected_total = total
        if not current:
            if total is not None and len(items) < total:
                raise ATSSourceError("json_feed 分页提前返回空页，未收齐声明的记录")
            break
        signature = json.dumps(current, sort_keys=True, ensure_ascii=False)
        if signature in seen_pages:
            raise ATSSourceError("json_feed 分页重复返回同一页，拒绝将不完整列表当成成功")
        seen_pages.add(signature)
        identities: set[str] = set()
        id_paths = source.json_mapping.get("source_id") or _DEFAULT_MAPPING["source_id"]
        for row in current:
            record_id = _first_matching_path(row, id_paths) if isinstance(row, dict) else None
            key = ["id", str(record_id)] if record_id is not None else ["row", row]
            identities.add(json.dumps(key, sort_keys=True, ensure_ascii=False))
        if identities & seen_records or len(identities) != len(current):
            raise ATSSourceError("json_feed 分页记录发生重叠或重复，请重新扫描")
        seen_records.update(identities)
        items.extend(current)
        if total is not None and len(items) >= total:
            break
    else:
        raise ATSSourceError("json_feed 达到分页上限，列表可能尚未完整，请调整 json_max_pages")

    mapping = source.json_mapping
    jobs: list[ATSJob] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        def field(name: str, data: dict[str, Any]) -> Any:
            explicit = mapping.get(name)
            if explicit:
                value = _first_matching_path(data, explicit)
                if value is not None:
                    return value
            return _first_matching_path(data, _DEFAULT_MAPPING.get(name, []))

        title = str(field("title", item) or "").strip()
        if not title:
            continue
        description = str(field("description", item) or "").strip()
        if "<" in description:
            description = _html_to_text(description)
        requirements = str(field("requirements", item) or "").strip()
        if "<" in requirements:
            requirements = _html_to_text(requirements)
        if requirements and requirements not in description:
            description = f"{description}\n\n任职要求：\n{requirements}".strip()
        location_value = field("location", item)
        if isinstance(location_value, list):
            location = "、".join(str(value).strip() for value in location_value if value)
        elif isinstance(location_value, dict):
            location = str(location_value.get("name") or "").strip()
        else:
            location = str(location_value or "").strip()
        remote_value = field("remote", item)
        remote = bool(remote_value)
        if isinstance(remote_value, str):
            remote = remote_value.casefold() in {"true", "1", "remote", "yes", "是"}
        jobs.append(
            ATSJob(
                source_id=str(field("source_id", item) or ""),
                title=title,
                description=description,
                requirements=requirements or None,
                location=location or None,
                apply_url=str(field("apply_url", item) or source.fallback_apply_url or "") or None,
                job_url=str(field("job_url", item) or "") or None,
                published_at=_normalize_datetime(field("published_at", item)),
                recruitment_type=str(field("recruitment_type", item) or "") or None,
                remote=remote,
            )
        )
    return jobs


def _public_post_json(
    session: requests.Session,
    url: str,
    body: dict[str, Any],
    timeout: float,
) -> Any:
    """Send one configured POST to a public JSON endpoint; never replay across redirects."""

    PublicTargetPolicy().ensure_public(url)
    response = session.post(url, json=body, timeout=timeout, allow_redirects=False)
    try:
        if 300 <= response.status_code < 400:
            raise ATSSourceError("json_feed POST 被重定向，未向新目标重放请求")
        response.raise_for_status()
        return response.json()
    finally:
        response.close()


def _public_get_json(
    session: requests.Session,
    url: str,
    timeout: float,
) -> Any:
    """带公共网络策略校验的 GET，防止 json_feed 把本机变内网代理。"""

    policy = PublicTargetPolicy()
    current = url
    for _ in range(_MAX_REDIRECTS):
        policy.ensure_public(current)
        response = session.get(current, timeout=timeout, allow_redirects=False)
        if response.status_code not in {301, 302, 303, 307, 308}:
            break
        location = response.headers.get("Location")
        response.close()
        if not location:
            raise requests.RequestException("json_feed 重定向缺少 Location")
        current = urljoin(current, location)
    else:
        raise requests.RequestException("json_feed 重定向次数过多")
    response.raise_for_status()
    try:
        return response.json()
    finally:
        response.close()


def fetch_ats_jobs(
    source: AtsSourceConfig,
    session: requests.Session | None = None,
    *,
    before_request: Callable[[str], None] | None = None,
) -> list[ATSJob]:
    """按配置类型调用对应适配器；网络/解析失败统一转为 ATSSourceError。"""

    owned_session = session is None
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", "Career-Radar/1.2 (job monitor)")
    try:
        if source.type == AtsSourceType.GREENHOUSE:
            return _greenhouse_jobs(source, session)
        if source.type == AtsSourceType.LEVER:
            return _lever_jobs(source, session)
        if source.type == AtsSourceType.ASHBY:
            return _ashby_jobs(source, session)
        if source.type == AtsSourceType.JSON_FEED:
            return _json_feed_jobs(source, session, before_request)
        raise ATSSourceError(f"暂不支持的 ATS 类型：{source.type}")
    except (requests.RequestException, ValueError, KeyError, TypeError, UnsafeTargetError) as exc:
        raise ATSSourceError(f"{source.type.value} 接口请求失败：{exc}") from exc
    finally:
        if owned_session:
            session.close()


def ats_jobs_to_postings(
    jobs: list[ATSJob],
    company: CompanyConfig,
) -> list[JobPosting]:
    """把归一化岗位转成入库标准结构，保持去重/变更检测/通知链路不变。"""

    postings: list[JobPosting] = []
    for job in jobs:
        title = job.title.strip()
        if not title:
            continue
        description = (job.description or "").strip()
        apply_url = job.apply_url or job.job_url
        cohort = re.search(r"(?<!\d)(?:20)?(2\d)(?:届|校招|秋招|春招)", title)
        cohort_year = 2000 + int(cohort.group(1)) if cohort else None
        source = company.ats_source
        source_namespace = (
            f"{source.type.value}:{source.tenant or urlsplit(source.json_url or '').netloc}"
            if source else company.url
        )
        postings.append(
            JobPosting(
                record_type="job",
                company=company.name,
                title=title[:300],
                location=job.location,
                description=description,
                requirements=job.requirements,
                recruitment_type=job.recruitment_type,
                target_graduates=f"{cohort_year} 届" if cohort_year else None,
                is_2026_target=cohort_year == 2026 if cohort_year else None,
                match_level=MatchLevel.MEDIUM if cohort_year == 2026 else MatchLevel.LOW,
                match_reason=f"官网标题明确面向 {cohort_year} 届" if cohort_year else "官网未明确标注目标毕业届别",
                published_at=job.published_at,
                apply_url=apply_url,
                source_url=job.job_url or company.url,
                source_job_id=f"{source_namespace}:{job.source_id}" if job.source_id else None,
                jd_complete=bool(
                    description
                    and (
                        not company.ats_source
                        or "requirements" not in company.ats_source.json_mapping
                        or job.requirements
                    )
                ),
                jd_incomplete_reason=(
                    None
                    if description
                    and (
                        not company.ats_source
                        or "requirements" not in company.ats_source.json_mapping
                        or job.requirements
                    )
                    else "ATS 接口未返回完整 JD"
                ),
            )
        )
    return postings
