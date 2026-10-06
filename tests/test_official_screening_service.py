import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from career_radar.api import create_app
from career_radar.config import load_settings
from career_radar.config_editor import mutate_config_blocks
from career_radar.models import JobPosting
from career_radar.official_screening_service import OfficialScreeningManager
from career_radar.storage import JobStorage
from career_radar.web_repository import WebRepository


def setup_repo(root: Path):
    config = root / "config.yaml"
    config.write_text("""
app:
  database_path: data/test.db
crawler:
  render_mode: never
  user_agent: Career Radar official screening integration test
llm:
  provider: mimo
  model: test-model
candidate:
  graduation_year: 2026
  education_level: 本科
  student_status: graduated
  education_mode: full_time
  formal_work_years: 0
  skills: [Python]
  projects: [项目：用 Python 开发 API]
companies:
  - name: 官网企业
    url: https://example.com/careers
""", encoding="utf-8")
    repo = WebRepository(config)
    repo.initialize()
    st = JobStorage(load_settings(config).app.database_path)
    common = dict(company="官网企业", description="Python API 开发。", requirements="本科及以上，接受应届生，无需工作经验。", recruitment_type="校招", source_url="https://example.com/jobs")
    events = st.store_jobs([
        JobPosting(title="2026届 AI 应用工程师", source_job_id="test:1", **common),
        JobPosting(title="2027届 FDE", source_job_id="test:2", **common),
    ], "2026-10-05T12:00:00+08:00")
    return repo, config, events


class FakeGateway:
    calls = 0

    def generate(self, response_model, _system, user):
        self.calls += 1
        request = json.loads(user)
        quote = next(x for x in request["candidate"]["allowed_evidence_quotes"] if x.startswith("项目"))
        return response_model.model_validate({
            "direction": "ai_application", "direction_score": 90, "evidence_score": 80,
            "summary": "API 项目可作为岗位实践证据。",
            "matches": [{"requirement": "API", "job_quote": "Python API 开发", "candidate_quote": quote, "reason": "已做 API 项目"}],
            "gaps": [], "next_steps": ["展示 API 运行和测试结果"],
        })


def wait_completed(manager):
    end = time.monotonic() + 5
    while manager.status()["status"] == "running" and time.monotonic() < end:
        time.sleep(0.01)
    assert manager.status()["status"] == "completed", manager.status()


def test_background_screening_skips_ineligible_caches_and_invalidates_profile_changes(tmp_path):
    repo, config, events = setup_repo(tmp_path)
    gateway = FakeGateway()
    manager = OfficialScreeningManager(repo, gateway_factory=lambda _llm: gateway)
    try:
        manager.start()
        wait_completed(manager)
        assert manager.status()["evaluated"] == 1
        assert manager.status()["ineligible"] == 1
        assert gateway.calls == 1
        assessed = repo.get_job(events[0].entity_key)
        assert assessed["aiAssessment"]["status"] == "current"
        assert assessed["priority"]["tier"] == "high"
        assert assessed["eligibility"]["verdict"] == "eligible"
        assert repo.get_job(events[1].entity_key)["priority"]["tier"] == "defer"
        manager.start()
        wait_completed(manager)
        assert manager.status()["cached"] == 1
        assert gateway.calls == 1
        mutate_config_blocks(config, lambda raw: ({"candidate": {**raw["candidate"], "skills": ["Python", "Go"]}}, None))
        stale = repo.get_job(events[0].entity_key)
        assert stale["aiAssessment"]["status"] == "stale"
        assert stale["priority"]["tier"] == "pending"
        assert stale["jdText"] == assessed["jdText"]
        manager.start()
        wait_completed(manager)
        assert gateway.calls == 2
    finally:
        manager.shutdown()


def test_real_api_contract_async_results_and_cross_origin_guard(tmp_path):
    _repo, config, events = setup_repo(tmp_path)
    app = create_app(config, web_dist=tmp_path / "no-dist")
    gateway = FakeGateway()
    app.state.official_screening.gateway_factory = lambda _llm: gateway
    with TestClient(app) as client:
        assert client.get("/api/jobs/screening").json()["status"] == "idle"
        assert client.post("/api/jobs/screening", json={"ids": [events[0].entity_key]}, headers={"Origin": "https://foreign.example"}).status_code == 403
        response = client.post("/api/jobs/screening", json={"ids": [events[0].entity_key]})
        assert response.status_code == 202
        wait_completed(app.state.official_screening)
        detail = client.get(f"/api/jobs/{events[0].entity_key}").json()
        assert detail["aiAssessment"]["status"] == "current"
        assert detail["aiAssessment"]["result"]["matches"][0]["candidate_quote"] == "项目：用 Python 开发 API"
        assert client.get("/api/jobs").json()[0]["id"] == events[0].entity_key
        profile = client.get("/api/profile").json()
        profile.update(studentStatus="enrolled", formalWorkYears=0.5)
        assert client.put("/api/profile", json=profile).status_code == 200
        assert load_settings(config).candidate.formal_work_years == 0.5
        assert client.get(f"/api/jobs/{events[0].entity_key}").json()["aiAssessment"]["status"] == "stale"
