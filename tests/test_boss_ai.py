from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from career_radar.application.llm import CompatibleApplicationGateway
from career_radar.boss_ai import BossAIResult, BossAIScreener
from career_radar.models import CandidateProfile, LLMConfig
from career_radar.platform_leads import BossLead, BossLeadRepository, parse_boss_export


def _lead(jd: str) -> BossLead:
    return parse_boss_export(
        json.dumps(
            {
                "jobs": [
                    {
                        "job_id": "ai-test-1",
                        "title": "AI FDE 工程师",
                        "boss_name": "示例科技",
                        "tags": "应届生 | 本科",
                        "jd": jd,
                    }
                ]
            },
            ensure_ascii=False,
        )
    )[0]


JD = "负责 Python、LLM Agent 应用开发和客户场景部署。 " * 6


def _result() -> BossAIResult:
    return BossAIResult(
        eligibility="eligible",
        fit="strong",
        action="prioritize",
        confidence="medium",
        summary="符合本科资格，Python 项目与岗位方向接近；仍需阅读客户现场工作要求。",
        eligibility_checks=[
            {
                "requirement": "本科",
                "verdict": "met",
                "job_quote": "本科",
                "candidate_quote": "普通本科",
            }
        ],
        matched_evidence=["Python"],
        gaps=["客户现场交付经验尚未证明"],
        next_step="核对原始岗位页后准备项目经历。",
    )


class FakeGateway:
    def __init__(self, response: BossAIResult):
        self.response = response
        self.calls = 0
        self.last_prompt = ""

    def generate(self, response_model, system_prompt: str, user_prompt: str) -> BossAIResult:
        assert response_model is BossAIResult
        assert "忽略" in system_prompt
        self.calls += 1
        self.last_prompt = user_prompt
        return self.response


def test_screening_is_cached_and_invalidated_by_job_profile_and_model(tmp_path: Path) -> None:
    repo = BossLeadRepository(tmp_path / "leads.db")
    repo.initialize()
    lead = _lead(JD)
    repo.import_leads([lead])
    profile = CandidateProfile(skills=["Python"], education_level="普通本科")
    gateway = FakeGateway(_result())
    created = []

    def factory():
        created.append(True)
        return gateway

    screener = BossAIScreener(repo, factory)
    first = screener.screen(lead.id, profile, "mimo-test")
    assert first["cached"] is False
    assert gateway.calls == 1
    assert "普通本科" in gateway.last_prompt
    assert "DEEPSEEK_API_KEY" not in gateway.last_prompt
    assert repo.list_leads(profile, "mimo-test")[0]["aiResult"]["eligibility"] == "eligible"

    second = screener.screen(lead.id, profile, "mimo-test")
    assert second["cached"] is True
    assert gateway.calls == 1 and len(created) == 1

    changed_profile = profile.model_copy(update={"skills": ["Python", "SQL"]})
    assert repo.list_leads(changed_profile, "mimo-test")[0]["aiNeedsRefresh"]
    assert repo.list_leads(profile, "new-model")[0]["aiNeedsRefresh"]

    newer = _lead("负责 Python、LLM Agent 应用开发和系统性能测试。 " * 5)
    repo.import_leads([newer])
    assert repo.list_leads(profile, "mimo-test")[0]["aiResult"] is None
    assert screener.screen(lead.id, profile, "mimo-test")["cached"] is False
    assert gateway.calls == 2


def test_unverifiable_ineligibility_is_downgraded_to_unknown(tmp_path: Path) -> None:
    repo = BossLeadRepository(tmp_path / "leads.db")
    repo.initialize()
    lead = _lead(JD)
    repo.import_leads([lead])
    profile = CandidateProfile(skills=["Python"])
    wrong = BossAIResult.model_validate(
        {
            **_result().model_dump(),
            "eligibility": "ineligible",
            "eligibility_checks": [
                {
                    "requirement": "985",
                    "verdict": "unmet",
                    "job_quote": "仅限985",
                    "candidate_quote": "普通本科",
                }
            ],
        }
    )
    gateway = FakeGateway(wrong)
    screened = BossAIScreener(repo, lambda: gateway).screen(lead.id, profile, "mimo-test")
    assert screened["result"]["eligibility"] == "unknown"
    assert screened["result"]["action"] == "consider"
    assert screened["result"]["eligibility_checks"][0]["verdict"] == "unknown"
    assert screened["result"]["eligibility_checks"][0]["job_quote"] == ""
    assert repo.list_leads(profile, "mimo-test")[0]["aiResult"]["eligibility"] == "unknown"


def test_preferred_school_is_never_an_ai_hard_blocker(tmp_path: Path) -> None:
    repo = BossLeadRepository(tmp_path / "leads.db")
    repo.initialize()
    lead = _lead(JD + "985院校优先，普通本科也可报名。")
    repo.import_leads([lead])
    profile = CandidateProfile(skills=["Python"])
    result = BossAIResult.model_validate(
        {
            **_result().model_dump(),
            "eligibility": "ineligible",
            "action": "defer",
            "eligibility_checks": [
                {
                    "requirement": "985院校优先",
                    "verdict": "unmet",
                    "job_quote": "985院校优先",
                    "candidate_quote": profile.school_background,
                }
            ],
        }
    )
    screened = BossAIScreener(repo, lambda: FakeGateway(result)).screen(
        lead.id, profile, "mimo-test"
    )
    assert screened["result"]["eligibility"] == "unknown"
    assert screened["result"]["eligibility_checks"][0]["verdict"] == "unknown"


def test_missing_jd_never_calls_paid_gateway(tmp_path: Path) -> None:
    repo = BossLeadRepository(tmp_path / "leads.db")
    repo.initialize()
    lead = _lead("")
    repo.import_leads([lead])
    profile = CandidateProfile(skills=["Python"])
    with pytest.raises(ValueError, match="完整 JD"):
        BossAIScreener(repo, lambda: (_ for _ in ()).throw(AssertionError("called"))).screen(
            lead.id, profile, "mimo-test"
        )


def test_oversized_jd_is_not_sent_as_partial_eligibility_check(tmp_path: Path) -> None:
    repo = BossLeadRepository(tmp_path / "leads.db")
    repo.initialize()
    lead = _lead(JD * 45)
    repo.import_leads([lead])
    profile = CandidateProfile(skills=["Python"])
    assert not repo.list_leads(profile, "mimo-test")[0]["aiScreenable"]
    with pytest.raises(ValueError, match="8000"):
        BossAIScreener(repo, lambda: (_ for _ in ()).throw(AssertionError("called"))).screen(
            lead.id, profile, "mimo-test"
        )


def test_updated_jd_during_model_call_does_not_save_stale_result(tmp_path: Path) -> None:
    repo = BossLeadRepository(tmp_path / "leads.db")
    repo.initialize()
    lead = _lead(JD)
    repo.import_leads([lead])
    profile = CandidateProfile(skills=["Python"])

    class UpdatingGateway(FakeGateway):
        def generate(self, response_model, system_prompt: str, user_prompt: str) -> BossAIResult:
            result = super().generate(response_model, system_prompt, user_prompt)
            repo.import_leads([_lead("负责 Python、LLM Agent 应用开发和新项目交付。 " * 5)])
            return result

    with pytest.raises(ValueError, match="发生变化"):
        BossAIScreener(repo, lambda: UpdatingGateway(_result())).screen(
            lead.id, profile, "mimo-test"
        )
    assert repo.list_leads(profile, "mimo-test")[0]["aiResult"] is None


def test_mimo_gateway_uses_its_completion_token_parameter() -> None:
    calls: list[dict[str, object]] = []

    class FakeCompletions:
        def create(self, **request):
            calls.append(request)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=_result().model_dump_json()))
                ]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    gateway = CompatibleApplicationGateway(
        LLMConfig(provider="mimo", model="mimo-v2.6-pro", max_retries=1),
        client=client,
    )
    result = gateway.generate(BossAIResult, "测试系统提示", "测试岗位与画像")
    assert result.eligibility == "eligible"
    assert calls[0]["model"] == "mimo-v2.6-pro"
    assert calls[0]["max_completion_tokens"] == gateway.config.max_output_tokens
    assert "max_tokens" not in calls[0]
    assert calls[0]["response_format"] == {"type": "json_object"}


def test_mimo_gateway_uses_only_mimo_key_and_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    import openai

    captured: dict[str, object] = {}

    def fake_openai(**options):
        captured.update(options)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace()))

    monkeypatch.setenv("XIAOMIMIMO_API_KEY", "mimo-unit-test-key")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(openai, "OpenAI", fake_openai)
    CompatibleApplicationGateway(LLMConfig(provider="mimo", model="mimo-v2.6-pro"))
    assert captured["api_key"] == "mimo-unit-test-key"
    assert captured["base_url"] == "https://api.xiaomimimo.com/v1"
