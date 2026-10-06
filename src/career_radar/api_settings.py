"""本地设置、连通性测试与维护操作路由。"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .config import ConfigError, is_api_key_placeholder
from .config_editor import mutate_config_blocks
from .llm import create_provider
from .mailer import MailError, send_test_email
from .maintenance import LocalMaintenance
from .notifications import NotificationError, send_test_notification
from .public_errors import public_error_message
from .web_repository import WebRepository

_EXTERNAL_PATH_MARKER = "已配置到项目目录外"


class BasicSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str
    outputDir: str = Field(min_length=1, max_length=500)
    dbPath: str = Field(min_length=1, max_length=500)
    dailyRunTime: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    reportRetentionDays: int = Field(ge=7, le=3650)
    backupRetentionCount: int = Field(ge=1, le=100)


class CrawlerSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minDelay: float = Field(ge=0)
    maxDelay: float = Field(ge=0)
    defaultRenderMode: str = Field(pattern=r"^(auto|static|dynamic)$")
    minContentLength: int = Field(ge=0)
    maxPagesPerCompany: int = Field(ge=1, le=5000)
    maxLlmPagesPerRun: int = Field(ge=1, le=5000)
    requestTimeout: float = Field(gt=0)
    respectRobots: bool


class LlmSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["DeepSeek", "MiMo"]
    model: str = Field(min_length=1)
    apiBaseUrl: str = ""
    apiKeyMasked: str = ""
    apiKeyConfigured: bool = False
    jsonOutput: bool = True
    maxChunkLength: int = Field(ge=10_000)
    chunkOverlap: int = Field(ge=0)
    timeout: float = Field(gt=0)
    retries: int = Field(ge=1, le=10)


class PaidActionConfirmation(BaseModel):
    """产生模型费用的操作必须携带明确确认。"""

    model_config = ConfigDict(extra="forbid")
    confirmed: bool = False


class BackupDeletePayload(BaseModel):
    """删除私有备份必须由用户明确确认。"""

    model_config = ConfigDict(extra="forbid")
    confirmed: bool = False


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


class AppriseSettingsPayload(BaseModel):
    """Apprise URL 属于敏感配置，接口只接收和返回聚合状态。"""

    model_config = ConfigDict(extra="forbid")
    enabled: bool
    urlCount: int = Field(ge=0, le=50)
    configured: bool


class SettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    basic: BasicSettingsPayload
    crawler: CrawlerSettingsPayload
    llm: LlmSettingsPayload
    email: EmailSettingsPayload
    apprise: AppriseSettingsPayload


def _api_key_configured(provider: str) -> bool:
    if provider == "litellm":
        return any(
            not is_api_key_placeholder(os.getenv(name))
            for name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
        )
    variable = {
        "deepseek": "DEEPSEEK_API_KEY",
        "mimo": "XIAOMIMIMO_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }[provider]
    return not is_api_key_placeholder(os.getenv(variable))


def _public_settings_path(path: Path, config_root: Path) -> str:
    """设置接口只展示项目内相对路径，不公开本机绝对目录。"""

    try:
        return path.resolve().relative_to(config_root.resolve()).as_posix()
    except ValueError:
        return _EXTERNAL_PATH_MARKER


def _validated_settings_path(value: str, label: str) -> str | None:
    """接受项目内相对路径；外部路径标记表示保持原配置不变。"""

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


def settings_json(settings: Any, config_root: Path) -> dict[str, Any]:
    """生成稳定、脱敏的设置视图。"""

    render_mode = {"auto": "auto", "never": "static", "always": "dynamic"}[
        settings.crawler.render_mode
    ]
    provider_label = {
        "deepseek": "DeepSeek",
        "mimo": "MiMo",
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "litellm": "LiteLLM",
    }[settings.llm.provider]
    encryption = (
        "SSL"
        if settings.smtp.use_ssl
        else ("STARTTLS" if settings.smtp.use_starttls else "none")
    )
    return {
        "basic": {
            "timezone": settings.app.timezone,
            "outputDir": _public_settings_path(settings.app.output_dir, config_root),
            "dbPath": _public_settings_path(settings.app.database_path, config_root),
            "dailyRunTime": settings.app.daily_run_time,
            "reportRetentionDays": settings.app.report_retention_days,
            "backupRetentionCount": settings.app.backup_retention_count,
        },
        "crawler": {
            "minDelay": settings.crawler.request_delay_min_seconds,
            "maxDelay": settings.crawler.request_delay_max_seconds,
            "defaultRenderMode": render_mode,
            "minContentLength": settings.crawler.min_static_text_chars,
            "maxPagesPerCompany": settings.crawler.max_pages_per_company,
            "maxLlmPagesPerRun": settings.crawler.max_llm_pages_per_run,
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
        "apprise": {
            "enabled": settings.apprise.enabled,
            "urlCount": len(settings.apprise.urls),
            "configured": bool(settings.apprise.urls),
        },
    }


def create_settings_router(repository: WebRepository, config_file: Path) -> APIRouter:
    """创建设置路由；调用方只需提供仓库与配置文件 seam。"""

    router = APIRouter(prefix="/api/settings", tags=["settings"])
    local_maintenance = LocalMaintenance(repository, config_file)

    @router.get("")
    def get_settings() -> dict[str, Any]:
        return settings_json(repository.settings, config_file.parent)

    @router.put("")
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
                "backup_retention_count": int(basic["backupRetentionCount"]),
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
                    "render_mode": {
                        "auto": "auto",
                        "static": "never",
                        "dynamic": "always",
                    }[crawler_input["defaultRenderMode"]],
                    "min_static_text_chars": int(crawler_input["minContentLength"]),
                    "max_pages_per_company": int(crawler_input["maxPagesPerCompany"]),
                    "max_llm_pages_per_run": int(crawler_input["maxLlmPagesPerRun"]),
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

    @router.get("/test-llm/preflight")
    def test_llm_preflight() -> dict[str, Any]:
        settings = repository.settings
        return {
            "requiresConfirmation": True,
            "provider": "MiMo" if settings.llm.provider == "mimo" else (
                "DeepSeek" if settings.llm.provider == "deepseek" else settings.llm.provider
            ),
            "model": settings.llm.model,
            "estimatedCalls": 1,
            "message": "连接测试会发送一次最小结构化请求，可能产生少量费用。",
        }

    @router.post("/test-llm")
    async def test_llm(payload: PaidActionConfirmation) -> dict[str, Any]:
        if not payload.confirmed:
            raise HTTPException(428, "请先确认本次测试会产生一次模型 API 调用")
        if repository.settings.llm.provider not in {"deepseek", "mimo"}:
            raise HTTPException(422, "当前部署只允许测试 DeepSeek 或 MiMo 连接")

        def call() -> tuple[int, str]:
            settings = repository.settings
            provider = create_provider(settings.llm)
            started = time.perf_counter()
            provider.analyze(
                "这是连接测试。请返回 page_type=no_jobs、"
                "contains_recruitment_info=false、jobs=[]、follow_links=[] 的 JSON。"
            )
            return int((time.perf_counter() - started) * 1000), settings.llm.model

        try:
            latency, model = await asyncio.to_thread(call)
        except Exception as exc:
            raise HTTPException(
                502,
                public_error_message(
                    exc,
                    context=(
                        "MiMo 连接测试"
                        if repository.settings.llm.provider == "mimo"
                        else "DeepSeek 连接测试"
                    ),
                ),
            ) from exc
        return {"ok": True, "latencyMs": latency, "model": model}

    @router.post("/test-email")
    async def test_email() -> dict[str, Any]:
        try:
            await asyncio.to_thread(send_test_email, repository.settings.smtp)
        except MailError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"ok": True, "message": "测试邮件已发送，请检查收件箱"}

    @router.post("/test-apprise")
    async def test_apprise() -> dict[str, Any]:
        try:
            await asyncio.to_thread(send_test_notification, repository.settings.apprise)
        except NotificationError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"ok": True, "message": "测试推送已发送，请检查对应渠道"}

    @router.get("/db-stats")
    def db_stats() -> dict[str, Any]:
        return repository.database_stats()

    @router.get("/backups")
    def backups() -> list[dict[str, Any]]:
        return local_maintenance.list_backups()

    @router.post("/backups/{backup_name}/verify")
    def verify_backup(backup_name: str) -> dict[str, Any]:
        try:
            return local_maintenance.verify_backup(backup_name)
        except FileNotFoundError as exc:
            raise HTTPException(404, "备份不存在") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.delete("/backups/{backup_name}")
    def delete_backup(
        backup_name: str,
        payload: BackupDeletePayload,
    ) -> dict[str, Any]:
        if not payload.confirmed:
            raise HTTPException(428, "请先确认删除这份本地备份")
        try:
            return local_maintenance.delete_backup(backup_name)
        except FileNotFoundError as exc:
            raise HTTPException(404, "备份不存在") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/maintenance/{action}")
    def maintenance(action: str) -> dict[str, Any]:
        try:
            return local_maintenance.run(action)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    return router
