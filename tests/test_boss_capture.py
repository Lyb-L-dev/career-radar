"""Offline contract tests for resume-aware capture before permanent import."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from career_radar import boss_capture
from career_radar.boss_ai import BossAIResult
from career_radar.boss_capture import (
    BossCaptureError,
    BossCaptureManager,
    CaptureRequest,
    plan_resume_searches,
    run_profiled_capture,
    select_detail_candidates,
)
from career_radar.models import CandidateProfile, Settings
from career_radar.platform_leads import BossLeadRepository, BossPreferences


def _row(job_id: str, title: str = "AI Agent 应用开发工程师", **changes: str) -> dict[str, str]:
    return {
        "job_id": f"surrogate-{job_id}",
        "title": title,
        "boss_name": "示例小公司",
        "location": "杭州",
        "tags": "经验不限 | 本科",
        "skills": "Python | AI Agent",
        "company_scale": "20-99人",
        "job_link": f"https://www.zhipin.com/job_detail/{job_id}.html",
        **changes,
    }


def _candidate() -> CandidateProfile:
    return CandidateProfile(
        graduation_year=2026,
        education_level="本科",
        school_background="普通本科，非 985/211",
        skills=["Python", "Flask"],
        projects=["Python 数据平台项目"],
        internships=[],
        has_work_experience=False,
    )


def test_list_gate_skips_hard_mismatch_but_keeps_realistic_stretch() -> None:
    jobs = [
        _row("ok"),
        _row("master", tags="应届生 | 硕士"),
        _row("intern", title="AI 应用开发实习生"),
        _row("future", title="2027届 AI 应用开发工程师"),
        _row("futurelabel", job_labels="2027届校招"),
        _row("senior", tags="3-5年 | 本科"),
        _row("two", tags="2-3年 | 本科"),
        _row("sales", title="AI 销售"),
        _row("sales_en", title="AI Sales Engineer"),
        _row("secret", boss_name="某知名企业"),
        _row("stretch", title="FDE 工程师", tags="1-3年 | 本科"),
        _row("large", title="AI 工程师", company_scale="10000人以上"),
    ]
    selected, counts = select_detail_candidates(
        jobs, _candidate(), BossPreferences(current_student=False, accept_internship=False), 6
    )
    assert {row["job_link"].split("/")[-1] for row in selected} == {
        "ok.html", "stretch.html", "large.html"
    }
    assert counts["hard_rejected"] == 6
    assert counts["off_target"] == 2
    assert counts["unclear_company"] == 1


def test_resume_plan_covers_supported_roles_and_balances_detail_budget() -> None:
    profile = _candidate().model_copy(update={"skills": [
        "Python", "SQL", "FastAPI", "RAG", "LangGraph", "Kafka", "Spark Streaming",
        "Scikit-learn", "Pytest", "Playwright", "React",
    ]})
    planned = plan_resume_searches(profile)
    assert {item.family for item in planned} == {
        "AI 应用开发", "Python 后端", "数据开发", "数据分析", "测试开发",
        "全栈开发", "机器学习应用", "FDE 与场景交付",
    }
    assert plan_resume_searches(profile, "数字管理研发")[0].keyword == "数字管理研发"
    rows = [
        _row("ai-one", _search_family="AI 应用开发"),
        _row("ai-two", _search_family="AI 应用开发"),
        _row("data", title="数据开发工程师", _search_family="数据开发"),
    ]
    selected, _ = select_detail_candidates(
        rows, profile, BossPreferences(current_student=False, accept_internship=False), 2
    )
    assert {row["_search_family"] for row in selected} == {"AI 应用开发", "数据开发"}


def test_open_browser_uses_existing_upstream_setup_without_copying_login_state(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    repo = BossLeadRepository(tmp_path / "jobs.db")
    monkeypatch.setattr(boss_capture, "_scraper_paths", lambda _path: (tmp_path, tmp_path / "python", tmp_path / "scraper.py"))
    ready = iter((False, True))
    monkeypatch.setattr(boss_capture, "_cdp_ready", lambda: next(ready))
    commands: list[list[str]] = []
    monkeypatch.setattr(boss_capture, "_run_scraper", lambda command, _root, _timeout: commands.append(command))
    manager = BossCaptureManager(repo, lambda: None, tmp_path)  # settings are not accessed by browser setup
    assert manager.open_browser() == {"ready": True}
    assert commands == [[str(tmp_path / "python"), str(tmp_path / "scraper.py"), "--setup-edge", "--no-wait-login"]]


def test_capture_fetches_only_shortlist_and_persists_only_mimo_accepted(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    settings = Settings.model_validate({
        "crawler": {"render_mode": "never", "request_delay_min_seconds": 0, "request_delay_max_seconds": 0, "user_agent": "Test browser"},
        "llm": {"provider": "mimo", "model": "mimo-test"},
        "companies": [{"name": "示例企业", "url": "https://example.com/careers"}],
    })
    repo = BossLeadRepository(tmp_path / "real.db")
    repo.initialize()
    prefs = BossPreferences(current_student=False, accept_internship=False)
    repo.set_preferences(prefs)
    monkeypatch.setattr(boss_capture, "candidate_from_verified_resume", lambda _settings: _candidate())
    monkeypatch.setattr(
        boss_capture, "_scraper_paths", lambda _config_dir: (tmp_path, tmp_path / "python", tmp_path / "scraper.py")
    )
    requested_details: list[str] = []

    def fake_runner(command: list[str], _root: Path, _timeout: int) -> None:
        if "--no-detail" in command:
            output = Path(command[command.index("--output") + 1])
            output.write_text(json.dumps({"jobs": [
                _row("good"), _row("bad", tags="3-5年 | 本科"), _row("sales", title="AI 销售")
            ]}, ensure_ascii=False), encoding="utf-8")
            return
        shortlisted = json.loads(Path(command[command.index("--input") + 1]).read_text(encoding="utf-8"))["jobs"]
        requested_details.extend(row["job_link"] for row in shortlisted)
        output = Path(command[command.index("--detail-output") + 1])
        output.write_text(json.dumps([{
            **row,
            "company": row["boss_name"],
            "tags_list": row["tags"],
            "jd": "本科；负责 AI Agent 应用开发与 Python API 服务，接受 2026 届毕业生。" * 5,
        } for row in shortlisted], ensure_ascii=False), encoding="utf-8")

    class FakeGateway:
        def generate(self, response_model, _system_prompt: str, _user_prompt: str) -> BossAIResult:
            assert response_model is BossAIResult
            return BossAIResult(
                eligibility="eligible", fit="reasonable", action="consider", confidence="medium",
                summary="项目技术相关，报名条件可核对。",
                eligibility_checks=[{"requirement": "本科", "verdict": "met", "job_quote": "本科", "candidate_quote": "本科"}],
                matched_evidence=["Python"], gaps=[], next_step="查看原始 JD 后投递。",
            )

    counts = run_profiled_capture(
        CaptureRequest(max_details=3), settings, repo, tmp_path,
        command_runner=fake_runner, gateway_factory=FakeGateway,
    )
    assert counts["searches"] == len(plan_resume_searches(_candidate()))
    assert counts["listed"] == 3 * counts["searches"]
    assert counts["shortlisted"] == counts["details"] == counts["accepted"] == 1
    assert requested_details == ["https://www.zhipin.com/job_detail/good.html"]
    stored = repo.list_leads(_candidate(), boss_capture.model_identity(settings))
    assert len(stored) == 1
    assert stored[0]["source_url"] == requested_details[0]
    assert stored[0]["aiResult"]["fit"] == "reasonable"
    history = (tmp_path / "private" / "boss_capture_history.json").read_text(encoding="utf-8")
    assert "good.html" not in history and "AI Agent" not in history
    (tmp_path / "private" / "boss_capture_history.json").unlink()
    requested_details.clear()
    repeat = run_profiled_capture(
        CaptureRequest(max_details=3), settings, repo, tmp_path,
        command_runner=fake_runner, gateway_factory=FakeGateway,
    )
    assert repeat["recently_reviewed"] == 1
    assert repeat["shortlisted"] == 0
    assert requested_details == []

    class FailedGateway:
        def generate(self, _response_model, _system_prompt: str, _user_prompt: str) -> BossAIResult:
            raise RuntimeError("model unavailable")

    fresh = BossLeadRepository(tmp_path / "no-unverified-import.db")
    fresh.initialize()
    fresh.set_preferences(prefs)
    with pytest.raises(BossCaptureError, match="MiMo 未能完成"):
        run_profiled_capture(
            CaptureRequest(max_details=3), settings, fresh, tmp_path / "retry",
            command_runner=fake_runner, gateway_factory=FailedGateway,
        )
    assert fresh.list_leads(_candidate()) == []

    class WeakGateway(FakeGateway):
        def generate(self, response_model, system_prompt: str, user_prompt: str) -> BossAIResult:
            return super().generate(response_model, system_prompt, user_prompt).model_copy(
                update={"fit": "weak", "action": "defer"}
            )

    rejected = BossLeadRepository(tmp_path / "rejected.db")
    rejected.initialize()
    rejected.set_preferences(prefs)
    rejected_dir = tmp_path / "rejected-run"
    first_rejection = run_profiled_capture(
        CaptureRequest(max_details=3), settings, rejected, rejected_dir,
        command_runner=fake_runner, gateway_factory=WeakGateway,
    )
    assert first_rejection["ai_rejected"] == 1
    assert rejected.list_leads(_candidate()) == []
    repeated_rejection = run_profiled_capture(
        CaptureRequest(max_details=3), settings, rejected, rejected_dir,
        command_runner=fake_runner, gateway_factory=FakeGateway,
    )
    assert repeated_rejection["recently_reviewed"] == 1
    assert repeated_rejection["shortlisted"] == 0
    updated_profile = _candidate().model_copy(update={"projects": ["新增 Python AI 项目证据"]})
    monkeypatch.setattr(boss_capture, "candidate_from_verified_resume", lambda _settings: updated_profile)
    after_resume_change = run_profiled_capture(
        CaptureRequest(max_details=3), settings, rejected, rejected_dir,
        command_runner=fake_runner, gateway_factory=FakeGateway,
    )
    assert after_resume_change["recently_reviewed"] == 0
    assert after_resume_change["accepted"] == 1


def test_review_history_expires_and_ignores_malformed_entries(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    now = datetime.now(UTC)
    recent = "a" * 64
    expired = "b" * 64
    fingerprint = "f" * 64
    def record(timestamp: str) -> dict[str, str]:
        return {"reviewed_at": timestamp, "listing_hash": fingerprint}
    path.write_text(json.dumps({
        "context": "current-resume",
        "reviewed": {
            recent: record(now.isoformat()),
            expired: record((now - timedelta(days=8)).isoformat()),
            "c" * 64: record("bad-date"),
            "d" * 64: record(now.replace(tzinfo=None).isoformat()),
            "e" * 64: record((now + timedelta(days=1)).isoformat()),
        },
    }), encoding="utf-8")
    assert boss_capture._recent_history(path, "current-resume") == {recent: record(now.isoformat())}
    assert boss_capture._recent_history(path, "changed-resume") == {}


def test_changed_listing_is_rechecked_during_review_cache_window() -> None:
    original = _row("changed")
    lead = boss_capture._lead_from_raw(original)
    assert lead is not None
    reviewed = {boss_capture._link_hash(lead.source_url): {
        "reviewed_at": datetime.now(UTC).isoformat(),
        "listing_hash": boss_capture._listing_hash(lead),
    }}
    preferences = BossPreferences(current_student=False, accept_internship=False)
    selected, counts = select_detail_candidates([original], _candidate(), preferences, 1, reviewed)
    assert selected == [] and counts["recently_reviewed"] == 1
    changed = {**original, "tags": "经验不限 | 硕士"}
    selected, counts = select_detail_candidates([changed], _candidate(), preferences, 1, reviewed)
    assert selected == []
    assert counts["recently_reviewed"] == 0 and counts["hard_rejected"] == 1
