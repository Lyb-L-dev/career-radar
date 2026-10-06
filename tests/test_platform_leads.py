from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from career_radar import api_platform_leads
from career_radar.api import create_app
from career_radar.boss_ai import BossAIResult
from career_radar.models import CandidateProfile
from career_radar.platform_leads import (
    BossExportError,
    BossLeadRepository,
    BossPreferences,
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

    surrogate = _job(job_id="a1b2c3d4e5f6a7b8", job_link=summary[0].source_url)
    assert parse_boss_export(_list_file([surrogate]))[0].external_id == "abc123"

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


def test_graduate_excludes_in_school_internship_but_keeps_formal_new_grad(tmp_path: Path) -> None:
    repo = BossLeadRepository(tmp_path / "leads.db")
    repo.initialize()
    internship = _job(
        "student-only",
        title="FDE 实习生",
        tags="实习 | 本科",
        jd=JD + "岗位要求：计算机相关专业在读大四学生，可连续实习三个月。",
    )
    formal = _job("formal", title="AI 应用工程师", tags="应届生 | 本科")
    repo.import_leads(parse_boss_export(_list_file([internship, formal])))
    repo.set_preferences(BossPreferences(current_student=False, accept_internship=False))
    by_id = {item["external_id"]: item for item in repo.list_leads(_profile())}
    assert by_id["student-only"]["category"] == "excluded"
    assert any("已毕业" in reason for reason in by_id["student-only"]["blockers"])
    assert by_id["formal"]["category"] != "excluded"


def test_graduate_keeps_student_preference_when_graduates_are_allowed() -> None:
    lead = parse_boss_export(
        _list_file(
            [
                _job(
                    "optional-student",
                    title="AI 应用工程师",
                    tags="本科 | 应届生",
                    jd=JD + "岗位要求：在校生优先，已毕业的应届生也可报名。",
                )
            ]
        )
    )[0]
    result = triage_boss_lead(
        lead,
        _profile(),
        "2026-09-28T00:00:00+00:00",
        BossPreferences(current_student=False, accept_internship=False),
    )
    assert result["category"] != "excluded"


def test_explicit_graduation_year_blocks_only_other_cohorts() -> None:
    profile = CandidateProfile(graduation_year=2026, skills=["Python"])
    other_year = parse_boss_export(
        _list_file(
            [
                _job(
                    "grad-2027",
                    title="AI 应用工程师",
                    jd=JD + "毕业时间：2027年 招聘截止日期：2026.10.31",
                )
            ]
        )
    )[0]
    mixed_years = parse_boss_export(
        _list_file(
            [
                _job(
                    "grad-mixed",
                    title="2026、2027届 AI 应用工程师",
                    jd=JD,
                )
            ]
        )
    )[0]
    seen = "2026-09-28T00:00:00+00:00"
    assert triage_boss_lead(other_year, profile, seen)["category"] == "excluded"
    assert triage_boss_lead(mixed_years, profile, seen)["category"] != "excluded"


def test_anonymous_company_is_reviewed_before_ai_cost(tmp_path: Path) -> None:
    repo = BossLeadRepository(tmp_path / "leads.db")
    repo.initialize()
    anonymous = parse_boss_export(
        _list_file(
            [
                _job(
                    "anonymous",
                    boss_name="某知名企业",
                    jd=JD,
                )
            ]
        )
    )[0]
    repo.import_leads([anonymous])
    result = repo.list_leads(_profile())[0]
    assert result["category"] == "review"
    assert result["companyIdentified"] is False
    assert result["aiScreenable"] is False


def test_platform_api_keeps_leads_out_of_official_jobs(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
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
  provider: mimo
  model: mimo-test
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
        assert client.get("/api/platform-leads/crawl").json()["state"] == "idle"
        monkeypatch.setattr(
            client.app.state.boss_capture,
            "plan",
            lambda _keyword="": {"searches": [{"family": "数据开发", "keyword": "数据开发"}], "resumeProjectCount": 3},
        )
        assert client.get("/api/platform-leads/crawl/plan").json()["searches"][0]["family"] == "数据开发"
        assert client.post("/api/platform-leads/crawl", json={"keyword": "AI应用开发"}).status_code == 422
        assert client.post("/api/platform-leads/crawl", json={"keyword": "  "}).status_code == 422
        monkeypatch.setattr(client.app.state.boss_capture, "open_browser", lambda: {"ready": True})
        assert client.post("/api/platform-leads/crawl/browser").json() == {"ready": True}
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
            client.post(f"/api/platform-leads/{lead['id']}/ai-screen", json={}).status_code == 422
        )
        gateway_calls: list[str] = []

        class FakeGateway:
            def generate(self, response_model, system_prompt: str, user_prompt: str):
                gateway_calls.append(user_prompt)
                assert response_model is BossAIResult
                return BossAIResult(
                    eligibility="eligible",
                    fit="strong",
                    action="prioritize",
                    confidence="medium",
                    summary="学历与方向有明确匹配证据。",
                    eligibility_checks=[
                        {
                            "requirement": "本科",
                            "verdict": "met",
                            "job_quote": "本科",
                            "candidate_quote": "普通本科",
                        }
                    ],
                    matched_evidence=["Python"],
                    gaps=[],
                    next_step="打开原始 BOSS 页面核对投递入口。",
                )

        monkeypatch.setattr(
            api_platform_leads, "CompatibleApplicationGateway", lambda _config: FakeGateway()
        )
        ai_url = f"/api/platform-leads/{lead['id']}/ai-screen"
        assert client.post(ai_url, json={"confirmed": True}).json()["cached"] is False
        assert client.post(ai_url, json={"confirmed": True}).json()["cached"] is True
        assert len(gateway_calls) == 1
        assert client.get("/api/platform-leads").json()[0]["aiResult"]["eligibility"] == "eligible"
        assert client.get("/api/platform-leads/preferences").json()["currentStudent"] is None
        assert (
            client.put(
                "/api/platform-leads/preferences",
                json={"currentStudent": False, "acceptInternship": False},
            ).status_code
            == 200
        )
        after_preference_change = client.get("/api/platform-leads").json()[0]
        assert after_preference_change["aiNeedsRefresh"]
        assert after_preference_change["aiResult"] is None
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
