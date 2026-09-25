from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from career_radar.api import create_app
from career_radar.models import CandidateProfile
from career_radar.platform_leads import (
    BossExportError,
    BossLeadRepository,
    parse_boss_export,
    triage_boss_lead,
)

JD = "负责 AI Agent 应用开发、Python API 服务与客户场景部署。 " * 5


def _list_file(jobs: list[dict[str, str]]) -> str:
    return json.dumps({"keyword": "FDE", "city": "上海", "jobs": jobs}, ensure_ascii=False)


def _job(job_id: str = "abc123", **changes: str) -> dict[str, str]:
    return {
        "job_id": job_id,
        "title": "AI FDE 工程师",
        "boss_name": "示例科技",
        "location": "上海",
        "tags": "应届生 | 本科",
        "job_link": f"https://www.zhipin.com/job_detail/{job_id}.html",
        "jd": JD,
        **changes,
    }


def _profile() -> CandidateProfile:
    return CandidateProfile(skills=["Python"], preferred_locations=["福州"])


def test_boss_export_accepts_list_and_detail_and_rejects_bad_identity() -> None:
    summary = parse_boss_export(_list_file([_job(jd=""), _job(jd=JD)]))
    assert len(summary) == 1
    assert summary[0].jd_complete
    assert summary[0].source_url == "https://www.zhipin.com/job_detail/abc123.html"

    details = parse_boss_export(json.dumps([_job(job_id="", job_link=summary[0].source_url)]))
    assert details[0].external_id == "abc123"

    try:
        parse_boss_export(
            _list_file([_job(job_id="", job_link="https://evil.example/job_detail/x.html")])
        )
    except BossExportError:
        pass
    else:
        raise AssertionError("Untrusted job URL must not become a BOSS lead")


def test_import_is_idempotent_and_keeps_jd_and_manual_state(tmp_path: Path) -> None:
    repo = BossLeadRepository(tmp_path / "leads.db")
    repo.initialize()
    complete = parse_boss_export(_list_file([_job()]))
    assert repo.import_leads(complete) == {"total": 1, "new": 1, "updated": 0, "unchanged": 0}
    lead_id = complete[0].id
    assert repo.set_state(lead_id, "favorite", True)
    assert repo.set_state(lead_id, "applied", True)
    assert repo.import_leads(parse_boss_export(_list_file([_job(jd="")])))["unchanged"] == 1
    changed = repo.import_leads(
        parse_boss_export(_list_file([_job(title="AI 应用 FDE 工程师", jd="")]))
    )
    assert changed["updated"] == 1
    result = repo.list_leads(_profile())[0]
    assert result["description"] == JD.strip()
    assert result["title"] == "AI 应用 FDE 工程师"
    assert result["isFavorite"] and result["isApplied"]
    assert result["sourceLabel"] == "BOSS直聘 · 平台线索"
    assert result["category"] == "priority"


def test_list_then_detail_import_upgrades_review_without_duplicate(tmp_path: Path) -> None:
    repo = BossLeadRepository(tmp_path / "leads.db")
    repo.initialize()
    summary = parse_boss_export(_list_file([_job(jd="")]))
    assert repo.import_leads(summary)["new"] == 1
    assert repo.list_leads(_profile())[0]["category"] == "review"

    detail = parse_boss_export(json.dumps([_job()], ensure_ascii=False))
    assert repo.import_leads(detail)["updated"] == 1
    after = repo.list_leads(_profile())
    assert len(after) == 1
    assert after[0]["category"] == "priority"
    assert after[0]["jdComplete"]


def test_explicit_qualification_exclusion_and_missing_jd_review() -> None:
    profile = _profile()
    seen = "2026-09-24T00:00:00+00:00"
    matching, masters, missing = parse_boss_export(
        _list_file(
            [
                _job("a"),
                _job("b", tags="硕士 | 应届生"),
                _job("c", jd="登录查看完整内容"),
            ]
        )
    )
    assert triage_boss_lead(matching, profile, seen)["category"] == "priority"
    assert triage_boss_lead(masters, profile, seen)["category"] == "excluded"
    assert triage_boss_lead(missing, profile, seen)["category"] == "review"
    # The configured preferred city is deliberately ignored for this opportunity pool.
    assert matching.location == "上海" and profile.preferred_locations == ["福州"]


def test_school_preference_is_not_mistaken_for_hard_requirement() -> None:
    profile = _profile()
    seen = "2026-09-24T00:00:00+00:00"
    not_required = parse_boss_export(_list_file([_job(jd=JD + "我们不要求985院校背景。")]))[0]
    preferred = parse_boss_export(_list_file([_job(jd=JD + "985院校优先，但不作硬性限制。")]))[0]
    required = parse_boss_export(_list_file([_job(jd=JD + "要求985院校背景。")]))[0]
    assert not triage_boss_lead(not_required, profile, seen)["blockers"]
    assert not triage_boss_lead(preferred, profile, seen)["blockers"]
    assert triage_boss_lead(required, profile, seen)["category"] == "excluded"


def test_platform_api_keeps_leads_out_of_official_jobs(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        """app:
  database_path: data/test.db
  output_dir: output
  log_dir: logs
crawler:
  render_mode: never
  request_delay_min_seconds: 0
  request_delay_max_seconds: 0
  user_agent: Test browser
llm:
  provider: deepseek
  model: test-model
smtp:
  enabled: false
candidate:
  skills: [Python]
  target_roles: [AI FDE]
  preferred_locations: [福州]
companies:
  - name: 示例企业
    url: https://example.com/careers
""",
        encoding="utf-8",
    )
    with TestClient(create_app(config, web_dist=tmp_path / "missing")) as client:
        content = _list_file([_job()])
        assert client.post("/api/platform-leads/preview", json={"content": content}).json() == {
            "total": 1,
            "completeJd": 1,
            "needsReview": 0,
        }
        assert (
            client.post("/api/platform-leads/import", json={"content": content}).json()["new"] == 1
        )
        lead = client.get("/api/platform-leads").json()[0]
        assert lead["category"] == "priority"
        assert client.get("/api/jobs").json() == []
        assert (
            client.post(
                f"/api/platform-leads/{lead['id']}/state",
                json={"field": "favorite", "value": True},
            ).status_code
            == 200
        )
        assert client.get("/api/platform-leads").json()[0]["isFavorite"]
        assert (
            client.post(
                "/api/platform-leads/import", json={"content": '{"jobs":[{"job_id":"oops"}]}'}
            ).status_code
            == 422
        )
        assert len(client.get("/api/platform-leads").json()) == 1
