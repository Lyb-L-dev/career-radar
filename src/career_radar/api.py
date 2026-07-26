"""Career Radar 本地 FastAPI 管理接口。

服务默认只绑定 ``127.0.0.1``，读取现有 ``config.yaml`` 和 SQLite。所有 API Key
仍只存在于后端进程环境变量中，接口最多返回“已配置”状态，绝不返回密钥或后四位。
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .api_applications import create_applications_router
from .api_candidates import create_candidates_router
from .api_companies import create_companies_router
from .api_jobs import create_jobs_router
from .api_notifications import create_notifications_router
from .api_reports import create_reports_router, report_items
from .api_reputation import create_reputation_router
from .api_runs import create_runs_router
from .api_wechat import create_wechat_router
from .application_manager import ApplicationManager
from .config import ConfigError, is_api_key_placeholder
from .config_editor import mutate_config_blocks, update_config_blocks
from .llm import create_provider
from .mailer import MailError, send_test_email
from .models import CandidateProfile
from .reputation import ReputationManager
from .run_manager import RunManager
from .web_repository import WebRepository
from .wechat_recruitment import WechatRecruitmentManager


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


class BasicSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str
    outputDir: str = Field(min_length=1, max_length=500)
    dbPath: str = Field(min_length=1, max_length=500)
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
    return not is_api_key_placeholder(os.getenv(variable))


_EXTERNAL_PATH_MARKER = "已配置到项目目录外"


def _public_settings_path(path: Path, config_root: Path) -> str:
    """设置接口只展示项目内相对路径，不公开本机绝对目录。"""

    try:
        return path.resolve().relative_to(config_root.resolve()).as_posix()
    except ValueError:
        return _EXTERNAL_PATH_MARKER


def _validated_settings_path(value: str, label: str) -> str | None:
    """接受项目内相对路径；外部路径标记表示保持现有配置不变。"""

    normalized = value.strip()
    if normalized == _EXTERNAL_PATH_MARKER:
        return None
    candidate = Path(normalized)
    if (
        candidate.is_absolute()
        or bool(candidate.drive)
        or ".." in candidate.parts
        or normalized.startswith("~")
        or "$" in normalized
        or "%" in normalized
    ):
        raise HTTPException(422, f"{label}必须使用项目目录内的相对路径")
    return normalized.replace("\\", "/")


def _settings_json(settings, config_root: Path) -> dict[str, Any]:  # type: ignore[no-untyped-def]
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
            "outputDir": _public_settings_path(settings.app.output_dir, config_root),
            "dbPath": _public_settings_path(settings.app.database_path, config_root),
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


def _resolve_default_web_dist(backend_root: Path) -> Path:
    """优先使用仓库内前端，并兼容迁移前的同级目录。"""

    dist_candidates = (
        backend_root / "web" / "dist",
        backend_root.parent / "career-radar-web" / "dist",
    )
    return next(
        (path for path in dist_candidates if (path / "index.html").is_file()),
        dist_candidates[0],
    )


def create_app(
    config_path: str | Path = "config.yaml",
    web_dist: str | Path | None = None,
) -> FastAPI:
    config_file = Path(config_path).expanduser().resolve()
    repository = WebRepository(config_file)
    repository.initialize()
    run_manager = RunManager(repository)
    reputation_manager = ReputationManager(repository)
    application_manager = ApplicationManager(repository)
    wechat_recruitment_manager = WechatRecruitmentManager(repository)

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
    app.state.application_manager = application_manager
    app.state.wechat_recruitment_manager = wechat_recruitment_manager
    app.add_middleware(
        CORSMiddleware,
        allow_origins=repository.settings.app.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(create_jobs_router(repository))
    app.include_router(create_applications_router(repository, application_manager))
    app.include_router(create_reputation_router(repository, reputation_manager))
    app.include_router(create_runs_router(repository, run_manager))
    app.include_router(create_reports_router(repository))
    app.include_router(create_notifications_router(repository))
    app.include_router(create_candidates_router(repository, config_file))
    app.include_router(create_companies_router(repository, config_file))
    app.include_router(
        create_wechat_router(repository, wechat_recruitment_manager)
    )

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

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

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return _settings_json(repository.settings, config_file.parent)

    @app.put("/api/settings")
    def save_settings(settings_payload: SettingsPayload) -> dict[str, bool]:
        payload = settings_payload.model_dump()
        basic = payload["basic"]
        crawler_input = payload["crawler"]
        llm_input = payload["llm"]
        email = payload["email"]
        database_path = _validated_settings_path(str(basic["dbPath"]), "数据库位置")
        output_dir = _validated_settings_path(str(basic["outputDir"]), "输出目录")

        def update_settings(raw: dict[str, Any]) -> tuple[dict[str, Any], None]:
            app_block = dict(raw["app"])
            crawler = dict(raw["crawler"])
            llm = dict(raw["llm"])
            smtp = dict(raw.get("smtp") or {})
            app_updates = {
                "timezone": str(basic["timezone"]).split(" ", 1)[0],
                "daily_run_time": basic["dailyRunTime"],
                "report_retention_days": int(basic["reportRetentionDays"]),
                "notify_match_levels": [email["minMatchLevel"]],
                "notify_max_difficulty_score": int(email["maxDifficulty"]),
            }
            if database_path is not None:
                app_updates["database_path"] = database_path
            if output_dir is not None:
                app_updates["output_dir"] = output_dir
            app_block.update(app_updates)
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
            return {"app": app_block, "crawler": crawler, "llm": llm, "smtp": smtp}, None

        try:
            mutate_config_blocks(config_file, update_settings)
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
        candidate_dist = _resolve_default_web_dist(backend_root)
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
