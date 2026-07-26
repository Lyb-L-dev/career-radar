"""本地 FastAPI 接口测试：确保 Web 展示和写入都来自真实配置与 SQLite。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import yaml
from fastapi.testclient import TestClient

import career_radar.web_repository as web_repository_module
from career_radar.api import _resolve_default_web_dist, create_app
from career_radar.application.document_renderer import file_sha256
from career_radar.application.models import ApplicationArtifact, ApplicationStatus
from career_radar.application.repository import ApplicationRepository
from career_radar.application.service import ApplicationService
from career_radar.application_manager import ApplicationManager
from career_radar.config import load_settings
from career_radar.models import JobPosting, MatchLevel, ProfileFitLevel
from career_radar.storage import JobStorage
from career_radar.web_repository import WebRepository


def _config() -> str:
    """生成不访问网络的最小合法配置。"""

    return """
app:
  timezone: Asia/Shanghai
  database_path: data/test.db
  output_dir: output
  log_dir: logs
crawler:
  render_mode: never
  request_delay_min_seconds: 0
  request_delay_max_seconds: 0
  user_agent: Mozilla/5.0 Career Radar API test browser
llm:
  provider: deepseek
  model: test-model
application:
  enabled: true
  profile_path: private/application_profile.yaml
  output_dir: private/application_outputs
  pdf_mode: never
smtp:
  enabled: false
candidate:
  graduation_year: 2026
  education_level: 普通本科
  school_background: 普通本科，非 985/211
  major: 数据科学与大数据技术
  skills: [Python, MySQL]
  projects: [数据分析平台：使用 Python 与 MySQL 完成数据处理]
  internships: [暂无正式实习经历]
  target_roles: [数据开发]
  preferred_locations: [上海, 杭州]
  skill_levels: {Python: 熟悉, MySQL: 熟悉}
  notes: 测试画像说明
companies:
  - name: 测试公司
    url: https://example.com/careers
    company_type: local_soe
"""


def _job() -> JobPosting:
    return JobPosting(
        company="测试公司",
        title="Python 数据开发工程师",
        location="上海",
        description="负责公开数据采集、清洗、入库和数据服务开发。",
        requirements="熟悉 Python 与 MySQL，面向 2026 届本科毕业生。",
        recruitment_type="校招",
        is_2026_target=True,
        target_graduates="2026 届",
        published_at="2026-07-18",
        apply_url="https://example.com/apply/1",
        source_url="https://example.com/jobs/1",
        match_level=MatchLevel.HIGH,
        match_reason="明确面向 2026 届",
        profile_fit_level=ProfileFitLevel.HIGH,
        profile_fit_reason="技能和目标方向均匹配",
        difficulty_score=5,
    )


def _client(tmp_path: Path) -> tuple[TestClient, Path]:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_config(), encoding="utf-8")
    app = create_app(config_path, web_dist=tmp_path / "missing-dist")
    return TestClient(app), config_path


def _write_application_profile(config_path: Path) -> None:
    """写入只供测试使用的已确认私有画像。"""

    profile_path = config_path.parent / "private" / "application_profile.yaml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "verification_status": "confirmed",
                "contact": {
                    "name": "接口隐私测试候选人",
                    "phone": "13800000000",
                    "email": "private-candidate@example.com",
                    "location": "福建福州",
                },
                "education": [
                    {
                        "institution": "测试大学",
                        "degree": "本科",
                        "major": "数据科学",
                        "start_date": "2022.09",
                        "end_date": "2026.06",
                        "source_ids": ["confirmed-profile"],
                    }
                ],
                "experiences": [],
                "projects": [],
                "skills": [],
                "awards": [],
                "leadership": [],
                "preferences": {
                    "target_roles": ["数据开发"],
                    "preferred_locations": ["福州"],
                    "cover_letter_mode": "auto",
                    "resume_page_target": 1,
                },
                "sources": [
                    {
                        "id": "confirmed-profile",
                        "kind": "user_confirmed",
                        "imported_at": "2026-07-22T08:00:00+08:00",
                        "visually_verified": True,
                    }
                ],
                "review_notes": [],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_candidate_catalog(config_path: Path) -> None:
    """写入两个最小候选记录，测试审批与提升监控时不依赖正式大文件。"""

    catalog_path = config_path.parent / "data" / "company_candidates.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    items = [
        {
            "id": "candidate-fujian-data",
            "name": "福建示例数据科技有限公司",
            "sourceRegion": "福建省",
            "province": "福建",
            "city": None,
            "sourceKey": "official-test",
            "sourceTitle": "官方测试名单",
            "evidenceUrl": "https://www.miit.gov.cn/example.pdf",
            "sourceSequence": 1,
            "qualityEvidenceScore": 85,
            "qualitySignals": ["官方名单"],
            "techSignals": ["数据/软件"],
            "suggestedIndustryCategory": "ai_data",
            "dueDiligenceStatus": "unverified",
        },
        {
            "id": "candidate-hebei-manufacturing",
            "name": "河北示例制造有限公司",
            "sourceRegion": "河北省",
            "province": "河北",
            "city": None,
            "sourceKey": "official-test",
            "sourceTitle": "官方测试名单",
            "evidenceUrl": "https://www.miit.gov.cn/example.pdf",
            "sourceSequence": 2,
            "qualityEvidenceScore": 85,
            "qualitySignals": ["官方名单"],
            "techSignals": [],
            "suggestedIndustryCategory": "manufacturing",
            "dueDiligenceStatus": "unverified",
        },
    ]
    catalog_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "generatedAt": "2026-07-19",
                "total": 2,
                "disclaimer": "测试候选不代表员工体验背书",
                "sources": [
                    {
                        "key": "official-test",
                        "title": "官方测试名单",
                        "url": "https://www.miit.gov.cn/example.pdf",
                        "count": 2,
                    }
                ],
                "items": items,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_health_profile_and_companies_are_loaded_from_yaml(tmp_path: Path) -> None:
    client, _config_path = _client(tmp_path)

    with client:
        assert client.get("/api/health").json()["ok"] is True
        profile = client.get("/api/profile").json()
        companies = client.get("/api/companies").json()

    assert profile["major"] == "数据科学与大数据技术"
    assert profile["schoolBackground"] == "普通本科，非 985/211"
    assert profile["internships"] == ["暂无正式实习经历"]
    assert companies[0]["name"] == "测试公司"
    assert companies[0]["website"] == "https://example.com/careers"
    assert companies[0]["companyType"] == "local_soe"


def test_health_and_settings_do_not_expose_absolute_local_paths(tmp_path: Path) -> None:
    client, _config_path = _client(tmp_path)

    with client:
        health = client.get("/api/health")
        settings = client.get("/api/settings")

    assert health.json() == {"ok": True}
    assert settings.status_code == 200
    assert settings.json()["basic"]["outputDir"] == "output"
    assert settings.json()["basic"]["dbPath"] == "data/test.db"
    assert str(tmp_path) not in json.dumps(settings.json(), ensure_ascii=False)


def test_settings_reject_absolute_paths_without_changing_config(tmp_path: Path) -> None:
    client, config_path = _client(tmp_path)
    before = config_path.read_bytes()

    with client:
        payload = client.get("/api/settings").json()
        payload["basic"]["dbPath"] = str((tmp_path / "outside.db").resolve())
        response = client.put("/api/settings", json=payload)

    assert response.status_code == 422
    assert "相对路径" in response.json()["detail"]
    assert config_path.read_bytes() == before


def test_settings_mask_and_preserve_existing_external_path(tmp_path: Path) -> None:
    config_root = tmp_path / "project"
    config_root.mkdir()
    external_database = (tmp_path / "external.db").resolve()
    config_path = config_root / "config.yaml"
    config_path.write_text(
        _config().replace("data/test.db", external_database.as_posix()),
        encoding="utf-8",
    )
    client = TestClient(create_app(config_path, web_dist=tmp_path / "missing-dist"))

    with client:
        payload = client.get("/api/settings").json()
        saved = client.put("/api/settings", json=payload)

    assert payload["basic"]["dbPath"] == "已配置到项目目录外"
    assert str(tmp_path) not in json.dumps(payload, ensure_ascii=False)
    assert saved.status_code == 200
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["app"]["database_path"] == external_database.as_posix()


def test_monorepo_web_dist_is_preferred_with_legacy_fallback(tmp_path: Path) -> None:
    backend_root = tmp_path / "career-radar"
    internal = backend_root / "web" / "dist"
    legacy = tmp_path / "career-radar-web" / "dist"
    legacy.mkdir(parents=True)
    (legacy / "index.html").write_text("legacy", encoding="utf-8")

    assert _resolve_default_web_dist(backend_root) == legacy

    internal.mkdir(parents=True)
    (internal / "index.html").write_text("monorepo", encoding="utf-8")

    assert _resolve_default_web_dist(backend_root) == internal


def test_profile_update_is_validated_and_written_back(tmp_path: Path) -> None:
    client, config_path = _client(tmp_path)

    with client:
        profile = client.get("/api/profile").json()
        profile["cities"] = ["深圳", "广州"]
        profile["maxDifficulty"] = 7
        profile["notes"] = "已通过前端更新"
        response = client.put("/api/profile", json=profile)

    assert response.status_code == 200
    saved = load_settings(config_path).candidate
    assert saved.preferred_locations == ["深圳", "广州"]
    assert saved.max_difficulty == 7
    assert saved.notes == "已通过前端更新"
    assert config_path.with_suffix(".yaml.bak").is_file()


def test_jobs_and_favorite_state_come_from_sqlite(tmp_path: Path) -> None:
    client, config_path = _client(tmp_path)
    storage = JobStorage(load_settings(config_path).app.database_path)
    event = storage.store_jobs([_job()], "2026-07-18T09:47:00+08:00")[0]

    with client:
        jobs = client.get("/api/jobs").json()
        favorite = client.post(
            f"/api/jobs/{event.entity_key}/favorite",
            json={"value": True},
        )
        detail = client.get(f"/api/jobs/{event.entity_key}").json()

    assert jobs[0]["title"] == "Python 数据开发工程师"
    assert jobs[0]["companyType"] == "local_soe"
    assert jobs[0]["gradYearMatch"] == "high"
    assert jobs[0]["difficulty"] == 5
    assert favorite.json() == {"isFavorite": True}
    assert detail["isFavorite"] is True
    assert detail["jdText"] == _job().description


def test_job_list_loads_settings_once_per_request(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_config(), encoding="utf-8")
    repository = WebRepository(config_path)
    repository.initialize()
    settings = load_settings(config_path)
    second = _job().model_copy(
        update={
            "title": "第二个 Python 岗位",
            "source_url": "https://example.com/jobs/2",
            "apply_url": "https://example.com/apply/2",
        }
    )
    JobStorage(settings.app.database_path).store_jobs(
        [_job(), second],
        "2026-07-18T09:47:00+08:00",
    )
    original_load_settings = web_repository_module.load_settings
    calls = 0

    def counted_load_settings(path):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return original_load_settings(path)

    monkeypatch.setattr(web_repository_module, "load_settings", counted_load_settings)

    jobs = repository.list_jobs()

    assert len(jobs) == 2
    assert calls == 1


def test_user_stopped_company_is_not_classified_as_unmonitorable(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_config(), encoding="utf-8")
    repository = WebRepository(config_path)
    repository.initialize()
    payload = {
        "id": "run-stopped",
        "status": "interrupted",
        "startedAt": "2026-07-23T09:00:00+08:00",
        "companies": [
            {
                "companyName": "测试公司",
                "status": "skipped",
                "skipReason": "user_stop",
            }
        ],
    }
    repository.save_run(payload)

    companies = repository.list_companies()

    assert companies[0]["status"] == "pending_verification"


def test_job_search_uses_sql_filter_and_returns_matching_rows(tmp_path: Path) -> None:
    """搜索应命中标题、公司或 JD，同时保留与列表一致的 JSON 结构。"""

    client, config_path = _client(tmp_path)
    storage = JobStorage(load_settings(config_path).app.database_path)
    storage.store_jobs([_job()], "2026-07-18T09:47:00+08:00")

    with client:
        response = client.get("/api/search", params={"q": "MySQL"})

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Python 数据开发工程师"
    assert jobs[0]["companyName"] == "测试公司"


def test_default_cors_origins_allow_local_frontend(tmp_path: Path) -> None:
    client, _config_path = _client(tmp_path)

    with client:
        response = client.get(
            "/api/health",
            headers={"Origin": "http://127.0.0.1:7100"},
        )

    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:7100"


def test_existing_cli_events_are_imported_as_honest_run_summary(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_config(), encoding="utf-8")
    storage = JobStorage(load_settings(config_path).app.database_path)
    storage.initialize()
    storage.store_jobs([_job()], "2026-07-18T09:47:00+08:00")
    client = TestClient(create_app(config_path, web_dist=tmp_path / "missing-dist"))

    with client:
        runs = client.get("/api/runs").json()

    assert len(runs) == 1
    assert runs[0]["code"].startswith("CLI-")
    assert runs[0]["newJobs"] == 1
    assert runs[0]["companies"][0]["companyName"] == "测试公司"
    assert "旧版" in runs[0]["logs"][0]["message"]


def test_company_api_rejects_private_network_targets(tmp_path: Path) -> None:
    client, _config_path = _client(tmp_path)

    with client:
        response = client.post(
            "/api/companies",
            json={
                "name": "不安全目标",
                "website": "http://127.0.0.1:9000",
                "renderMode": "auto",
                "maxPages": 20,
                "enabled": True,
            },
        )

    assert response.status_code == 422
    assert "不允许监控" in response.json()["detail"]


def test_company_route_modules_preserve_public_api_contract(tmp_path: Path) -> None:
    client, _config_path = _client(tmp_path)

    schema = client.app.openapi()

    expected_methods = {
        "/api/companies": {"get", "post"},
        "/api/companies/bulk-delete": {"post"},
        "/api/companies/{identifier}": {"get", "patch", "delete"},
        "/api/companies/test": {"post"},
        "/api/company-candidates": {"get"},
        "/api/company-candidates/review-many": {"patch"},
        "/api/company-candidates/{candidate_id}/monitor": {"post"},
        "/api/company-candidates/{candidate_id}/sources": {"get", "post"},
    }
    for path, methods in expected_methods.items():
        assert path in schema["paths"]
        assert methods <= set(schema["paths"][path])


def test_company_bulk_delete_is_atomic_and_keeps_one_company(tmp_path: Path) -> None:
    client, config_path = _client(tmp_path)

    with client:
        for index in (2, 3):
            response = client.post(
                "/api/companies",
                json={
                    "name": f"批量删除测试公司 {index}",
                    "website": f"https://example{index}.com/careers",
                },
            )
            assert response.status_code == 200
        companies = client.get("/api/companies").json()
        selected_ids = [item["id"] for item in companies if "批量删除" in item["name"]]
        before_stale = config_path.read_bytes()

        stale = client.post(
            "/api/companies/bulk-delete",
            json={"ids": [selected_ids[0], "c-does-not-exist"]},
        )
        after_stale_bytes = config_path.read_bytes()
        after_stale = client.get("/api/companies").json()
        deleted = client.post(
            "/api/companies/bulk-delete",
            json={"ids": [*selected_ids, selected_ids[0]]},
        )
        remaining = client.get("/api/companies").json()
        delete_last = client.post(
            "/api/companies/bulk-delete",
            json={"ids": [remaining[0]["id"]]},
        )

    assert stale.status_code == 404
    assert after_stale_bytes == before_stale
    assert len(after_stale) == 3
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True, "deleted": 2}
    assert [item["name"] for item in remaining] == ["测试公司"]
    assert delete_last.status_code == 422
    assert [company.name for company in load_settings(config_path).companies] == ["测试公司"]


def test_single_company_run_request_reaches_run_manager(tmp_path: Path) -> None:
    client, _config_path = _client(tmp_path)
    company = client.get("/api/companies").json()[0]
    captured: dict[str, object] = {}

    def fake_create(scope: str, send_email: bool, selected_company_id: str | None = None):
        captured.update(
            scope=scope,
            send_email=send_email,
            selected_company_id=selected_company_id,
        )
        return {"id": "run-test"}

    client.app.state.run_manager.create = fake_create
    with client:
        response = client.post(
            "/api/runs",
            json={"scope": "company", "companyId": company["id"], "sendEmail": False},
        )

    assert response.status_code == 202
    assert response.json() == {"ok": True, "runId": "run-test"}
    assert captured == {
        "scope": "company",
        "send_email": False,
        "selected_company_id": company["id"],
    }


def test_company_type_run_request_reaches_run_manager(tmp_path: Path) -> None:
    client, _config_path = _client(tmp_path)
    captured: dict[str, object] = {}

    def fake_create(
        scope: str,
        send_email: bool,
        selected_company_id: str | None = None,
        selected_company_type: str | None = None,
    ) -> dict[str, str]:
        captured.update(
            scope=scope,
            send_email=send_email,
            selected_company_id=selected_company_id,
            selected_company_type=selected_company_type,
        )
        return {"id": "run-company-type"}

    client.app.state.run_manager.create = fake_create
    with client:
        response = client.post(
            "/api/runs",
            json={
                "scope": "company_type",
                "companyType": "central_soe",
                "sendEmail": False,
            },
        )

    assert response.status_code == 202
    assert response.json() == {"ok": True, "runId": "run-company-type"}
    assert captured["selected_company_type"] == "central_soe"


def test_reputation_endpoints_use_job_and_background_manager(tmp_path: Path) -> None:
    client, config_path = _client(tmp_path)
    storage = JobStorage(load_settings(config_path).app.database_path)
    event = storage.store_jobs([_job()], "2026-07-18T09:47:00+08:00")[0]
    scan = {
        "id": "rep-test",
        "jobId": event.entity_key,
        "status": "completed",
        "evidence": [],
        "analysis": None,
    }
    manager = client.app.state.reputation_manager
    manager.health = lambda: {"enabled": True, "available": True, "platforms": []}
    manager.create = lambda job_id: {**scan, "jobId": job_id}
    manager.latest = lambda job_id: {**scan, "jobId": job_id}
    manager.get = lambda scan_id: {**scan, "id": scan_id}

    with client:
        health = client.get("/api/reputation/health")
        started = client.post(f"/api/jobs/{event.entity_key}/reputation-scan")
        latest = client.get(f"/api/jobs/{event.entity_key}/reputation")
        detail = client.get("/api/reputation-scans/rep-test")
        missing_job = client.get("/api/jobs/not-a-job/reputation")

    assert health.json()["available"] is True
    assert started.status_code == 202
    assert started.json() == {"ok": True, "scanId": "rep-test"}
    assert latest.json()["jobId"] == event.entity_key
    assert detail.json()["id"] == "rep-test"
    assert missing_job.status_code == 404


def test_candidate_catalog_can_be_filtered_reviewed_and_promoted_safely(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_config(), encoding="utf-8")
    _write_candidate_catalog(config_path)
    client = TestClient(create_app(config_path, web_dist=tmp_path / "missing-dist"))

    with client:
        page = client.get(
            "/api/company-candidates",
            params={"province": "福建", "techOnly": True, "pageSize": 10},
        )
        review = client.patch(
            "/api/company-candidates/candidate-fujian-data",
            json={"decision": "shortlisted", "note": "等待核验双休与岗位边界"},
        )
        shortlisted = client.get(
            "/api/company-candidates",
            params={"decision": "shortlisted", "pageSize": 10},
        )
        promoted = client.post(
            "/api/company-candidates/candidate-fujian-data/monitor",
            json={
                "website": "https://example.org",
                "careersUrl": "https://example.org/careers",
                "companyType": "private",
                "industryCategory": "ai_data",
                "monitorMode": "jobs",
                "maxPages": 20,
                "enabled": False,
            },
        )
        monitored = client.get(
            "/api/company-candidates",
            params={"decision": "monitored", "pageSize": 10},
        )

    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["fitLevel"] == "high"
    assert review.json() == {"ok": True}
    assert shortlisted.json()["items"][0]["reviewNote"] == "等待核验双休与岗位边界"
    assert promoted.status_code == 200
    assert promoted.json()["name"] == "福建示例数据科技有限公司"
    assert promoted.json()["enabled"] is False
    assert monitored.json()["items"][0]["monitored"] is True
    saved = load_settings(config_path)
    assert len(saved.companies) == 2
    assert saved.companies[-1].evidence_urls == ["https://www.miit.gov.cn/example.pdf"]


def test_candidate_channels_sources_and_manual_notice_keep_official_boundary(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_config(), encoding="utf-8")
    _write_candidate_catalog(config_path)
    client = TestClient(create_app(config_path, web_dist=tmp_path / "missing-dist"))
    candidate_id = "candidate-fujian-data"

    with client:
        grouped = client.patch(
            f"/api/company-candidates/{candidate_id}",
            json={
                "decision": "shortlisted",
                "recruitmentChannelStatus": "group_recruitment",
                "parentCompany": "福建示例集团",
                "groupRecruitmentUrl": "https://group.example.org/careers",
                "attributionKeywords": [
                    "福建示例数据科技有限公司",
                    "示例数据",
                ],
            },
        )
        detail = client.get(f"/api/company-candidates/{candidate_id}")
        third_party_rejected = client.post(
            f"/api/company-candidates/{candidate_id}/sources",
            json={
                "sourceKind": "third_party_lead",
                "verificationStatus": "verified_official",
                "materialType": "webpage",
                "title": "第三方招聘页",
                "sourceUrl": "https://jobs.example.net/company",
                "importAsNotice": True,
            },
        )
        imported = client.post(
            f"/api/company-candidates/{candidate_id}/sources",
            json={
                "sourceKind": "government_notice",
                "verificationStatus": "verified_official",
                "materialType": "pdf",
                "title": "2026 届校园招聘公告",
                "sourceUrl": "https://government.example.org/notice.pdf",
                "content": "本公告面向 2026 届毕业生，报名方式见附件。",
                "publishedAt": "2026-07-26",
                "importAsNotice": True,
            },
        )
        sources = client.get(f"/api/company-candidates/{candidate_id}/sources")
        jobs = client.get("/api/jobs", params={"tab": "notice"})

    assert grouped.json() == {"ok": True}
    assert detail.json()["recruitmentChannelStatus"] == "group_recruitment"
    assert detail.json()["parentCompany"] == "福建示例集团"
    assert detail.json()["groupRecruitmentUrl"] == "https://group.example.org/careers"
    assert detail.json()["attributionKeywords"] == [
        "福建示例数据科技有限公司",
        "示例数据",
    ]
    assert third_party_rejected.status_code == 422
    assert imported.status_code == 200
    assert imported.json()["importedJobId"]
    assert sources.json()[0]["sourceKind"] == "government_notice"
    assert jobs.status_code == 200
    assert any(item["title"] == "2026 届校园招聘公告" for item in jobs.json())


def test_wechat_account_api_enforces_identity_scope_and_private_article_boundary(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_config(), encoding="utf-8")
    _write_candidate_catalog(config_path)
    client = TestClient(create_app(config_path, web_dist=tmp_path / "missing-dist"))
    candidate_id = "candidate-fujian-data"
    manager = client.app.state.wechat_recruitment_manager
    manager.health = lambda: {
        "enabled": True,
        "available": True,
        "message": "测试可用",
    }

    with client:
        invalid_group = client.post(
            f"/api/company-candidates/{candidate_id}/wechat-accounts",
            json={
                "accountName": "示例集团招聘",
                "scope": "group",
                "verificationStatus": "pending",
                "enabled": True,
                "attributionKeywords": [],
            },
        )
        created = client.post(
            f"/api/company-candidates/{candidate_id}/wechat-accounts",
            json={
                "accountName": "示例企业招聘",
                "accountIdentifier": "example_jobs",
                "scope": "company",
                "verificationStatus": "verified",
                "enabled": True,
                "attributionKeywords": ["示例数据科技"],
            },
        )
        duplicate = client.post(
            f"/api/company-candidates/{candidate_id}/wechat-accounts",
            json={
                "accountName": " 示例企业招聘 ",
                "scope": "company",
                "verificationStatus": "pending",
                "enabled": True,
                "attributionKeywords": [],
            },
        )
        listed = client.get(
            f"/api/company-candidates/{candidate_id}/wechat-accounts"
        )
        health = client.get("/api/wechat-recruitment/health")

    assert invalid_group.status_code == 422
    assert created.status_code == 200
    assert duplicate.status_code == 409
    assert listed.status_code == 200
    assert listed.json()[0]["accountIdentifier"] == "example_jobs"
    assert health.json()["message"] == "测试可用"

    now = "2026-07-26T09:00:00+08:00"
    client.app.state.repository.save_wechat_article(
        {
            "article_id": "wechat-article-private-boundary",
            "candidate_id": candidate_id,
            "account_id": created.json()["id"],
            "title": "2026 届校园招聘",
            "account_name": "示例企业招聘",
            "account_identifier": "example_jobs",
            "biz_id": None,
            "source_url": "https://mp.weixin.qq.com/s?__biz=Example&mid=1",
            "summary": "公开摘要",
            "content": "不应由文章列表接口返回的完整正文",
            "published_at": "2026-07-26",
            "classification": "official_recruitment",
            "verification_status": "verified_official",
            "reason": "测试身份边界",
            "content_hash": "test-content-hash",
            "source_id": None,
            "imported_job_id": None,
            "first_seen_at": now,
            "updated_at": now,
        }
    )

    with client:
        articles = client.get(
            f"/api/company-candidates/{candidate_id}/wechat-articles"
        )
        deleted = client.delete(
            f"/api/company-candidates/{candidate_id}/wechat-accounts/"
            f"{created.json()['id']}"
        )
        articles_after_delete = client.get(
            f"/api/company-candidates/{candidate_id}/wechat-articles"
        )

    serialized = json.dumps(articles.json(), ensure_ascii=False)
    assert articles.status_code == 200
    assert "不应由文章列表接口返回的完整正文" not in serialized
    assert "content" not in articles.json()[0]
    assert deleted.json() == {"ok": True}
    assert articles_after_delete.json()[0]["accountId"] is None


def test_application_profile_endpoint_never_exposes_private_path_or_contact(
    tmp_path: Path,
) -> None:
    client, config_path = _client(tmp_path)

    with client:
        missing = client.get("/api/application-profile")
    missing_text = json.dumps(missing.json(), ensure_ascii=False)
    assert missing.status_code == 200
    assert missing.json()["ready"] is False
    assert str(tmp_path) not in missing_text

    _write_application_profile(config_path)
    with client:
        ready = client.get("/api/application-profile")
    ready_text = json.dumps(ready.json(), ensure_ascii=False)
    assert ready.json()["ready"] is True
    assert "接口隐私测试候选人" not in ready_text
    assert "13800000000" not in ready_text
    assert "private-candidate@example.com" not in ready_text
    assert str(tmp_path) not in ready_text


def test_application_action_endpoints_delegate_to_background_manager(tmp_path: Path) -> None:
    client, _config_path = _client(tmp_path)
    manager = client.app.state.application_manager
    calls: list[tuple[str, str]] = []
    manager.create = lambda job_id: (
        calls.append(("create", job_id)) or SimpleNamespace(id="app-created")
    )
    manager.approve = lambda application_id: (
        calls.append(("approve", application_id)) or SimpleNamespace(id=application_id)
    )

    with client:
        created = client.post("/api/jobs/job-test/applications")
        approved = client.post("/api/applications/app-created/approve")

    assert created.status_code == 202
    assert created.json() == {"ok": True, "applicationId": "app-created"}
    assert approved.status_code == 202
    assert calls == [("create", "job-test"), ("approve", "app-created")]


def test_application_list_and_artifact_download_are_private_and_integrity_checked(
    tmp_path: Path,
) -> None:
    client, config_path = _client(tmp_path)
    _write_application_profile(config_path)
    settings = load_settings(config_path)
    storage = JobStorage(settings.app.database_path)
    event = storage.store_jobs([_job()], "2026-07-22T08:00:00+08:00")[0]
    repository = ApplicationRepository(settings.app.database_path)
    service = ApplicationService(repository, settings.application, settings.app.timezone)
    run = service.create(event.entity_key)
    artifact_path = settings.application.output_dir / run.id / "定制简历.docx"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"test-docx-content")
    repository.save_artifact(
        ApplicationArtifact(
            id=f"{run.id}:resume_docx",
            application_id=run.id,
            kind="resume_docx",
            path=str(artifact_path),
            sha256=file_sha256(artifact_path),
            created_at="2026-07-22T08:01:00+08:00",
        )
    )

    with client:
        listing = client.get("/api/applications")
        detail = client.get(f"/api/applications/{run.id}")
        downloaded = client.get(
            f"/api/applications/{run.id}/artifacts/resume_docx"
        )

    serialized = json.dumps(listing.json(), ensure_ascii=False)
    assert listing.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["job"]["title"] == _job().title
    assert detail.json()["artifacts"][0]["downloadUrl"].startswith("/applications/")
    assert "接口隐私测试候选人" not in serialized
    assert "private-candidate@example.com" not in serialized
    assert str(tmp_path) not in serialized
    assert downloaded.status_code == 200
    assert downloaded.content == b"test-docx-content"

    artifact_path.write_bytes(b"tampered")
    with client:
        tampered = client.get(
            f"/api/applications/{run.id}/artifacts/resume_docx"
        )
    assert tampered.status_code == 409


def test_application_manager_marks_interrupted_stage_as_resumable_after_restart(
    tmp_path: Path,
) -> None:
    client, config_path = _client(tmp_path)
    _write_application_profile(config_path)
    settings = load_settings(config_path)
    event = JobStorage(settings.app.database_path).store_jobs(
        [_job()], "2026-07-22T08:00:00+08:00"
    )[0]
    repository = ApplicationRepository(settings.app.database_path)
    service = ApplicationService(repository, settings.application, settings.app.timezone)
    run = service.create(event.entity_key)
    service.transition(run.id, ApplicationStatus.EVALUATING)

    ApplicationManager(client.app.state.repository)
    recovered = repository.get_run(run.id)

    assert recovered is not None
    assert recovered.status == ApplicationStatus.FAILED
    assert recovered.failed_step == ApplicationStatus.EVALUATING
