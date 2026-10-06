"""Offline growth-loop tests through the service and public HTTP contracts."""

import json
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from career_radar.api import create_app
from career_radar.growth.evidence import ZONE
from career_radar.growth.manager import GrowthManager
from career_radar.growth.models import Grade, JDAnalysis, ProjectReview, QuestionOutput, Teaching
from career_radar.growth.repository import GrowthRepository
from career_radar.growth.service import (
    GrowthService,
    code_excerpt,
    http_message_example,
    original_code_excerpt,
)
from career_radar.models import JobPosting, LLMConfig
from career_radar.platform_leads import BossLead
from career_radar.storage import JobStorage
from career_radar.task_coordinator import TaskCoordinator


class FakeGateway:
    def __init__(self):
        self.question_count = 0
        self.bad_quote = False
        self.fail = False
        self.calls = []

    def generate(self, response_model, system_prompt, user_prompt):
        data = json.loads(user_prompt)
        self.calls.append(data["task"])
        if self.fail:
            raise ValueError("测试模型暂时不可用")
        if response_model is JDAnalysis:
            text = data["jd"]
            requirements = []
            for name in ("HTTP", "Python", "RAG"):
                if name in text:
                    requirements.append({"skill": name, "quote": "虚构要求" if self.bad_quote else name, "kind": "skill", "minimumLevel": 2})
            return response_model(requirements=requirements)
        if response_model is Teaching:
            return response_model(explanation="请求包含方法、路径和头部；响应包含状态码和正文。请合上讲解复述。")
        if response_model is QuestionOutput:
            self.question_count += 1
            modes = data["allowedModes"]
            mode = modes[(self.question_count - 2) % len(modes)]
            code = data["skill"].get("questionExamples", ["response = client.get('/api/jobs')\nif response.status_code >= 400:\n    raise ValueError('请求失败')"])[0] if mode == "code" else ""
            return response_model(question={"text": f"场景 {self.question_count}：解释本次请求及代码处理。", "code": code, "pointIds": data["requiredPointIds"], "expectedAnswer": "评分要点：请求和响应、方法、状态码、头部与会话。", "mode": mode})
        if response_model is Grade:
            answer = data["answer"]
            return response_model(points=[{"pointId": p, "passed": answer != "不会", "answerQuote": "虚构引用" if self.bad_quote else answer, "reason": "回答覆盖评分点" if answer != "不会" else "尚未解释评分点"} for p in data["question"]["pointIds"]], feedback="逐项核对完成。", teaching="响应应包含明确状态码。", followup=None)
        if response_model is ProjectReview:
            return response_model(feedback="这是用户提交的实现，尚未由系统运行。", runResultQuote=data.get("runRecord", "") if data.get("runRecord", "").startswith("用户") else "", points=[{"pointId": p["id"], "passed": True, "answerQuote": data["explanation"], "reason": "解释引用可核对"} for p in data["skill"]["points"]], question={"text": "为什么使用这个状态码？失败时怎样恢复？", "pointIds": [p["id"] for p in data["skill"]["points"]], "expectedAnswer": "应解释实现和失败恢复。", "mode": "implementation"})
        raise AssertionError(response_model)


@pytest.fixture
def loop(tmp_path):
    path = tmp_path / "growth.db"
    JobStorage(path).initialize()
    repo = GrowthRepository(path)
    repo.seed()
    clock = SimpleNamespace(value=datetime(2026, 10, 5, 9, tzinfo=ZONE))
    web = SimpleNamespace(settings=SimpleNamespace(llm=LLMConfig(provider="mimo", model="test"), candidate=SimpleNamespace(skills=["HTTP"])), list_jobs=lambda: [])
    leads = SimpleNamespace(list_leads=lambda profile: [])
    service = GrowthService(repo, web, leads, lambda: clock.value)
    return service, repo, clock, FakeGateway()


def target(service, description="要求熟悉 HTTP"):
    return service.add_target({"source": "manual", "title": "AI 应用工程师", "description": description})


def answer_once(service, gateway, answer="请求和响应", skill_id="http", hint=False):
    sid = uuid4().hex
    service.create_session({"sessionId": sid, "skillIds": [skill_id]}, gateway)
    session = service.repo.get("sessions", sid)
    qid = session["questions"][0]["id"]
    payload = {"sessionId": sid, "questionId": qid, "answer": answer}
    if hint:
        service.hint(payload, gateway)
    service.prepare_answer(payload)
    service.answer(payload, gateway)
    return sid


def test_closed_loop_wrong_teaching_next_day_evidence_and_jd_reassessment(loop):
    service, repo, clock, gateway = loop
    job = target(service)
    service.analyze({}, gateway)
    initial = service.plan()
    answer_once(service, gateway, "不会")
    assert service.skill_detail("http")["status"] == "needs_practice"
    service.reflect(initial["date"], initial["tasks"][0]["id"], {"status": "blocked", "blocker": "状态码还不理解", "output": "已提交第一次回答"})
    clock.value += timedelta(days=1)
    answer_once(service, gateway)
    updated = service.snapshot()
    http = next(s for s in updated["skills"] if s["id"] == "http")
    assert http["level"] == 2
    assert http["streak"] == 1
    assert http["nextReview"] == "2026-10-07"
    assert updated["targets"][0]["requirements"][0]["status"] == "supported"
    next_plan = service.plan()
    assert "状态码还不理解" in next_plan["tasks"][0]["reason"]
    assert next_plan["tasks"][0]["references"][0]["targetId"] == job["id"]
    assert repo.get("plans", "2026-10-05")["tasks"][0]["status"] == "blocked"


def test_hint_then_correct_is_assisted_and_not_an_independent_streak(loop):
    service, _, _, gateway = loop
    answer_once(service, gateway, hint=True)
    state = service.skill_detail("http")
    assert state["level"] == 0
    assert state["streak"] == 0
    assert state["nextReview"] == "2026-10-06"
    assert all(p["status"] == "needs_hint" for p in state["points"])
    answer_once(service, gateway)
    assert service.skill_detail("http")["streak"] == 0


def test_same_day_practice_preserves_existing_independent_proofs(loop):
    service, _, _, gateway = loop
    answer_once(service, gateway)
    answer_once(service, gateway)
    state = service.skill_detail("http")
    assert state["level"] == 2
    assert state["streak"] == 1
    assert all(point["status"] == "independent" for point in state["points"])


def test_review_allocation_stays_inside_budget_and_small_budget_changes_scope(loop):
    service, _, clock, gateway = loop
    target(service, "HTTP Python RAG")
    service.analyze({}, gateway)
    for skill_id in ("http", "python", "sql", "api"):
        answer_once(service, gateway, skill_id=skill_id)
    clock.value += timedelta(days=1)
    service.update_settings(30)
    small = service.plan()
    assert small["allocation"]["reviewMinutes"] <= 10
    assert small["allocation"]["learningMinutes"] + small["allocation"]["projectMinutes"] == 30
    assert "一小段" in small["tasks"][1]["description"]
    service.update_settings(180)
    larger = service.plan(adjust=True)
    assert larger["allocation"]["reviewMinutes"] <= 15
    assert len(larger["tasks"][1]["criteria"]) > len(small["tasks"][1]["criteria"])


def test_levels_three_to_five_require_distinct_kinds_and_project_followup(loop):
    service, _, clock, gateway = loop
    answer_once(service, gateway)
    clock.value += timedelta(days=1)
    answer_once(service, gateway)
    assert service.skill_detail("http")["level"] == 2  # application alone isn't code evidence
    clock.value += timedelta(days=3)
    answer_once(service, gateway)
    assert service.skill_detail("http")["level"] == 3
    sid = uuid4().hex
    service.project({"skillId": "http", "evidenceId": uuid4().hex, "sessionId": sid, "code": "return JSONResponse(status_code=400)", "explanation": "请求非法时返回400", "runRecord": "用户执行pytest，测试通过"}, gateway)
    assert service.skill_detail("http")["level"] == 3  # review alone cannot promote
    question = service.repo.get("sessions", sid)["questions"][0]
    service.answer({"sessionId": sid, "questionId": question["id"], "answer": "请求非法时返回400"}, gateway)
    assert service.skill_detail("http")["level"] == 4
    clock.value += timedelta(days=7)
    answer_once(service, gateway)
    assert service.skill_detail("http")["level"] == 5
    clock.value += timedelta(days=180)
    assert service.skill_detail("http")["level"] == 5
    assert service.skill_detail("http")["reviewDue"]


def test_duplicate_answer_and_skip_do_not_count_twice(loop):
    service, repo, _, gateway = loop
    sid = answer_once(service, gateway)
    qid = repo.get("sessions", sid)["questions"][0]["id"]
    with pytest.raises(ValueError):
        service.answer({"sessionId": sid, "questionId": qid, "answer": "请求和响应"}, gateway)
    assert len(repo.all("evidence")) == 1
    next_sid = uuid4().hex
    service.create_session({"sessionId": next_sid, "skillIds": ["http"]}, gateway)
    qid = repo.get("sessions", next_sid)["questions"][0]["id"]
    service.answer({"sessionId": next_sid, "questionId": qid, "answer": "", "skipped": True}, gateway)
    assert service.skill_detail("http")["streak"] == 1


def test_unverified_is_not_unlearned_and_resume_claims_do_not_set_levels(loop):
    service, _, _, _ = loop
    state = service.skill_detail("http")
    assert state["selfReported"] == ["HTTP"]
    assert state["level"] == 0
    assert all(p["status"] == "unassessed" for p in state["points"])
    service.mark_unlearned("http", "headers", True)
    assert next(p for p in service.skill_detail("http")["points"] if p["id"] == "headers")["status"] == "not_learned"


def test_jd_cache_quotes_dedup_refresh_and_focus_limit(loop):
    service, _, _, gateway = loop
    job = target(service)
    service.analyze({}, gateway)
    service.analyze({}, gateway)
    assert gateway.calls.count("analyze_jd") == 1
    duplicate = target(service)
    service.analyze({}, gateway)
    assert service.snapshot()["sampleCount"] == 1
    service.update_target(job["id"], {"description": "要求 HTTP 和 RAG"})
    assert service.snapshot()["targets"][0]["analysisStale"]
    gateway.bad_quote = True
    with pytest.raises(ValueError, match="引用"):
        service.analyze({"targetIds": [job["id"]]}, gateway)
    assert service.require("targets", job["id"])["requirements"][0]["quote"] == "HTTP"
    service.update_target(job["id"], {"focus": True})
    service.update_target(duplicate["id"], {"focus": True})
    third = target(service, "HTTP 开发")
    service.update_target(third["id"], {"focus": True})
    with pytest.raises(ValueError, match="3"):
        service.update_target(target(service, "HTTP 场景")["id"], {"focus": True})


def test_fabricated_grade_quote_cannot_promote(loop):
    service, _, _, gateway = loop
    gateway.bad_quote = True
    with pytest.raises(ValueError, match="引用"):
        answer_once(service, gateway)
    state = service.skill_detail("http")
    assert state["level"] == 0
    assert state["status"] == "unverified"
    assert state["evidence"] == []


def test_plan_is_stable_and_adjust_keeps_completed_tasks(loop):
    service, _, _, gateway = loop
    target(service, "要求 HTTP Python RAG")
    service.analyze({}, gateway)
    plan = service.plan()
    assert service.plan() == plan
    service.reflect(plan["date"], plan["tasks"][0]["id"], {"status": "done", "output": "已提交回答"})
    adjusted = service.plan(adjust=True)
    assert adjusted["tasks"][0]["status"] == "done"
    assert adjusted["tasks"][0]["output"] == "已提交回答"
    assert len(adjusted["tasks"]) == 2


def test_plan_waits_for_model_updates_without_changing_an_existing_day(loop):
    service, repo, _, gateway = loop
    target(service, "HTTP Python RAG")
    service.analyze({}, gateway)
    pending = {"id": "pending-analysis", "requestKey": "pending-plan", "kind": "analyze", "status": "running", "createdAt": service.timestamp()}
    repo.save("operations", pending["id"], pending)
    with pytest.raises(ValueError, match="仍在处理"):
        service.plan()
    assert repo.all("plans") == []
    pending["status"] = "completed"
    repo.save("operations", pending["id"], pending)
    plan = service.plan()
    pending["status"] = "queued"
    repo.save("operations", pending["id"], pending)
    assert service.plan() == plan
    with pytest.raises(ValueError, match="仍在处理"):
        service.plan(adjust=True)


def test_old_retried_work_stays_visible_beyond_the_recent_operation_window(loop):
    service, repo, _, gateway = loop
    target(service)
    service.analyze({}, gateway)
    repo.save("operations", "old", {"id": "old", "requestKey": "old", "kind": "answer", "status": "running", "createdAt": "2026-10-04T09:00:00+08:00"})
    for index in range(35):
        key = f"completed-{index}"
        repo.save("operations", key, {"id": key, "requestKey": key, "kind": "answer", "status": "completed", "createdAt": service.timestamp()})
    assert any(operation["id"] == "old" for operation in service.snapshot()["operations"])
    with pytest.raises(ValueError, match="仍在处理"):
        service.plan()


def wait_operation(manager, operation):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        latest = manager.service.repo.get("operations", operation["id"])
        if latest["status"] not in {"queued", "running"}:
            return latest
        time.sleep(0.01)
    raise AssertionError("后台任务没有完成")


def test_background_failure_retry_idempotency_and_restart(loop):
    service, repo, _, gateway = loop
    target(service)
    coordinator = TaskCoordinator()
    manager = GrowthManager(service, coordinator, lambda config: gateway)
    try:
        gateway.fail = True
        operation = manager.start("analyze", {}, "request1")
        assert wait_operation(manager, operation)["status"] == "failed"
        gateway.fail = False
        retried = wait_operation(manager, manager.retry(operation["id"]))
        assert retried["status"] == "completed"
        assert manager.start("analyze", {}, "request1")["id"] == operation["id"]
        with pytest.raises(ValueError):
            manager.start("analyze", {"targetIds": ["different"]}, "request1")
        pending = {"id": "interrupted", "requestKey": "restart", "kind": "analyze", "payload": {}, "inputHash": "x", "status": "running", "createdAt": service.timestamp()}
        repo.save("operations", pending["id"], pending)
    finally:
        manager.shutdown()
    resumed = GrowthManager(service, coordinator, lambda config: gateway)
    try:
        assert repo.get("operations", "interrupted")["status"] == "failed"
        assert wait_operation(resumed, resumed.retry("interrupted"))["status"] == "completed"
    finally:
        resumed.shutdown()


def test_failed_scoring_keeps_answer_and_committed_retry_does_not_score_twice(loop):
    service, repo, _, gateway = loop
    sid = uuid4().hex
    service.create_session({"sessionId": sid, "skillIds": ["http"]}, gateway)
    qid = repo.get("sessions", sid)["questions"][0]["id"]
    manager = GrowthManager(service, TaskCoordinator(), lambda config: gateway)
    try:
        gateway.fail = True
        operation = manager.start("answer", {"sessionId": sid, "questionId": qid, "answer": "请求与响应"}, "saved-answer")
        assert wait_operation(manager, operation)["status"] == "failed"
        assert repo.get("sessions", sid)["questions"][0]["submittedAnswer"] == "请求与响应"
        gateway.fail = False
        assert wait_operation(manager, manager.retry(operation["id"]))["status"] == "completed"
        calls = gateway.calls.count("grade")
        persisted = repo.get("operations", operation["id"])
        persisted["status"] = "failed"  # emulate crash after evidence commit, before operation commit
        repo.save("operations", persisted["id"], persisted)
        assert wait_operation(manager, manager.retry(operation["id"]))["status"] == "completed"
        assert gateway.calls.count("grade") == calls
        assert len(repo.all("evidence")) == 1
    finally:
        manager.shutdown()


def test_session_generation_retries_only_unfinished_questions(loop, monkeypatch):
    service, repo, _, gateway = loop
    original = gateway.generate
    fail_second = [True]

    def generate(model, system, prompt):
        if model is QuestionOutput and gateway.question_count == 1 and fail_second[0]:
            raise ValueError("第二题生成中断")
        return original(model, system, prompt)

    monkeypatch.setattr(gateway, "generate", generate)
    payload = {"sessionId": "partial", "skillIds": ["http", "python"]}
    with pytest.raises(ValueError):
        service.create_session(payload, gateway)
    first_id = repo.get("sessions", "partial")["questions"][0]["id"]
    assert repo.get("sessions", "partial")["status"] == "generating"
    fail_second[0] = False
    service.create_session(payload, gateway)
    completed = repo.get("sessions", "partial")
    assert completed["status"] == "active"
    assert completed["questions"][0]["id"] == first_id
    assert len(completed["questions"]) == 2


def test_removed_targets_keep_traceable_quotes_without_affecting_priorities(loop):
    service, _, _, gateway = loop
    job = target(service)
    service.analyze({}, gateway)
    plan = service.plan()
    service.update_target(job["id"], {"active": False})
    snapshot = service.snapshot()
    assert snapshot["sampleCount"] == 0
    assert snapshot["nextSkillId"] is None
    assert snapshot["targets"][0]["requirements"][0]["quote"] == "HTTP"
    assert plan["tasks"][0]["references"][0]["targetId"] == job["id"]


def test_midnight_uses_beijing_not_utc(loop):
    service, _, clock, _ = loop
    clock.value = datetime.fromisoformat("2026-10-05T16:01:00+00:00")
    assert service.snapshot()["today"] == "2026-10-06"


def test_public_http_hides_scoring_answers_and_persists_growth(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("""app:
  database_path: data/test.db
crawler:
  render_mode: never
  user_agent: Career Radar offline growth tests
llm:
  provider: mimo
  model: fake
smtp:
  enabled: false
companies:
  - name: 示例
    url: https://example.com/careers
""", encoding="utf-8")
    app = create_app(config, web_dist=tmp_path / "missing")
    fake = FakeGateway()
    app.state.growth_manager.gateway_factory = lambda config: fake
    with TestClient(app) as client:
        response = client.post("/api/growth/targets", json={"source": "manual", "title": "AI", "description": "HTTP"})
        assert response.status_code == 200
        operation = client.post("/api/growth/analyze", json={"requestId": "analyze"}).json()
        assert wait_operation(app.state.growth_manager, operation)["status"] == "completed"
        operation = client.post("/api/growth/sessions", json={"requestId": "session", "skillIds": ["http"]}).json()
        sid = wait_operation(app.state.growth_manager, operation)["result"]["sessionId"]
        public = client.get(f"/api/growth/sessions/{sid}")
        assert "expectedAnswer" not in public.text
        assert "expectedAnswer" not in client.get("/api/growth").text
        assert client.post("/api/growth/plans/today", json={}).status_code == 200
        assert client.post("/api/growth/plans/today", json={}).json()["revision"] == 1
        assert client.put("/api/growth/settings", json={"dailyMinutes": 0}).status_code == 422
        storage = JobStorage(app.state.repository.settings.app.database_path)
        storage.store_jobs([JobPosting(company="离线官网企业", title="AI 应用开发", description="要求熟悉 HTTP 和 Python，负责 API 服务与完整异常处理。", source_url="https://example.com/jobs/growth")], "2026-10-05T09:00:00+08:00")
        app.state.platform_leads.import_leads([BossLead(external_id="growthabc", title="AI Agent 工程师", company="离线平台企业", location="上海", salary="面议", tags="经验不限", description="要求掌握 HTTP 请求与响应、Python 服务开发，并具备测试与异常恢复能力。" * 4, source_url="https://www.zhipin.com/job_detail/growthabc.html")])
        sources = client.get("/api/growth/sources").json()
        assert {source["source"] for source in sources} == {"official", "boss"}
        for source in sources:
            imported = client.post("/api/growth/targets", json={"source": source["source"], "id": source["id"]})
            assert imported.status_code == 200
            assert imported.json()["sourceId"] == source["id"]
            assert "HTTP" in imported.json()["description"]
    restarted = create_app(config, web_dist=tmp_path / "missing")
    with TestClient(restarted) as client:
        assert len(client.get("/api/growth").json()["targets"]) == 3
        assert client.get(f"/api/growth/sessions/{sid}").json()["status"] == "active"


def test_migration_preserves_existing_jobs_and_is_idempotent(tmp_path):
    storage = JobStorage(tmp_path / "migration.db")
    storage.initialize()
    with storage.transaction() as connection:
        connection.execute("PRAGMA user_version=11")
        connection.execute("INSERT INTO page_analysis_cache(company_name,final_url,context_hash,content_hash,document_json,analysis_json,updated_at) VALUES ('企业','https://example.com','context','content','原有数据','{}','2026-10-05')")
    storage.initialize()
    storage.initialize()
    with storage.transaction() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12
        assert connection.execute("SELECT document_json FROM page_analysis_cache").fetchone()[0] == "原有数据"
        assert connection.execute("SELECT COUNT(*) FROM growth_evidence").fetchone()[0] == 0


def test_technical_requirements_cannot_be_hidden_as_enrollment_conditions(loop):
    service, _, _, gateway = loop
    target(service, "必须熟悉 Python 和 HTTP，能用 SQL 查询。")
    gateway.generate = lambda model, system, prompt: JDAnalysis(requirements=[{"skill": "HTTP", "quote": "必须熟悉 Python 和 HTTP", "kind": "hard", "minimumLevel": 3}])
    with pytest.raises(ValueError, match="报名条件"):
        service.analyze({}, gateway)
    assert service.snapshot()["targets"][0]["requirements"] == []


def test_project_followup_cannot_invent_replacement_code(loop):
    service, repo, _, gateway = loop
    original = gateway.generate

    def generate(model, system, prompt):
        result = original(model, system, prompt)
        if model is ProjectReview:
            result.question.code = "response.headers['Location'] = '/new'; return JSONResponse({})"
        return result

    gateway.generate = generate
    with pytest.raises(ValueError, match="提交"):
        service.project({"skillId": "http", "evidenceId": "invented", "sessionId": "invented", "code": "return JSONResponse(status_code=400)", "explanation": "非法请求返回400", "runRecord": ""}, gateway)
    assert repo.all("evidence") == []


def test_explicit_no_run_record_cannot_raise_level_four(loop):
    service, _, clock, gateway = loop
    answer_once(service, gateway)
    clock.value += timedelta(days=1)
    answer_once(service, gateway)
    clock.value += timedelta(days=3)
    answer_once(service, gateway)
    assert service.skill_detail("http")["level"] == 3
    service.project({"skillId": "http", "evidenceId": "not-run", "sessionId": "not-run", "code": "return JSONResponse(status_code=400)", "explanation": "非法请求返回400", "runRecord": "未实际运行，没有测试结果。"}, gateway)
    question = service.require("sessions", "not-run")["questions"][0]
    service.answer({"sessionId": "not-run", "questionId": question["id"], "answer": "非法请求返回400"}, gateway)
    assert service.skill_detail("http")["level"] == 3


def test_generated_http_code_must_be_reviewed_and_separate_from_question_text(loop):
    service, repo, _, gateway = loop
    original = gateway.generate

    def generate(model, system, prompt):
        result = original(model, system, prompt)
        if model is QuestionOutput:
            result.question.code = "def profile(session_id: str): return session_id"
        return result

    gateway.generate = generate
    with pytest.raises(ValueError, match="应用程序"):
        service.create_session({"sessionId": "unreviewed", "skillIds": ["http"]}, gateway)
    assert repo.get("sessions", "unreviewed")["questions"] == []
    gateway.generate = original
    question = original(QuestionOutput, "", json.dumps({"task": "question", "allowedModes": ["explain"], "requiredPointIds": ["request"], "skill": service.require("skills", "http")})).question
    question.text = "阅读下面代码：```python\nprint('hidden')\n```"
    with pytest.raises(ValueError, match="正文"):
        service._question(question, service.require("skills", "http"))


def test_reviewed_examples_accept_crlf_but_reject_changed_semantics(loop):
    service, _, _, gateway = loop
    original = gateway.generate

    def generate(model, system, prompt):
        result = original(model, system, prompt)
        if model is QuestionOutput:
            result.question.code = service.require("skills", "http")["questionExamples"][0].replace("\n", "\r\n")
        return result

    gateway.generate = generate
    service.create_session({"sessionId": "crlf", "skillIds": ["http"]}, gateway)
    assert service.require("sessions", "crlf")["status"] == "active"
    source = "def route():\n    if bad:\n        return 400\n    return 201"
    assert code_excerpt("if bad:\n    return 400\nreturn 201", source)
    assert not code_excerpt("if bad:\n    return 500\nreturn 201", source)
    assert original_code_excerpt("if bad:\n        return 400\n    return 201", source) == "if bad:\n    return 400\nreturn 201"
    example = service.require("skills", "http")["questionExamples"][1]
    assert http_message_example(example.replace("/api/messages", "/api/apply").replace('"message": "hello"', '"jobId": 42'))
    assert not http_message_example("def profile(session_id: str): return session_id")
