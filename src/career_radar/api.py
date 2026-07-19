"""Career Radar 本地 FastAPI 管理接口。

服务默认只绑定 ``127.0.0.1``，读取现有 ``config.yaml`` 和 SQLite。所有 API Key
仍只存在于后端进程环境变量中，接口最多返回“已配置”状态，绝不返回密钥或后四位。
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .api_jobs import create_jobs_router
from .api_notifications import create_notifications_router
from .api_reports import create_reports_router, report_items
from .api_reputation import create_reputation_router
from .api_runs import create_runs_router
from .company_catalog import (
    CompanyCatalogError,
    catalog_response,
    find_catalog_candidate,
    load_company_catalog,
)
from .config import ConfigError
from .config_editor import load_raw_config, update_config_blocks
from .crawler import PageFetcher
from .discovery import parse_html, ranked_prompt_links
from .llm import create_provider
from .mailer import MailError, send_test_email
from .models import CandidateProfile
from .reputation import ReputationManager
from .run_manager import RunManager
from .web_repository import WebRepository


class SkillPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    level: str = Field(pattern=r"^(了解|熟悉|熟练)$")


class ProjectPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=10_000)
    skills: list[str] = Field(default_factory=list)


class ProfilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gradYear: str
    degree: str
    schoolBackground: str
    major: str
    targetRoles: list[str]
    cities: list[str]
    salaryRange: list[int] = Field(min_length=2, max_length=2)
    acceptInternship: bool
    acceptRelocation: bool
    maxDifficulty: int = Field(ge=1, le=10)
    workTypes: list[str]
    skills: list[SkillPayload]
    projects: list[ProjectPayload]
    internships: list[str]
    excludedDirections: list[str]
    notes: str = ""
    completeness: int = Field(default=0, ge=0, le=100)


class CompanyCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    website: str
    careersUrl: str | None = None
    companyType: str = Field(
        default="private",
        pattern=r"^(central_soe|local_soe|private|foreign|joint_venture|other)$",
    )
    industryCategory: str = Field(
        default="other",
        pattern=r"^(internet|gaming|pet|enterprise_software|ai_data|iot|fintech|telecom|energy|manufacturing|consumer|other)$",
    )
    province: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    priority: str = Field(default="medium", pattern=r"^(high|medium|low)$")
    monitorMode: str = Field(default="jobs", pattern=r"^(jobs|notices|both)$")
    governmentHonors: list[str] = Field(default_factory=list, max_length=50)
    evidenceUrls: list[str] = Field(default_factory=list, max_length=50)
    renderMode: str = Field(default="auto", pattern=r"^(auto|static|dynamic)$")
    maxPages: int = Field(default=120, ge=1, le=5000)
    enabled: bool = True
    note: str | None = Field(default=None, max_length=2000)


class CompanyPatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website: str | None = None
    careersUrl: str | None = None
    companyType: str | None = Field(
        default=None,
        pattern=r"^(central_soe|local_soe|private|foreign|joint_venture|other)$",
    )
    industryCategory: str | None = Field(
        default=None,
        pattern=r"^(internet|gaming|pet|enterprise_software|ai_data|iot|fintech|telecom|energy|manufacturing|consumer|other)$",
    )
    province: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    priority: str | None = Field(default=None, pattern=r"^(high|medium|low)$")
    monitorMode: str | None = Field(default=None, pattern=r"^(jobs|notices|both)$")
    governmentHonors: list[str] | None = Field(default=None, max_length=50)
    evidenceUrls: list[str] | None = Field(default=None, max_length=50)
    maxPages: int | None = Field(default=None, ge=1, le=5000)
    enabled: bool | None = None
    status: str | None = Field(default=None, pattern=r"^(active|paused)$")
    note: str | None = Field(default=None, max_length=2000)


class CandidateReviewPayload(BaseModel):
    """候选企业的本地审批结果；不会因此自动启动网络抓取。"""

    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern=r"^(pending|shortlisted|rejected)$")
    officialWebsite: str | None = None
    careersUrl: str | None = None
    companyType: str | None = Field(
        default=None,
        pattern=r"^(central_soe|local_soe|private|foreign|joint_venture|other)$",
    )
    industryCategory: str | None = Field(
        default=None,
        pattern=r"^(internet|gaming|pet|enterprise_software|ai_data|iot|fintech|telecom|energy|manufacturing|consumer|other)$",
    )
    note: str | None = Field(default=None, max_length=2000)


class CandidateBulkReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=500)
    decision: str = Field(pattern=r"^(pending|shortlisted|rejected)$")


class CandidateMonitorPayload(BaseModel):
    """人工核验官网后，把候选企业提升为正式监控配置。"""

    model_config = ConfigDict(extra="forbid")
    website: str
    careersUrl: str | None = None
    companyType: str = Field(
        default="other",
        pattern=r"^(central_soe|local_soe|private|foreign|joint_venture|other)$",
    )
    industryCategory: str | None = Field(
        default=None,
        pattern=r"^(internet|gaming|pet|enterprise_software|ai_data|iot|fintech|telecom|energy|manufacturing|consumer|other)$",
    )
    monitorMode: str = Field(default="jobs", pattern=r"^(jobs|notices|both)$")
    maxPages: int = Field(default=20, ge=1, le=5000)
    enabled: bool = False
    note: str | None = Field(default=None, max_length=2000)


class BasicSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str
    outputDir: str
    dbPath: str
    dailyRunTime: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    reportRetentionDays: int = Field(ge=7, le=3650)


class CrawlerSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minDelay: float = Field(ge=0)
    maxDelay: float = Field(ge=0)
    defaultRenderMode: str = Field(pattern=r"^(auto|static|dynamic)$")
    minContentLength: int = Field(ge=0)
    maxPagesPerCompany: int = Field(ge=1, le=5000)
    requestTimeout: float = Field(gt=0)
    respectRobots: bool


class LlmSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(pattern=r"^(DeepSeek|OpenAI|Anthropic)$")
    model: str = Field(min_length=1)
    apiBaseUrl: str = ""
    apiKeyMasked: str = ""
    apiKeyConfigured: bool = False
    jsonOutput: bool = True
    maxChunkLength: int = Field(ge=10_000)
    chunkOverlap: int = Field(ge=0)
    timeout: float = Field(gt=0)
    retries: int = Field(ge=1, le=10)


class EmailSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    smtpHost: str
    smtpPort: int = Field(ge=1, le=65535)
    encryption: str = Field(pattern=r"^(SSL|STARTTLS|none)$")
    fromAddress: str
    toAddresses: list[str]
    sendOnNew: bool
    sendOnUpdate: bool
    minMatchLevel: str = Field(pattern=r"^(high|medium|low|unknown)$")
    maxDifficulty: int = Field(ge=1, le=10)


class SettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    basic: BasicSettingsPayload
    crawler: CrawlerSettingsPayload
    llm: LlmSettingsPayload
    email: EmailSettingsPayload


class CompanyTestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    website: str
    careersUrl: str | None = None


def _safe_public_url(value: str) -> str:
    """拒绝明显的本机/内网目标，降低 Web 表单被滥用于 SSRF 的风险。"""

    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
        raise ValueError("必须填写不含账号密码的公开 HTTP(S) URL")
    hostname = parts.hostname.casefold()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ValueError("不允许监控本机或 .local 地址")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return value
    if not address.is_global:
        raise ValueError("不允许监控私网、回环、链路本地或保留 IP")
    return value


def _profile_json(candidate: CandidateProfile) -> dict[str, Any]:
    skills = [
        {
            "name": name,
            "level": candidate.skill_levels.get(
                name,
                "了解" if any(word in name for word in ("基础", "认知", "了解")) else "熟悉",
            ),
        }
        for name in candidate.skills
    ]
    projects = []
    for index, value in enumerate(candidate.projects, 1):
        name, separator, description = value.partition("：")
        if not separator:
            name, separator, description = value.partition(":")
        if not separator:
            name, description = f"项目 {index}", value
        matched_skills = [skill["name"] for skill in skills if skill["name"] in value]
        projects.append(
            {
                "id": f"project-{index}",
                "name": name.strip(),
                "description": description.strip(),
                "skills": matched_skills,
            }
        )
    completed = sum(
        bool(item)
        for item in (
            candidate.major,
            candidate.skills,
            candidate.projects,
            candidate.target_roles,
            candidate.preferred_locations,
            candidate.constraints,
        )
    )
    degree = "本科" if "本科" in candidate.education_level else candidate.education_level
    return {
        "gradYear": f"{candidate.graduation_year} 届",
        "degree": degree,
        "schoolBackground": candidate.school_background,
        "major": candidate.major,
        "targetRoles": candidate.target_roles,
        "cities": candidate.preferred_locations,
        "salaryRange": candidate.salary_range_k,
        "acceptInternship": candidate.accept_internship,
        "acceptRelocation": candidate.accept_relocation,
        "maxDifficulty": candidate.max_difficulty,
        "workTypes": candidate.work_types,
        "skills": skills,
        "projects": projects,
        "internships": candidate.internships,
        "excludedDirections": candidate.excluded_directions,
        "notes": candidate.notes,
        "completeness": round(completed / 6 * 100),
    }


def _api_key_configured(provider: str) -> bool:
    variable = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }[provider]
    value = os.getenv(variable, "").strip().casefold()
    return bool(value and "your-" not in value and not value.endswith("api-key"))


def _settings_json(settings) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    render_mode = {"auto": "auto", "never": "static", "always": "dynamic"}[
        settings.crawler.render_mode
    ]
    provider_label = {
        "deepseek": "DeepSeek",
        "openai": "OpenAI",
        "anthropic": "Anthropic",
    }[settings.llm.provider]
    encryption = "SSL" if settings.smtp.use_ssl else ("STARTTLS" if settings.smtp.use_starttls else "none")
    return {
        "basic": {
            "timezone": settings.app.timezone,
            "outputDir": str(settings.app.output_dir),
            "dbPath": str(settings.app.database_path),
            "dailyRunTime": settings.app.daily_run_time,
            "reportRetentionDays": settings.app.report_retention_days,
        },
        "crawler": {
            "minDelay": settings.crawler.request_delay_min_seconds,
            "maxDelay": settings.crawler.request_delay_max_seconds,
            "defaultRenderMode": render_mode,
            "minContentLength": settings.crawler.min_static_text_chars,
            "maxPagesPerCompany": settings.crawler.max_pages_per_company,
            "requestTimeout": settings.crawler.request_timeout_seconds,
            "respectRobots": True,
        },
        "llm": {
            "provider": provider_label,
            "model": settings.llm.model,
            "apiBaseUrl": settings.llm.base_url or "",
            "apiKeyMasked": "••••••••" if _api_key_configured(settings.llm.provider) else "",
            "apiKeyConfigured": _api_key_configured(settings.llm.provider),
            "jsonOutput": True,
            "maxChunkLength": settings.llm.max_input_chars,
            "chunkOverlap": settings.llm.chunk_overlap_chars,
            "timeout": settings.llm.request_timeout_seconds,
            "retries": settings.llm.max_retries,
        },
        "email": {
            "enabled": settings.smtp.enabled,
            "smtpHost": settings.smtp.host,
            "smtpPort": settings.smtp.port,
            "encryption": encryption,
            "fromAddress": settings.smtp.from_address,
            "toAddresses": settings.smtp.to_addresses,
            "sendOnNew": True,
            "sendOnUpdate": settings.app.include_updates_in_output,
            "minMatchLevel": settings.app.notify_match_levels[0].value,
            "maxDifficulty": settings.app.notify_max_difficulty_score,
        },
    }


def create_app(
    config_path: str | Path = "config.yaml",
    web_dist: str | Path | None = None,
) -> FastAPI:
    config_file = Path(config_path).expanduser().resolve()
    repository = WebRepository(config_file)
    repository.initialize()
    run_manager = RunManager(repository)
    reputation_manager = ReputationManager(repository)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        repository.initialize()
        yield

    app = FastAPI(
        title="Career Radar Local API",
        version="1.2.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.repository = repository
    app.state.run_manager = run_manager
    app.state.reputation_manager = reputation_manager
    app.add_middleware(
        CORSMiddleware,
        allow_origins=repository.settings.app.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(create_jobs_router(repository))
    app.include_router(create_reputation_router(repository, reputation_manager))
    app.include_router(create_runs_router(repository, run_manager))
    app.include_router(create_reports_router(repository))
    app.include_router(create_notifications_router(repository))

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "config": str(config_file), "database": str(repository.settings.app.database_path)}

    @app.get("/api/profile")
    def get_profile() -> dict[str, Any]:
        return _profile_json(repository.settings.candidate)

    @app.put("/api/profile")
    def save_profile(payload: ProfilePayload) -> dict[str, bool]:
        current = repository.settings.candidate.model_dump(mode="json")
        match = re.search(r"(20\d{2})", payload.gradYear)
        if not match:
            raise HTTPException(422, "毕业届别必须包含四位年份")
        current.update(
            {
                "graduation_year": int(match.group(1)),
                "education_level": payload.degree,
                "school_background": payload.schoolBackground.strip(),
                "major": payload.major.strip(),
                "skills": [skill.name.strip() for skill in payload.skills],
                "skill_levels": {skill.name.strip(): skill.level for skill in payload.skills},
                "projects": [f"{project.name}：{project.description}" for project in payload.projects],
                "internships": [item.strip() for item in payload.internships if item.strip()],
                "target_roles": payload.targetRoles,
                "preferred_locations": payload.cities,
                "salary_range_k": payload.salaryRange,
                "accept_internship": payload.acceptInternship,
                "accept_relocation": payload.acceptRelocation,
                "max_difficulty": payload.maxDifficulty,
                "work_types": payload.workTypes,
                "excluded_directions": payload.excludedDirections,
                "notes": payload.notes.strip(),
            }
        )
        candidate = CandidateProfile.model_validate(current)
        update_config_blocks(config_file, {"candidate": candidate.model_dump(mode="json")})
        return {"ok": True}

    @app.post("/api/profile/recalculate")
    def recalculate_profile() -> dict[str, Any]:
        # 重新抓取时 LLM 会按新画像评分；历史 payload 不应在没有原始页面时被伪造重算。
        return {"ok": True, "updated": 0, "message": "新画像将在下一次真实扫描中生效"}

    def current_catalog() -> dict[str, Any]:
        try:
            return load_company_catalog(repository.settings.app.company_catalog_path)
        except CompanyCatalogError as exc:
            raise HTTPException(500, str(exc)) from exc

    @app.get("/api/company-candidates")
    def list_company_candidates(
        q: str = Query(default="", max_length=200),
        province: str | None = Query(default=None, max_length=100),
        city: str | None = Query(default=None, max_length=100),
        fitLevel: str | None = Query(default=None, pattern=r"^(high|medium|low)$"),
        decision: str | None = Query(
            default=None,
            pattern=r"^(pending|shortlisted|rejected|monitored)$",
        ),
        sourceKey: str | None = Query(default=None, max_length=200),
        techOnly: bool = False,
        page: int = Query(default=1, ge=1),
        pageSize: int = Query(default=50, ge=10, le=100),
    ) -> dict[str, Any]:
        """分页查询千家官方名单候选池；只读静态证据，不访问候选企业网站。"""

        return catalog_response(
            current_catalog(),
            profile=repository.settings.candidate,
            states=repository.candidate_states(),
            monitored_names={company.name for company in repository.settings.companies},
            query=q,
            province=province,
            city=city,
            fit_level=fitLevel,
            decision=decision,
            source_key=sourceKey,
            tech_only=techOnly,
            page=page,
            page_size=pageSize,
        )

    @app.patch("/api/company-candidates/review-many")
    def review_many_candidates(payload: CandidateBulkReviewPayload) -> dict[str, Any]:
        catalog = current_catalog()
        known_ids = {item["id"] for item in catalog["items"]}
        unknown = [candidate_id for candidate_id in payload.ids if candidate_id not in known_ids]
        if unknown:
            raise HTTPException(404, f"存在未知候选企业：{unknown[0]}")
        repository.set_candidate_state(payload.ids, decision=payload.decision)
        return {"ok": True, "updated": len(payload.ids)}

    @app.get("/api/company-candidates/{candidate_id}")
    def get_company_candidate(candidate_id: str) -> dict[str, Any]:
        catalog = current_catalog()
        raw = find_catalog_candidate(catalog, candidate_id)
        if raw is None:
            raise HTTPException(404, "候选企业不存在")
        response = catalog_response(
            catalog,
            profile=repository.settings.candidate,
            states=repository.candidate_states(),
            monitored_names={company.name for company in repository.settings.companies},
            query=raw["name"],
            page=1,
            page_size=100,
        )
        item = next((entry for entry in response["items"] if entry["id"] == candidate_id), None)
        if item is None:  # pragma: no cover - 精确名称必然命中，仅作为数据损坏保护
            raise HTTPException(500, "候选企业索引异常")
        return item

    @app.patch("/api/company-candidates/{candidate_id}")
    def review_company_candidate(
        candidate_id: str,
        payload: CandidateReviewPayload,
    ) -> dict[str, bool]:
        if find_catalog_candidate(current_catalog(), candidate_id) is None:
            raise HTTPException(404, "候选企业不存在")
        website = payload.officialWebsite
        careers_url = payload.careersUrl
        try:
            if website:
                website = _safe_public_url(website)
            if careers_url:
                careers_url = _safe_public_url(careers_url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        repository.set_candidate_state(
            [candidate_id],
            decision=payload.decision,
            official_website=website,
            careers_url=careers_url,
            company_type=payload.companyType,
            industry_category=payload.industryCategory,
            note=payload.note,
        )
        return {"ok": True}

    @app.post("/api/company-candidates/{candidate_id}/monitor")
    def monitor_company_candidate(
        candidate_id: str,
        payload: CandidateMonitorPayload,
    ) -> dict[str, Any]:
        candidate = find_catalog_candidate(current_catalog(), candidate_id)
        if candidate is None:
            raise HTTPException(404, "候选企业不存在")
        try:
            website = _safe_public_url(payload.website)
            careers_url = _safe_public_url(payload.careersUrl) if payload.careersUrl else None
            target_url = careers_url or website
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        raw = load_raw_config(config_file)
        companies = list(raw.get("companies") or [])
        normalized_name = candidate["name"].strip().casefold()
        if any(str(item.get("name", "")).strip().casefold() == normalized_name for item in companies):
            raise HTTPException(409, "该候选企业已经在监控列表中")

        industry = payload.industryCategory or candidate.get("suggestedIndustryCategory") or "other"
        source_note = f"候选库来源：{candidate['sourceTitle']}。员工体验与劳动风险仍需人工背调。"
        companies.append(
            {
                "name": candidate["name"],
                "url": target_url,
                "company_type": payload.companyType,
                "industry_category": industry,
                "province": candidate.get("province"),
                "city": candidate.get("city"),
                "priority": "high" if candidate.get("province") == "福建" else "medium",
                "monitor_mode": payload.monitorMode,
                "government_honors": [candidate["sourceTitle"]],
                "evidence_urls": [candidate["evidenceUrl"]],
                "enabled": payload.enabled,
                "discover_from_homepage": False if payload.careersUrl else "auto",
                "max_pages": payload.maxPages,
                "notes": payload.note.strip() if payload.note else source_note,
            }
        )
        update_config_blocks(config_file, {"companies": companies})
        repository.set_candidate_state(
            [candidate_id],
            decision="shortlisted",
            official_website=website,
            careers_url=careers_url,
            company_type=payload.companyType,
            industry_category=industry,
            note=payload.note,
        )
        return next(
            item for item in repository.list_companies() if item["name"] == candidate["name"]
        )

    @app.get("/api/companies")
    def list_companies() -> list[dict[str, Any]]:
        return repository.list_companies()

    @app.get("/api/companies/{identifier}")
    def get_company(identifier: str) -> dict[str, Any]:
        company = next((item for item in repository.list_companies() if item["id"] == identifier), None)
        if company is None:
            raise HTTPException(404, "企业不存在")
        return company

    @app.post("/api/companies")
    def add_company(payload: CompanyCreatePayload) -> dict[str, Any]:
        try:
            url = _safe_public_url(payload.careersUrl or payload.website)
            _safe_public_url(payload.website)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        raw = load_raw_config(config_file)
        companies = list(raw.get("companies") or [])
        if any(str(item.get("name", "")).casefold() == payload.name.strip().casefold() for item in companies):
            raise HTTPException(409, "企业名称已存在")
        companies.append(
            {
                "name": payload.name.strip(),
                "url": url,
                "company_type": payload.companyType,
                "industry_category": payload.industryCategory,
                "province": payload.province,
                "city": payload.city,
                "priority": payload.priority,
                "monitor_mode": payload.monitorMode,
                "government_honors": payload.governmentHonors,
                "evidence_urls": payload.evidenceUrls,
                "enabled": payload.enabled,
                "discover_from_homepage": False if payload.careersUrl else "auto",
                "max_pages": payload.maxPages,
                "notes": payload.note,
            }
        )
        update_config_blocks(config_file, {"companies": companies})
        return next(item for item in repository.list_companies() if item["name"] == payload.name.strip())

    @app.patch("/api/companies/{identifier}")
    def update_company(identifier: str, payload: CompanyPatchPayload) -> dict[str, bool]:
        patch = payload.model_dump(exclude_unset=True)
        found = repository.find_company(identifier)
        if found is None:
            raise HTTPException(404, "企业不存在")
        index, current = found
        raw = load_raw_config(config_file)
        companies = list(raw["companies"])
        item = dict(companies[index])
        if "name" in patch:
            item["name"] = str(patch["name"]).strip()
        if "website" in patch or "careersUrl" in patch:
            value = patch.get("careersUrl") or patch.get("website") or current.url
            try:
                item["url"] = _safe_public_url(str(value))
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
        if "enabled" in patch:
            item["enabled"] = bool(patch["enabled"])
        if "companyType" in patch:
            item["company_type"] = patch["companyType"]
        if "industryCategory" in patch:
            item["industry_category"] = patch["industryCategory"]
        if "province" in patch:
            item["province"] = patch["province"]
        if "city" in patch:
            item["city"] = patch["city"]
        if "priority" in patch:
            item["priority"] = patch["priority"]
        if "monitorMode" in patch:
            item["monitor_mode"] = patch["monitorMode"]
        if "governmentHonors" in patch:
            item["government_honors"] = patch["governmentHonors"]
        if "evidenceUrls" in patch:
            item["evidence_urls"] = patch["evidenceUrls"]
        if "maxPages" in patch:
            item["max_pages"] = patch["maxPages"]
        if patch.get("status") == "paused":
            item["enabled"] = False
        elif patch.get("status") == "active":
            item["enabled"] = True
        if "note" in patch:
            item["notes"] = patch["note"]
        companies[index] = item
        update_config_blocks(config_file, {"companies": companies})
        return {"ok": True}

    @app.delete("/api/companies/{identifier}")
    def remove_company(identifier: str) -> dict[str, bool]:
        found = repository.find_company(identifier)
        if found is None:
            raise HTTPException(404, "企业不存在")
        index, _company = found
        raw = load_raw_config(config_file)
        companies = list(raw["companies"])
        del companies[index]
        if not companies:
            raise HTTPException(422, "至少保留一家企业配置")
        update_config_blocks(config_file, {"companies": companies})
        return {"ok": True}

    @app.post("/api/companies/test")
    async def test_company(payload: CompanyTestPayload) -> dict[str, Any]:
        try:
            target = _safe_public_url(payload.careersUrl or payload.website)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        def probe() -> dict[str, Any]:
            settings = repository.settings
            with PageFetcher(settings.crawler) as fetcher:
                page = fetcher.fetch(target)
            document = parse_html(page.html, page.final_url)
            links = ranked_prompt_links(document, 100)
            entry = next(
                (link.url for link in links if link.career_score > 0 or link.job_score > 0),
                None,
            )
            return {
                "robotsAllowed": True,
                "homepageReachable": True,
                "entryFound": bool(entry or payload.careersUrl),
                "entryUrl": entry or (target if payload.careersUrl else None),
                "needsBrowserRender": page.rendered,
                "estimatedPages": sum(link.career_score > 0 or link.job_score > 0 for link in links),
            }

        try:
            return await asyncio.to_thread(probe)
        except Exception as exc:
            raise HTTPException(400, f"连接测试失败：{type(exc).__name__}: {exc}") from exc

    @app.get("/api/companies/{identifier}/pages")
    def company_pages(identifier: str) -> list[dict[str, Any]]:
        if repository.find_company(identifier) is None:
            raise HTTPException(404, "企业不存在")
        return repository.list_company_pages(identifier)

    @app.get("/api/companies/{identifier}/errors")
    def company_errors(identifier: str) -> list[dict[str, Any]]:
        found = repository.find_company(identifier)
        if found is None:
            raise HTTPException(404, "企业不存在")
        _index, company = found
        errors = []
        for run in repository.list_runs()[:50]:
            for result in run.get("companies", []):
                if result.get("companyName") == company.name and result.get("error"):
                    errors.append(
                        {
                            "time": run.get("finishedAt") or run["startedAt"],
                            "message": result["error"].splitlines()[0],
                            "technicalDetail": result["error"],
                        }
                    )
        return errors

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return _settings_json(repository.settings)

    @app.put("/api/settings")
    def save_settings(settings_payload: SettingsPayload) -> dict[str, bool]:
        payload = settings_payload.model_dump()
        raw = load_raw_config(config_file)
        app_block = dict(raw["app"])
        crawler = dict(raw["crawler"])
        llm = dict(raw["llm"])
        smtp = dict(raw.get("smtp") or {})
        basic = payload["basic"]
        crawler_input = payload["crawler"]
        llm_input = payload["llm"]
        email = payload["email"]

        app_block.update(
            {
                "timezone": str(basic["timezone"]).split(" ", 1)[0],
                "database_path": basic["dbPath"],
                "output_dir": basic["outputDir"],
                "daily_run_time": basic["dailyRunTime"],
                "report_retention_days": int(basic["reportRetentionDays"]),
                "notify_match_levels": [email["minMatchLevel"]],
                "notify_max_difficulty_score": int(email["maxDifficulty"]),
            }
        )
        crawler.update(
            {
                "request_delay_min_seconds": float(crawler_input["minDelay"]),
                "request_delay_max_seconds": float(crawler_input["maxDelay"]),
                "render_mode": {"auto": "auto", "static": "never", "dynamic": "always"}[
                    crawler_input["defaultRenderMode"]
                ],
                "min_static_text_chars": int(crawler_input["minContentLength"]),
                "max_pages_per_company": int(crawler_input["maxPagesPerCompany"]),
                "request_timeout_seconds": float(crawler_input["requestTimeout"]),
            }
        )
        llm.update(
            {
                "provider": str(llm_input["provider"]).casefold(),
                "model": llm_input["model"],
                "base_url": llm_input["apiBaseUrl"] or None,
                "max_input_chars": int(llm_input["maxChunkLength"]),
                "chunk_overlap_chars": int(llm_input["chunkOverlap"]),
                "request_timeout_seconds": float(llm_input["timeout"]),
                "max_retries": int(llm_input["retries"]),
            }
        )
        encryption = email["encryption"]
        smtp.update(
            {
                "enabled": bool(email["enabled"]),
                "host": email["smtpHost"],
                "port": int(email["smtpPort"]),
                "use_ssl": encryption == "SSL",
                "use_starttls": encryption == "STARTTLS",
                "username": smtp.get("username") or email["fromAddress"],
                "from_address": email["fromAddress"],
                "to_addresses": email["toAddresses"],
            }
        )
        try:
            update_config_blocks(
                config_file,
                {"app": app_block, "crawler": crawler, "llm": llm, "smtp": smtp},
            )
        except ConfigError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"ok": True}

    @app.post("/api/settings/test-llm")
    async def test_llm() -> dict[str, Any]:
        def call() -> tuple[int, str]:
            settings = repository.settings
            provider = create_provider(settings.llm)
            started = time.perf_counter()
            provider.analyze("这是连接测试。请返回 page_type=no_jobs、contains_recruitment_info=false、jobs=[]、follow_links=[] 的 JSON。")
            return int((time.perf_counter() - started) * 1000), settings.llm.model

        try:
            latency, model = await asyncio.to_thread(call)
        except Exception as exc:
            raise HTTPException(502, f"LLM 连接失败：{type(exc).__name__}: {exc}") from exc
        return {"ok": True, "latencyMs": latency, "model": model}

    @app.post("/api/settings/test-email")
    async def test_email() -> dict[str, Any]:
        try:
            await asyncio.to_thread(send_test_email, repository.settings.smtp)
        except MailError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"ok": True, "message": "测试邮件已发送，请检查收件箱"}

    @app.get("/api/settings/db-stats")
    def db_stats() -> dict[str, Any]:
        return repository.database_stats()

    @app.post("/api/settings/maintenance/{action}")
    def maintenance(action: str) -> dict[str, Any]:
        settings = repository.settings
        if action == "rebuildIndex":
            with repository.transaction() as connection:
                connection.execute("REINDEX")
            return {"ok": True, "message": "SQLite 索引已重建"}
        if action == "recalcMatch":
            return {"ok": True, "message": "新画像将在下一次真实扫描中生效"}
        if action == "clearLogs":
            for path in settings.app.log_dir.glob("*.log*"):
                path.write_text("", encoding="utf-8")
            return {"ok": True, "message": "运行日志已清空"}
        if action == "cleanReports":
            raise HTTPException(409, "为避免误删日报，请在文件系统中手工归档")
        if action == "export":
            raise HTTPException(409, "请直接备份 data、output 和 config.yaml")
        raise HTTPException(404, "未知维护操作")

    @app.get("/api/dashboard")
    def dashboard() -> dict[str, Any]:
        settings = repository.settings
        jobs = repository.list_jobs()
        runs = repository.list_runs()
        today = datetime.now(ZoneInfo(settings.app.timezone)).date().isoformat()
        today_new = [job for job in jobs if job.get("firstSeenAt", "").startswith(today)]
        today_updated = [
            job
            for job in jobs
            if job["status"] == "updated" and job.get("lastUpdatedAt", "").startswith(today)
        ]
        companies = repository.list_companies()
        success = sum(company["status"] == "active" for company in companies)
        pending = sum(company["status"] == "pending_verification" for company in companies)
        last_scan = (
            (runs[0].get("finishedAt") or runs[0]["startedAt"])
            if runs
            else max((job["lastUpdatedAt"] for job in jobs), default=datetime.now().isoformat())
        )
        attention = []
        if pending:
            attention.append(
                {
                    "id": "pending-companies",
                    "kind": "verify",
                    "text": f"{pending} 家企业尚无真实岗位记录，建议运行首次扫描",
                    "actionLabel": "查看企业",
                    "link": "/companies",
                }
            )
        if not settings.smtp.enabled:
            attention.append(
                {
                    "id": "smtp-disabled",
                    "kind": "smtp",
                    "text": "SMTP 尚未开启，邮件提醒当前不可用",
                    "actionLabel": "前往设置",
                    "link": "/settings?tab=email",
                }
            )
        return {
            "todayNew": len(today_new),
            "todayNewDelta": 0,
            "todayUpdated": len(today_updated),
            "todayUpdatedDelta": 0,
            "highMatch": sum(job["abilityMatch"] == "high" for job in jobs),
            "highMatchDelta": 0,
            "monitoredCompanies": sum(company["enabled"] for company in companies),
            "lastScanAt": last_scan,
            "environment": {
                **repository.environment(),
                "successCompanies": success,
                "pendingCompanies": pending,
            },
            "attentionItems": attention,
        }

    @app.get("/api/search")
    def search(q: str = Query(min_length=1, max_length=200), limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
        keyword = q.casefold().strip()
        jobs = repository.search_jobs(keyword, limit)
        companies = [
            company
            for company in repository.list_companies()
            if keyword in " ".join((company["name"], company["website"], company["note"] or "")).casefold()
        ][:limit]
        reports = [item for item in report_items(repository) if keyword in f"{item['date']} {item['summary']}".casefold()][:limit]
        runs = [item for item in repository.list_runs() if keyword in f"{item['code']} {item['status']}".casefold()][:limit]
        return {"jobs": jobs, "companies": companies, "reports": reports, "runs": runs}

    if web_dist is None:
        backend_root = Path(__file__).resolve().parents[2]
        candidate_dist = backend_root.parent / "career-radar-web" / "dist"
    else:
        candidate_dist = Path(web_dist).expanduser().resolve()
    if candidate_dist.is_dir() and (candidate_dist / "index.html").is_file():
        assets = candidate_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):  # type: ignore[no-untyped-def]
            if full_path.startswith("api/"):
                raise HTTPException(404, "API 路径不存在")
            requested = (candidate_dist / full_path).resolve()
            if requested.is_file() and candidate_dist in requested.parents:
                return FileResponse(requested)
            return FileResponse(candidate_dist / "index.html")

    return app
