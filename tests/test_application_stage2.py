"""第二阶段 DeepSeek 评估、双审工作流、隐私和断点恢复测试。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from career_radar.application.content import ApplicationContentGenerator
from career_radar.application.document_renderer import (
    ApplicationDocumentRenderer,
    RenderedApplicationDocuments,
)
from career_radar.application.document_verifier import ApplicationDocumentVerifier
from career_radar.application.document_workflow import ApplicationDocumentWorkflow
from career_radar.application.evaluator import DIMENSION_WEIGHTS, JobApplicationEvaluator
from career_radar.application.llm import DeepSeekApplicationGateway
from career_radar.application.models import (
    ApplicationConfig,
    ApplicationDraftBundle,
    ApplicationProfile,
    ApplicationRun,
    ApplicationStatus,
    ApplicationVerification,
    DocumentVerification,
    JobFitEvaluation,
    VerificationIssue,
)
from career_radar.application.profile import profile_llm_context
from career_radar.application.repository import ApplicationRepository
from career_radar.application.service import ApplicationService
from career_radar.application.workflow import ApplicationWorkflow
from career_radar.llm import FatalLLMError
from career_radar.models import JobPosting, LLMConfig, MatchLevel
from career_radar.storage import JobStorage


def _profile_payload(*, confirmed: bool = True, cover_mode: str = "always") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "verification_status": "confirmed" if confirmed else "needs_review",
        "contact": {
            "name": "隐私测试姓名",
            "phone": "13811112222",
            "email": "private-candidate@example.com",
            "location": "福建莆田",
            "github": "https://github.com/private-person",
        },
        "education": [
            {
                "institution": "测试学院",
                "degree": "本科",
                "major": "数据科学与大数据技术",
                "start_date": "2022.09",
                "end_date": "2026.06",
                "source_ids": ["resume"],
            }
        ],
        "experiences": [],
        "projects": [
            {
                "name": "数据分析平台",
                "description": "完成公开数据采集、清洗与可视化。",
                "responsibilities": ["使用 Python 清洗数据"],
                "technologies": ["Python", "MySQL"],
                "links": ["https://github.com/private-person/private-project"],
                "source_ids": ["resume"],
            }
        ],
        "skills": [
            {
                "name": "Python",
                "level": "熟悉",
                "evidence": ["数据分析平台"],
                "source_ids": ["resume"],
            }
        ],
        "awards": [],
        "leadership": [],
        "preferences": {
            "target_roles": ["数据开发", "数据分析"],
            "preferred_locations": ["福州", "厦门"],
            "cover_letter_mode": cover_mode,
            "resume_page_target": 1,
        },
        "sources": [
            {
                "id": "resume",
                "kind": "resume_docx",
                "path": "C:\\Users\\Private\\Desktop\\resume.docx",
                "imported_at": "2026-07-22T08:00:00+08:00",
                "visually_verified": True,
            }
        ],
        "review_notes": ["自由备注 private-candidate@example.com"],
    }


def _job() -> JobPosting:
    return JobPosting(
        company="测试科技",
        title="数据开发工程师",
        location="福州",
        description="负责数据采集、清洗和数据服务开发，并提交求职信。",
        requirements="2026届本科，熟悉 Python 和 MySQL。",
        recruitment_type="校招",
        is_2026_target=True,
        target_graduates="2026届",
        apply_url="https://example.com/apply?token=secret",
        contact_email="jobs@example.com",
        source_url="https://example.com/jobs/1",
        match_level=MatchLevel.HIGH,
    )


def _evaluation_payload() -> dict[str, Any]:
    scores = {
        "skills": 80,
        "projects_experience": 70,
        "education_graduation": 90,
        "career": 75,
        "logistics": 80,
    }
    return {
        "eligibility": [
            {
                "name": "毕业年份",
                "verdict": "pass",
                "reason": "2026届匹配",
                "evidence": "本科结束时间为2026.06",
            }
        ],
        "dimensions": [
            {
                "name": name,
                "score": score,
                "weight": 1,
                "strengths": ["有画像证据"],
                "gaps": [],
                "evidence": ["数据分析平台"],
            }
            for name, score in scores.items()
        ],
        "overall_score": 1,
        "difficulty_score": 6,
        "verdict": "weak",
        "recommendation": "建议申请",
        "requirement_coverage": [
            {
                "requirement": "熟悉 Python",
                "priority": "required",
                "status": "matched",
                "candidate_evidence": ["数据分析平台"],
                "honest_bridge": None,
            }
        ],
    }


def _resume_payload(*, source_id: str = "resume") -> dict[str, Any]:
    return {
        "headline": "2026届数据开发候选人",
        "professional_summary": "具备数据采集、清洗与分析项目经验。",
        "skills": [{"text": "Python（熟悉）", "source_ids": [source_id]}],
        "education": [
            {
                "institution": "测试学院",
                "degree": "本科",
                "major": "数据科学与大数据技术",
                "period": "2022.09-2026.06",
                "highlights": [],
                "source_ids": [source_id],
            }
        ],
        "experiences": [],
        "projects": [
            {
                "name": "数据分析平台",
                "period": None,
                "summary": "公开数据处理项目",
                "bullets": ["使用 Python 完成数据清洗"],
                "technologies": ["Python", "MySQL"],
                "source_ids": [source_id],
            }
        ],
        "awards": [],
        "leadership": [],
        "omitted_items": [],
        "grounding_warnings": [],
    }


def _cover_payload() -> dict[str, Any]:
    return {
        "subject": "应聘数据开发工程师",
        "salutation": "招聘团队您好：",
        "paragraphs": ["我希望申请该岗位。", "我的真实项目与岗位数据处理职责相关。"],
        "closing": "感谢审阅。",
        "requirement_bridges": ["用项目经验回应 Python 要求"],
        "source_ids": ["resume"],
    }


def _review_payload(reviewer: str) -> dict[str, Any]:
    return {"reviewer": reviewer, "passed": True, "findings": [], "summary": "通过"}


class QueueGateway:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[str, str, str]] = []

    def generate(self, response_model, system_prompt: str, user_prompt: str):
        self.calls.append((response_model.__name__, system_prompt, user_prompt))
        value = self.payloads.pop(0)
        if isinstance(value, Exception):
            raise value
        return response_model.model_validate(value)


def _workflow_fixture(
    tmp_path: Path,
    gateway: QueueGateway,
    *,
    confirmed: bool = True,
    cover_mode: str = "always",
) -> tuple[ApplicationService, ApplicationWorkflow, str, ApplicationRepository]:
    database = tmp_path / "data/jobs.db"
    storage = JobStorage(database)
    storage.initialize()
    event = storage.store_jobs([_job()], "2026-07-22T08:00:00+08:00")[0]
    profile_path = tmp_path / "private/application_profile.yaml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        yaml.safe_dump(
            _profile_payload(confirmed=confirmed, cover_mode=cover_mode),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    repository = ApplicationRepository(database)
    service = ApplicationService(
        repository,
        ApplicationConfig(profile_path=profile_path),
        "Asia/Shanghai",
    )
    workflow = ApplicationWorkflow(
        repository,
        JobApplicationEvaluator(gateway),
        ApplicationContentGenerator(gateway),
        "Asia/Shanghai",
    )
    return service, workflow, event.entity_key, repository


def test_profile_context_removes_all_contact_paths_and_free_notes() -> None:
    profile = ApplicationProfile.model_validate(_profile_payload())

    serialized = json.dumps(profile_llm_context(profile), ensure_ascii=False)

    for forbidden in (
        "隐私测试姓名",
        "13811112222",
        "private-candidate@example.com",
        "github.com/private-person",
        "C:\\Users\\Private",
        "自由备注",
    ):
        assert forbidden not in serialized


def test_unconfirmed_profile_cannot_create_application(tmp_path: Path) -> None:
    gateway = QueueGateway([])
    service, _workflow, job_id, _repository = _workflow_fixture(
        tmp_path, gateway, confirmed=False
    )

    with pytest.raises(ValueError, match="尚未确认"):
        service.create(job_id)


def test_full_stage_two_flow_persists_evaluation_drafts_and_reviews(tmp_path: Path) -> None:
    final_bundle = {"resume": _resume_payload(), "cover_letter": _cover_payload()}
    gateway = QueueGateway(
        [
            _evaluation_payload(),
            _resume_payload(),
            _cover_payload(),
            _review_payload("recruiter_ats"),
            _review_payload("factual"),
            final_bundle,
        ]
    )
    service, workflow, job_id, repository = _workflow_fixture(tmp_path, gateway)
    run = service.create(job_id)

    waiting = workflow.evaluate(run.id)
    assert waiting.status == ApplicationStatus.WAITING_FOR_APPROVAL
    evaluation = repository.get_evaluation(run.id)
    assert evaluation is not None
    assert evaluation.overall_score == 79
    assert evaluation.verdict == "strong"
    assert {item.name: item.weight for item in evaluation.dimensions} == DIMENSION_WEIGHTS

    finished = workflow.approve_and_generate(run.id)
    assert finished.status == ApplicationStatus.RENDERING
    assert len(gateway.calls) == 6
    assert repository.get_draft_bundle(run.id, 1) is not None
    assert repository.get_draft_bundle(run.id, 2) is not None
    factual = repository.get_review(run.id, "factual", 1)
    recruiter = repository.get_review(run.id, "recruiter_ats", 1)
    assert factual is not None and factual.reviewer == "factual"
    assert recruiter is not None and recruiter.reviewer == "recruiter_ats"

    all_prompts = "\n".join(prompt for _model, _system, prompt in gateway.calls)
    assert "隐私测试姓名" not in all_prompts
    assert "13811112222" not in all_prompts
    assert "private-candidate@example.com" not in all_prompts
    assert "C:\\Users\\Private" not in all_prompts
    assert "token=secret" not in all_prompts
    assert "jobs@example.com" not in all_prompts


def test_approval_cannot_be_skipped(tmp_path: Path) -> None:
    gateway = QueueGateway([])
    service, workflow, job_id, _repository = _workflow_fixture(tmp_path, gateway)
    run = service.create(job_id)

    with pytest.raises(ValueError, match="等待批准"):
        workflow.approve_and_generate(run.id)
    assert gateway.calls == []


def test_unknown_grounding_source_marks_drafting_failed(tmp_path: Path) -> None:
    gateway = QueueGateway([_evaluation_payload(), _resume_payload(source_id="invented")])
    service, workflow, job_id, _repository = _workflow_fixture(
        tmp_path, gateway, cover_mode="never"
    )
    run = service.create(job_id)
    assert workflow.evaluate(run.id).status == ApplicationStatus.WAITING_FOR_APPROVAL

    failed = workflow.approve_and_generate(run.id)

    assert failed.status == ApplicationStatus.FAILED
    assert failed.failed_step == ApplicationStatus.DRAFTING


def test_resume_reuses_persisted_steps_without_repeating_llm_calls(tmp_path: Path) -> None:
    first_gateway = QueueGateway(
        [
            _evaluation_payload(),
            _resume_payload(),
            _review_payload("factual"),
            RuntimeError("模拟招聘官审查网络中断"),
        ]
    )
    service, workflow, job_id, repository = _workflow_fixture(
        tmp_path, first_gateway, cover_mode="never"
    )
    run = service.create(job_id)
    assert workflow.evaluate(run.id).status == ApplicationStatus.WAITING_FOR_APPROVAL
    failed = workflow.approve_and_generate(run.id)
    assert failed.status == ApplicationStatus.FAILED
    assert failed.failed_step == ApplicationStatus.RECRUITER_REVIEW
    assert repository.get_draft_bundle(run.id, 1) is not None
    assert repository.get_review(run.id, "factual", 1) is not None

    resume_gateway = QueueGateway(
        [
            _review_payload("recruiter_ats"),
            {"resume": _resume_payload(), "cover_letter": None},
        ]
    )
    resumed_workflow = ApplicationWorkflow(
        repository,
        JobApplicationEvaluator(resume_gateway),
        ApplicationContentGenerator(resume_gateway),
        "Asia/Shanghai",
    )

    finished = resumed_workflow.resume(run.id)

    assert finished.status == ApplicationStatus.RENDERING
    assert [call[0] for call in resume_gateway.calls] == [
        "ApplicationReview",
        "ApplicationDraftBundle",
    ]


class _FakeCompletions:
    def __init__(self, values: list[object]) -> None:
        self.values = values
        self.calls = 0

    def create(self, **_request):
        value = self.values[self.calls]
        self.calls += 1
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(value)))]
        )


class _Fatal401(Exception):
    status_code = 401


def test_deepseek_gateway_retries_invalid_structure_but_not_auth_failure() -> None:
    completions = _FakeCompletions([{"wrong": True}, _evaluation_payload()])
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    sleeps: list[float] = []
    gateway = DeepSeekApplicationGateway(
        LLMConfig(provider="deepseek", model="test", max_retries=2),
        client=client,
        sleeper=sleeps.append,
    )

    result = gateway.generate(JobFitEvaluation, "system", "user")

    assert result.difficulty_score == 6
    assert completions.calls == 2
    assert sleeps == [1]

    fatal_completions = _FakeCompletions([_Fatal401("bad key"), _evaluation_payload()])
    fatal_client = SimpleNamespace(chat=SimpleNamespace(completions=fatal_completions))
    fatal_gateway = DeepSeekApplicationGateway(
        LLMConfig(provider="deepseek", model="test", max_retries=2),
        client=fatal_client,
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(FatalLLMError):
        fatal_gateway.generate(JobFitEvaluation, "system", "user")
    assert fatal_completions.calls == 1


class _FakeRenderer:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.render_calls = 0

    def _paths(self, run) -> RenderedApplicationDocuments:
        output = self.root / run.id
        output.mkdir(parents=True, exist_ok=True)
        resume = output / "resume.docx"
        if not resume.exists():
            resume.write_bytes(b"fake-docx-for-workflow-test")
        return RenderedApplicationDocuments(
            output_dir=output,
            resume_docx=resume,
            resume_pdf=None,
            cover_letter_docx=None,
            cover_letter_pdf=None,
        )

    def render(self, run, _job, _profile, _drafts, _date):
        self.render_calls += 1
        return self._paths(run)

    def existing(self, run, _drafts):
        return self._paths(run)


class _FakeVerifier:
    def __init__(self, *, passed: bool) -> None:
        self.passed = passed

    def verify(self, run, _job, _profile, _drafts, rendered, generated_at):
        issues = []
        if not self.passed:
            issues.append(
                VerificationIssue(
                    severity="error",
                    code="test_failure",
                    document_kind="resume",
                    message="模拟文档校验失败",
                )
            )
        return ApplicationVerification(
            application_id=run.id,
            passed=self.passed,
            documents=[
                DocumentVerification(
                    document_kind="resume",
                    docx_sha256="0" * 64,
                    docx_bytes=rendered.resume_docx.stat().st_size,
                    expected_text_checks=1,
                    issues=issues,
                )
            ],
            generated_at=generated_at,
        )


def _rendering_run(tmp_path: Path):
    gateway = QueueGateway(
        [
            _evaluation_payload(),
            _resume_payload(),
            _review_payload("factual"),
            _review_payload("recruiter_ats"),
            {"resume": _resume_payload(), "cover_letter": None},
        ]
    )
    service, workflow, job_id, repository = _workflow_fixture(
        tmp_path, gateway, cover_mode="never"
    )
    run = service.create(job_id)
    workflow.evaluate(run.id)
    rendering = workflow.approve_and_generate(run.id)
    assert rendering.status == ApplicationStatus.RENDERING
    return rendering, repository


def test_document_workflow_registers_artifacts_and_reaches_ready(tmp_path: Path) -> None:
    run, repository = _rendering_run(tmp_path)
    renderer = _FakeRenderer(tmp_path / "private/application_outputs")
    workflow = ApplicationDocumentWorkflow(
        repository,
        renderer,  # type: ignore[arg-type]
        _FakeVerifier(passed=True),  # type: ignore[arg-type]
        "Asia/Shanghai",
    )

    ready = workflow.run(run.id)

    assert ready.status == ApplicationStatus.READY
    assert ready.completed_at is not None
    assert renderer.render_calls == 1
    artifacts = repository.list_artifacts(run.id)
    assert {artifact.kind for artifact in artifacts} == {"resume_docx", "verification"}
    assert all(Path(artifact.path).is_file() for artifact in artifacts)


def test_document_verification_failure_resumes_without_rerendering(tmp_path: Path) -> None:
    run, repository = _rendering_run(tmp_path)
    renderer = _FakeRenderer(tmp_path / "private/application_outputs")
    failing = ApplicationDocumentWorkflow(
        repository,
        renderer,  # type: ignore[arg-type]
        _FakeVerifier(passed=False),  # type: ignore[arg-type]
        "Asia/Shanghai",
    )
    failed = failing.run(run.id)
    assert failed.status == ApplicationStatus.FAILED
    assert failed.failed_step == ApplicationStatus.VERIFYING
    assert renderer.render_calls == 1

    passing = ApplicationDocumentWorkflow(
        repository,
        renderer,  # type: ignore[arg-type]
        _FakeVerifier(passed=True),  # type: ignore[arg-type]
        "Asia/Shanghai",
    )
    ready = passing.resume(run.id)

    assert ready.status == ApplicationStatus.READY
    assert renderer.render_calls == 1


def test_real_docx_renderer_injects_contact_and_passes_structural_audit(
    tmp_path: Path,
) -> None:
    profile = ApplicationProfile.model_validate(_profile_payload())
    drafts = ApplicationDraftBundle.model_validate(
        {"resume": _resume_payload(), "cover_letter": _cover_payload()}
    )
    run = ApplicationRun(
        id="app-20260722000000-pytest12",
        job_id="job-test",
        job_content_hash="1" * 64,
        profile_hash="2" * 64,
        status=ApplicationStatus.RENDERING,
        created_at="2026-07-22T08:00:00+08:00",
        updated_at="2026-07-22T08:00:00+08:00",
    )
    config = ApplicationConfig(output_dir=tmp_path / "private/outputs", pdf_mode="never")
    renderer = ApplicationDocumentRenderer(config)

    rendered = renderer.render(run, _job(), profile, drafts, "2026年07月22日")
    report = ApplicationDocumentVerifier(config).verify(
        run,
        _job(),
        profile,
        drafts,
        rendered,
        "2026-07-22T08:01:00+08:00",
    )

    assert report.passed is True
    assert rendered.resume_docx.is_file()
    assert rendered.cover_letter_docx is not None
    assert rendered.cover_letter_docx.is_file()
    assert all(not document.issues for document in report.documents)
