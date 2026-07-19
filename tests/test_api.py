"""本地 FastAPI 接口测试：确保 Web 展示和写入都来自真实配置与 SQLite。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from career_radar.api import create_app
from career_radar.config import load_settings
from career_radar.models import JobPosting, MatchLevel, ProfileFitLevel
from career_radar.storage import JobStorage


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
