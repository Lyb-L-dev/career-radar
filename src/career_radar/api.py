"""Career Radar 本地 FastAPI 应用装配入口。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api_applications import create_applications_router
from .api_automation import create_automation_router
from .api_candidates import create_candidates_router
from .api_companies import create_companies_router
from .api_growth import create_growth_router
from .api_jobs import create_jobs_router
from .api_notifications import create_notifications_router
from .api_overview import create_overview_router
from .api_platform_leads import create_platform_leads_router
from .api_profile import create_profile_router
from .api_reports import create_reports_router
from .api_reputation import create_reputation_router
from .api_runs import create_runs_router
from .api_settings import create_settings_router
from .api_wechat import create_wechat_router
from .application_manager import ApplicationManager
from .automation import AutomationService
from .boss_capture import BossCaptureManager
from .growth.manager import GrowthManager
from .growth.repository import GrowthRepository
from .growth.service import GrowthService
from .local_request_guard import LocalRequestGuardMiddleware
from .official_screening_service import OfficialScreeningManager
from .platform_leads import BossLeadRepository
from .reputation import ReputationManager
from .run_manager import RunManager
from .task_coordinator import TaskCoordinator
from .web_repository import WebRepository
from .wechat_recruitment import WechatRecruitmentManager


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


def _mount_web_app(app: FastAPI, candidate_dist: Path) -> None:
    """在 API 路由之后挂载构建产物，并为 SPA 深链接提供回退。"""

    if not candidate_dist.is_dir() or not (candidate_dist / "index.html").is_file():
        return
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


def create_app(
    config_path: str | Path = "config.yaml",
    web_dist: str | Path | None = None,
) -> FastAPI:
    """装配本地应用；领域行为由各自路由模块和后台管理器负责。"""

    config_file = Path(config_path).expanduser().resolve()
    repository = WebRepository(config_file)
    repository.initialize()
    platform_leads = BossLeadRepository(repository.settings.app.database_path)
    platform_leads.initialize()
    boss_capture = BossCaptureManager(platform_leads, lambda: repository.settings, config_file.parent)
    task_coordinator = TaskCoordinator()
    growth_repository = GrowthRepository(repository.settings.app.database_path)
    growth_repository.seed()
    growth_service = GrowthService(growth_repository, repository, platform_leads)
    growth_manager = GrowthManager(growth_service, task_coordinator)
    official_screening = OfficialScreeningManager(repository, task_coordinator)
    run_manager = RunManager(repository, task_coordinator)
    reputation_manager = ReputationManager(repository, task_coordinator)
    application_manager = ApplicationManager(repository, task_coordinator)
    wechat_recruitment_manager = WechatRecruitmentManager(
        repository,
        coordinator=task_coordinator,
    )
    automation_service = AutomationService(config_file)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        repository.initialize()
        platform_leads.initialize()
        try:
            yield
        finally:
            task_coordinator.shutdown()
            await asyncio.gather(
                asyncio.to_thread(run_manager.shutdown),
                asyncio.to_thread(reputation_manager.shutdown),
                asyncio.to_thread(application_manager.shutdown),
                asyncio.to_thread(wechat_recruitment_manager.shutdown),
                asyncio.to_thread(official_screening.shutdown),
                asyncio.to_thread(growth_manager.shutdown),
            )

    app = FastAPI(
        title="Career Radar Local API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.repository = repository
    app.state.platform_leads = platform_leads
    app.state.boss_capture = boss_capture
    app.state.run_manager = run_manager
    app.state.reputation_manager = reputation_manager
    app.state.application_manager = application_manager
    app.state.wechat_recruitment_manager = wechat_recruitment_manager
    app.state.task_coordinator = task_coordinator
    app.state.official_screening = official_screening
    app.state.automation_service = automation_service
    app.state.growth_service = growth_service
    app.state.growth_manager = growth_manager
    app.add_middleware(
        CORSMiddleware,
        allow_origins=repository.settings.app.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.add_middleware(
        LocalRequestGuardMiddleware,
        allowed_origins=repository.settings.app.cors_origins,
    )

    app.include_router(create_overview_router(repository))
    app.include_router(create_growth_router(growth_service, growth_manager))
    app.include_router(create_profile_router(repository, config_file))
    app.include_router(create_settings_router(repository, config_file))
    app.include_router(create_jobs_router(repository, official_screening))
    app.include_router(create_platform_leads_router(platform_leads, repository, boss_capture))
    app.include_router(create_automation_router(repository, automation_service))
    app.include_router(create_applications_router(repository, application_manager))
    app.include_router(create_reputation_router(repository, reputation_manager))
    app.include_router(create_runs_router(repository, run_manager))
    app.include_router(create_reports_router(repository))
    app.include_router(create_notifications_router(repository))
    app.include_router(create_candidates_router(repository, config_file))
    app.include_router(create_companies_router(repository, config_file))
    app.include_router(create_wechat_router(repository, wechat_recruitment_manager))

    backend_root = Path(__file__).resolve().parents[2]
    candidate_dist = (
        _resolve_default_web_dist(backend_root)
        if web_dist is None
        else Path(web_dist).expanduser().resolve()
    )
    _mount_web_app(app, candidate_dist)
    return app
