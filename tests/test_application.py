"""私有申请画像、状态机、SQLite 快照和 CLI 骨架测试。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from career_radar.application.models import (
    APPLICATION_STATUS_PROGRESS,
    ApplicationConfig,
    ApplicationProfile,
    ApplicationStatus,
)
from career_radar.application.profile import (
    ApplicationProfileError,
    load_application_profile,
    profile_summary,
)
from career_radar.application.repository import ApplicationRepository
from career_radar.application.service import ApplicationService
from career_radar.cli import main
from career_radar.config import load_settings
from career_radar.models import JobPosting, MatchLevel
from career_radar.storage import JobStorage


def test_application_status_metadata_covers_the_complete_state_machine() -> None:
    assert set(APPLICATION_STATUS_PROGRESS) == set(ApplicationStatus)
    assert APPLICATION_STATUS_PROGRESS[ApplicationStatus.READY] == 100


def _profile_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "verification_status": "confirmed",
        "contact": {
            "name": "测试候选人",
            "phone": "13800000000",
            "email": "candidate@example.com",
            "location": "福建福州",
        },
        "education": [
            {
                "institution": "测试大学",
                "degree": "本科",
                "major": "数据科学",
                "start_date": "2022.09",
                "end_date": "2026.06",
                "source_ids": ["resume"],
            }
        ],
        "experiences": [],
        "projects": [
            {
                "name": "数据平台",
                "description": "完成数据采集与分析。",
                "technologies": ["Python", "MySQL"],
                "source_ids": ["resume"],
            }
        ],
        "skills": [
            {
                "name": "Python",
                "level": "熟悉",
                "evidence": ["数据平台"],
                "source_ids": ["resume"],
            }
        ],
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
                "id": "resume",
                "kind": "resume_docx",
                "path": "private/master_resume.docx",
                "imported_at": "2026-07-22T08:00:00+08:00",
                "visually_verified": False,
            }
        ],
        "review_notes": ["请确认联系方式"],
    }


def _write_profile(path: Path) -> ApplicationProfile:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(_profile_payload(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return load_application_profile(path)


def _job() -> JobPosting:
    return JobPosting(
        company="测试公司",
        title="数据开发工程师",
        location="福州",
        description="负责数据采集、清洗和数据服务开发。",
        requirements="2026届本科，熟悉Python和MySQL。",
        recruitment_type="校招",
        is_2026_target=True,
        target_graduates="2026届",
        apply_url="https://example.com/apply/1",
        source_url="https://example.com/jobs/1",
        match_level=MatchLevel.HIGH,
    )


def _service(tmp_path: Path) -> tuple[ApplicationService, str, Path]:
    database = tmp_path / "data/jobs.db"
    storage = JobStorage(database)
    storage.initialize()
    event = storage.store_jobs([_job()], "2026-07-22T08:00:00+08:00")[0]
    profile_path = tmp_path / "private/application_profile.yaml"
    _write_profile(profile_path)
    repository = ApplicationRepository(database)
    service = ApplicationService(
        repository,
        ApplicationConfig(profile_path=profile_path),
        "Asia/Shanghai",
    )
    return service, event.entity_key, database


def test_private_profile_loads_and_summary_never_exposes_contact(tmp_path: Path) -> None:
    profile = _write_profile(tmp_path / "private/profile.yaml")

    summary = profile_summary(profile)
    serialized = json.dumps(summary, ensure_ascii=False)

    assert summary["verificationStatus"] == "confirmed"
    assert summary["projectCount"] == 1
    assert "测试候选人" not in serialized
    assert "13800000000" not in serialized
    assert "candidate@example.com" not in serialized
    assert "reviewNotes" not in summary


def test_profile_rejects_unknown_fact_source(tmp_path: Path) -> None:
    payload = _profile_payload()
    payload["projects"][0]["source_ids"] = ["unknown"]  # type: ignore[index]
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ApplicationProfileError, match="未知来源"):
        load_application_profile(path)


def test_application_run_freezes_job_and_private_profile(tmp_path: Path) -> None:
    service, job_id, database = _service(tmp_path)

    run = service.create(job_id)
    saved = service.get(run.id)
    snapshot = service.repository.get_profile_snapshot(run.id)
    public = service.public_json(saved)

    assert saved.status == ApplicationStatus.CREATED
    assert saved.job_id == job_id
    assert snapshot is not None
    assert snapshot.contact.name == "测试候选人"
    assert "测试候选人" not in json.dumps(public, ensure_ascii=False)
    assert public["nextAction"] == "等待岗位匹配评估"
    with sqlite3.connect(database) as connection:
        frozen_job = connection.execute(
            "SELECT job_snapshot_json FROM application_runs WHERE application_id = ?",
            (run.id,),
        ).fetchone()
    assert frozen_job is not None
    assert "数据开发工程师" in frozen_job[0]


def test_state_machine_blocks_skipped_approval_and_supports_failure_resume(
    tmp_path: Path,
) -> None:
    service, job_id, _database = _service(tmp_path)
    run = service.create(job_id)

    with pytest.raises(ValueError, match="不允许"):
        service.transition(run.id, ApplicationStatus.DRAFTING)

    evaluating = service.transition(run.id, ApplicationStatus.EVALUATING)
    assert evaluating.status == ApplicationStatus.EVALUATING
    failed = service.repository.mark_failed(
        run.id,
        "模拟瞬时失败 candidate@example.com",
        "2026-07-22T09:00:00+08:00",
    )
    assert failed.status == ApplicationStatus.FAILED
    assert failed.failed_step == ApplicationStatus.EVALUATING
    assert "candidate@example.com" not in json.dumps(service.public_json(failed))
    resumed = service.resume(run.id)
    assert resumed.status == ApplicationStatus.EVALUATING
    waiting = service.transition(run.id, ApplicationStatus.WAITING_FOR_APPROVAL)
    approved = service.transition(waiting.id, ApplicationStatus.DRAFTING)
    assert approved.approved_at is not None


def test_database_initialization_creates_all_application_tables(tmp_path: Path) -> None:
    database = tmp_path / "jobs.db"
    JobStorage(database).initialize()

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'application_%'"
            )
        }
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert tables == {
        "application_runs",
        "application_profile_snapshots",
        "application_evaluations",
        "application_drafts",
        "application_reviews",
        "application_artifacts",
    }
    assert version >= 6


def test_existing_version_five_database_is_upgraded_in_place(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 5")

    JobStorage(database).initialize()

    with sqlite3.connect(database) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='application_runs'"
        ).fetchone()
    assert version == 8
    assert table == ("application_runs",)


def _config(profile_path: Path) -> str:
    return f"""
app:
  database_path: data/jobs.db
  output_dir: output
  log_dir: logs
crawler:
  render_mode: never
  request_delay_min_seconds: 0
  request_delay_max_seconds: 0
  user_agent: Mozilla/5.0 Career Radar application test
llm:
  provider: deepseek
  model: test-model
application:
  profile_path: {profile_path.as_posix()}
smtp:
  enabled: false
companies:
  - name: 测试公司
    url: https://example.com/careers
"""


def test_cli_checks_profile_and_creates_local_application_without_llm(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile_path = tmp_path / "private/profile.yaml"
    _write_profile(profile_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_config(profile_path), encoding="utf-8")
    settings = load_settings(config_path)
    storage = JobStorage(settings.app.database_path)
    storage.initialize()
    event = storage.store_jobs([_job()], "2026-07-22T08:00:00+08:00")[0]

    assert main(["check-application-profile", "-c", str(config_path)]) == 0
    summary_output = capsys.readouterr().out
    assert "confirmed" in summary_output
    assert "candidate@example.com" not in summary_output

    assert (
        main(
            [
                "apply",
                "-c",
                str(config_path),
                "--job-id",
                event.entity_key,
                "--prepare-only",
            ]
        )
        == 0
    )
    run_output = json.loads(capsys.readouterr().out)
    assert run_output["status"] == "created"
    assert run_output["job_id"] == event.entity_key
    assert "candidate@example.com" not in json.dumps(run_output)
