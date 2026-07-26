"""申请工作流的 SQLite 持久化层。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..models import JobPosting
from ..storage import JobStorage
from .models import (
    ApplicationArtifact,
    ApplicationDraftBundle,
    ApplicationProfile,
    ApplicationReview,
    ApplicationRun,
    ApplicationStatus,
    CoverLetterDraft,
    JobFitEvaluation,
    ResumeDraft,
    validate_status_transition,
)


class ApplicationRepository:
    """保存申请任务状态和不可变的岗位/画像快照。"""

    def __init__(self, database_path: str | Path) -> None:
        self.storage = JobStorage(Path(database_path))

    def initialize(self) -> None:
        self.storage.initialize()

    def get_job_snapshot(self, job_id: str) -> tuple[str, JobPosting] | None:
        """读取岗位内容哈希与标准化原始载荷，避免使用前端展示摘要。"""

        with self.storage.transaction() as connection:
            row = connection.execute(
                "SELECT content_hash, payload_json FROM jobs WHERE entity_key = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return row["content_hash"], JobPosting.model_validate_json(row["payload_json"])

    def create_run(
        self,
        run: ApplicationRun,
        job: JobPosting,
        profile: ApplicationProfile,
        profile_source_path: str,
    ) -> ApplicationRun:
        """原子写入任务、岗位快照和私有画像快照。"""

        job_payload = json.dumps(job.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        profile_payload = json.dumps(
            profile.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
        )
        with self.storage.transaction() as connection:
            connection.execute(
                """
                INSERT INTO application_runs(
                    application_id, job_entity_key, job_content_hash, profile_hash,
                    status, failed_step, error, cover_letter_mode, resume_page_target,
                    job_snapshot_json, created_at, updated_at, approved_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.job_id,
                    run.job_content_hash,
                    run.profile_hash,
                    run.status.value,
                    None,
                    None,
                    run.cover_letter_mode,
                    run.resume_page_target,
                    job_payload,
                    run.created_at,
                    run.updated_at,
                    None,
                    None,
                ),
            )
            connection.execute(
                """
                INSERT INTO application_profile_snapshots(
                    application_id, profile_hash, payload_json, source_path, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.profile_hash,
                    profile_payload,
                    profile_source_path,
                    run.created_at,
                ),
            )
        return run

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> ApplicationRun:
        return ApplicationRun(
            id=row["application_id"],
            job_id=row["job_entity_key"],
            job_content_hash=row["job_content_hash"],
            profile_hash=row["profile_hash"],
            status=row["status"],
            failed_step=row["failed_step"],
            error=row["error"],
            cover_letter_mode=row["cover_letter_mode"],
            resume_page_target=row["resume_page_target"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approved_at=row["approved_at"],
            completed_at=row["completed_at"],
        )

    def get_run(self, application_id: str) -> ApplicationRun | None:
        with self.storage.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM application_runs WHERE application_id = ?",
                (application_id,),
            ).fetchone()
        return self._run_from_row(row) if row is not None else None

    def list_runs(self, *, job_id: str | None = None, limit: int = 100) -> list[ApplicationRun]:
        if not 1 <= limit <= 1000:
            raise ValueError("申请任务查询 limit 必须在 1 到 1000 之间")
        query = "SELECT * FROM application_runs"
        parameters: tuple[object, ...]
        if job_id:
            query += " WHERE job_entity_key = ?"
            parameters = (job_id, limit)
        else:
            parameters = (limit,)
        query += " ORDER BY created_at DESC LIMIT ?"
        with self.storage.transaction() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._run_from_row(row) for row in rows]

    def transition(
        self,
        application_id: str,
        target: ApplicationStatus,
        updated_at: str,
    ) -> ApplicationRun:
        """按状态图推进任务，禁止绕过用户批准和两次审稿。"""

        with self.storage.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM application_runs WHERE application_id = ?",
                (application_id,),
            ).fetchone()
            if row is None:
                raise ValueError("申请任务不存在")
            current = ApplicationStatus(row["status"])
            validate_status_transition(current, target)
            approved_at = updated_at if target == ApplicationStatus.DRAFTING else row["approved_at"]
            completed_at = (
                updated_at
                if target in {ApplicationStatus.READY, ApplicationStatus.REJECTED}
                else row["completed_at"]
            )
            connection.execute(
                """
                UPDATE application_runs
                SET status = ?, failed_step = NULL, error = NULL, updated_at = ?,
                    approved_at = ?, completed_at = ?
                WHERE application_id = ?
                """,
                (target.value, updated_at, approved_at, completed_at, application_id),
            )
        result = self.get_run(application_id)
        assert result is not None  # 已在同一方法验证存在
        return result

    def mark_failed(
        self,
        application_id: str,
        error: str,
        updated_at: str,
    ) -> ApplicationRun:
        """保存失败步骤，后续恢复时从该步骤重新执行。"""

        message = error.strip()
        if not message:
            raise ValueError("申请任务失败原因不能为空")
        with self.storage.transaction() as connection:
            row = connection.execute(
                "SELECT status FROM application_runs WHERE application_id = ?",
                (application_id,),
            ).fetchone()
            if row is None:
                raise ValueError("申请任务不存在")
            current = ApplicationStatus(row["status"])
            if current in {
                ApplicationStatus.CREATED,
                ApplicationStatus.WAITING_FOR_APPROVAL,
                ApplicationStatus.READY,
                ApplicationStatus.REJECTED,
                ApplicationStatus.FAILED,
            }:
                raise ValueError(f"申请任务当前状态 {current.value} 不能标记为执行失败")
            connection.execute(
                """
                UPDATE application_runs
                SET status = ?, failed_step = ?, error = ?, updated_at = ?
                WHERE application_id = ?
                """,
                (
                    ApplicationStatus.FAILED.value,
                    current.value,
                    message[:4000],
                    updated_at,
                    application_id,
                ),
            )
        result = self.get_run(application_id)
        assert result is not None
        return result

    def resume_failed(self, application_id: str, updated_at: str) -> ApplicationRun:
        """把失败任务恢复到原步骤；具体步骤必须以幂等方式重新执行。"""

        with self.storage.transaction() as connection:
            row = connection.execute(
                "SELECT status, failed_step FROM application_runs WHERE application_id = ?",
                (application_id,),
            ).fetchone()
            if row is None:
                raise ValueError("申请任务不存在")
            if row["status"] != ApplicationStatus.FAILED.value or not row["failed_step"]:
                raise ValueError("只有保存了失败步骤的申请任务才能恢复")
            connection.execute(
                """
                UPDATE application_runs
                SET status = ?, error = NULL, updated_at = ?
                WHERE application_id = ?
                """,
                (row["failed_step"], updated_at, application_id),
            )
        result = self.get_run(application_id)
        assert result is not None
        return result

    def get_profile_snapshot(self, application_id: str) -> ApplicationProfile | None:
        """仅供申请生成内部使用，调用方不得把完整画像返回给 Web。"""

        with self.storage.transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM application_profile_snapshots WHERE application_id = ?",
                (application_id,),
            ).fetchone()
        if row is None:
            return None
        return ApplicationProfile.model_validate_json(row["payload_json"])

    def get_run_job_snapshot(self, application_id: str) -> JobPosting | None:
        """读取创建任务时冻结的 JD，而不是之后可能更新的岗位记录。"""

        with self.storage.transaction() as connection:
            row = connection.execute(
                "SELECT job_snapshot_json FROM application_runs WHERE application_id = ?",
                (application_id,),
            ).fetchone()
        if row is None:
            return None
        return JobPosting.model_validate_json(row["job_snapshot_json"])

    def save_evaluation(
        self,
        application_id: str,
        evaluation: JobFitEvaluation,
        prompt_version: str,
        created_at: str,
    ) -> None:
        payload = json.dumps(evaluation.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        with self.storage.transaction() as connection:
            connection.execute(
                """
                INSERT INTO application_evaluations(
                    application_id, prompt_version, payload_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (application_id, prompt_version, payload, created_at),
            )

    def get_evaluation(self, application_id: str) -> JobFitEvaluation | None:
        with self.storage.transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM application_evaluations WHERE application_id = ?",
                (application_id,),
            ).fetchone()
        if row is None:
            return None
        return JobFitEvaluation.model_validate_json(row["payload_json"])

    def save_draft_bundle(
        self,
        application_id: str,
        bundle: ApplicationDraftBundle,
        version: int,
        created_at: str,
    ) -> None:
        """原子保存同一版本的简历与可选求职信，避免断点处出现半份草稿。"""

        rows: list[tuple[str, str]] = [
            (
                "resume",
                json.dumps(bundle.resume.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            )
        ]
        if bundle.cover_letter is not None:
            rows.append(
                (
                    "cover_letter",
                    json.dumps(
                        bundle.cover_letter.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
        with self.storage.transaction() as connection:
            connection.executemany(
                """
                INSERT INTO application_drafts(
                    application_id, document_kind, version, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (application_id, document_kind, version, payload, created_at)
                    for document_kind, payload in rows
                ],
            )

    def get_draft_bundle(
        self,
        application_id: str,
        version: int,
    ) -> ApplicationDraftBundle | None:
        with self.storage.transaction() as connection:
            rows = connection.execute(
                """
                SELECT document_kind, payload_json FROM application_drafts
                WHERE application_id = ? AND version = ?
                """,
                (application_id, version),
            ).fetchall()
        payloads = {row["document_kind"]: row["payload_json"] for row in rows}
        if "resume" not in payloads:
            return None
        cover_letter = (
            CoverLetterDraft.model_validate_json(payloads["cover_letter"])
            if "cover_letter" in payloads
            else None
        )
        return ApplicationDraftBundle(
            resume=ResumeDraft.model_validate_json(payloads["resume"]),
            cover_letter=cover_letter,
        )

    def save_review(
        self,
        application_id: str,
        review: ApplicationReview,
        version: int,
        created_at: str,
    ) -> None:
        payload = json.dumps(review.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        with self.storage.transaction() as connection:
            connection.execute(
                """
                INSERT INTO application_reviews(
                    application_id, reviewer, version, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (application_id, review.reviewer, version, payload, created_at),
            )

    def get_review(
        self,
        application_id: str,
        reviewer: str,
        version: int,
    ) -> ApplicationReview | None:
        with self.storage.transaction() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM application_reviews
                WHERE application_id = ? AND reviewer = ? AND version = ?
                """,
                (application_id, reviewer, version),
            ).fetchone()
        if row is None:
            return None
        return ApplicationReview.model_validate_json(row["payload_json"])

    def save_artifact(self, artifact: ApplicationArtifact) -> None:
        """按稳定 artifact_id 幂等登记文件；重试后用最新哈希和路径覆盖。"""

        with self.storage.transaction() as connection:
            connection.execute(
                """
                INSERT INTO application_artifacts(
                    artifact_id, application_id, kind, path, sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    path = excluded.path,
                    sha256 = excluded.sha256,
                    created_at = excluded.created_at
                """,
                (
                    artifact.id,
                    artifact.application_id,
                    artifact.kind,
                    artifact.path,
                    artifact.sha256,
                    artifact.created_at,
                ),
            )

    def list_artifacts(self, application_id: str) -> list[ApplicationArtifact]:
        with self.storage.transaction() as connection:
            rows = connection.execute(
                """
                SELECT * FROM application_artifacts
                WHERE application_id = ? ORDER BY created_at, kind
                """,
                (application_id,),
            ).fetchall()
        return [
            ApplicationArtifact(
                id=row["artifact_id"],
                application_id=row["application_id"],
                kind=row["kind"],
                path=row["path"],
                sha256=row["sha256"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def delete_artifact(self, application_id: str, kind: str) -> None:
        """删除已不再存在的生成物登记，不删除磁盘文件。"""

        with self.storage.transaction() as connection:
            connection.execute(
                "DELETE FROM application_artifacts WHERE application_id = ? AND kind = ?",
                (application_id, kind),
            )
