"""SQLite 初始化、职位去重、变化检测和历史记录。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from .job_merge import (
    is_same_job,
    job_urls,
    normalized,
    preserve_richer_previous_content,
)
from .models import JobPosting, StoredJobEvent

SCHEMA_VERSION = 8


def _normalized(value: str | None) -> str:
    """用于哈希的轻量规范化，不修改最终展示的 JD 原文。"""

    return normalized(value)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def compute_job_hashes(job: JobPosting) -> tuple[str, str, str, str]:
    """返回实体键、需求指定指纹、JD 前缀哈希和全内容哈希。

    ``fingerprint`` 严格包含“公司 + 职位名称 + 发布日期 + JD 前 100 字哈希”；
    ``content_hash`` 再覆盖所有字段，用于发现前 100 字未变化但正文更新的情况。
    独立 ``entity_key`` 则避免 JD 一改就被误判成全新的岗位。
    """

    jd_prefix_hash = _sha256(_normalized(job.description)[:100])
    fingerprint = _sha256(
        "|".join(
            (
                _normalized(job.company),
                _normalized(job.title),
                _normalized(job.published_at),
                jd_prefix_hash,
            )
        )
    )
    # 同一列表页可能包含多个同名岗位；把详情和申请 URL 都纳入新记录的键，
    # 后续 URL 漂移由 store_jobs 的身份证据匹配与状态迁移安全处理。
    identity_urls = "|".join(sorted(job_urls(job)))
    # 有稳定详情来源时不把地点放入实体键。LLM 可能把“上海”“上海徐汇”轮流
    # 输出，若地点参与主键会把同一个岗位误判为多个新岗位。
    identity_location = "" if identity_urls else _normalized(job.location)
    entity_key = _sha256(
        "|".join(
            (
                job.record_type,
                _normalized(job.company),
                _normalized(job.title),
                identity_urls,
                identity_location,
            )
        )
    )
    content_json = json.dumps(job.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    content_hash = _sha256(content_json)
    return entity_key, fingerprint, jd_prefix_hash, content_hash


class JobStorage:
    """轻量 SQLite 仓库；每个实例按操作短暂打开连接，适合每日定时任务。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """提交或回滚后显式关闭连接，避免 Windows 持续占用数据库文件。"""

        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        """幂等创建表；未来升级可依据 ``PRAGMA user_version`` 增加迁移。"""

        with self.transaction() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"数据库版本 {version} 高于程序支持版本 {SCHEMA_VERSION}，请升级程序"
                )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    entity_key TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    jd_prefix_hash TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    published_at TEXT,
                    match_level TEXT NOT NULL,
                    apply_url TEXT,
                    source_url TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_company_title
                    ON jobs(company, title);
                CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint
                    ON jobs(fingerprint);

                CREATE TABLE IF NOT EXISTS job_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_key TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK(event_type IN ('new', 'updated')),
                    fingerprint TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    FOREIGN KEY(entity_key) REFERENCES jobs(entity_key)
                );
                CREATE INDEX IF NOT EXISTS idx_history_detected_at
                    ON job_history(detected_at);

                CREATE TABLE IF NOT EXISTS web_job_state (
                    entity_key TEXT PRIMARY KEY,
                    is_favorite INTEGER NOT NULL DEFAULT 0,
                    is_applied INTEGER NOT NULL DEFAULT 0,
                    not_interested INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(entity_key) REFERENCES jobs(entity_key) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS web_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_web_runs_started_at
                    ON web_runs(started_at DESC);

                CREATE TABLE IF NOT EXISTS web_notification_state (
                    notification_id TEXT PRIMARY KEY,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    is_dismissed INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS web_page_visits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    requested_url TEXT NOT NULL,
                    final_url TEXT NOT NULL,
                    page_type TEXT,
                    method TEXT NOT NULL,
                    http_status INTEGER,
                    content_length INTEGER NOT NULL DEFAULT 0,
                    llm_extracted INTEGER NOT NULL DEFAULT 0,
                    jobs_found INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    error TEXT,
                    fetched_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_web_page_visits_company_time
                    ON web_page_visits(company_id, fetched_at DESC);
                CREATE INDEX IF NOT EXISTS idx_web_page_visits_run
                    ON web_page_visits(run_id, id);

                CREATE TABLE IF NOT EXISTS company_candidate_state (
                    candidate_id TEXT PRIMARY KEY,
                    decision TEXT NOT NULL DEFAULT 'pending'
                        CHECK(decision IN ('pending', 'shortlisted', 'rejected')),
                    official_website TEXT,
                    careers_url TEXT,
                    company_type TEXT,
                    industry_category TEXT,
                    recruitment_channel_status TEXT NOT NULL DEFAULT 'official_site_pending',
                    parent_company TEXT,
                    group_recruitment_url TEXT,
                    attribution_keywords_json TEXT,
                    note TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_company_candidate_state_decision
                    ON company_candidate_state(decision, updated_at DESC);

                CREATE TABLE IF NOT EXISTS company_recruitment_sources (
                    source_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    source_kind TEXT NOT NULL CHECK(source_kind IN (
                        'official_homepage', 'official_careers', 'group_recruitment',
                        'government_notice', 'official_account', 'official_document',
                        'official_email', 'third_party_lead'
                    )),
                    verification_status TEXT NOT NULL CHECK(verification_status IN (
                        'verified_official', 'pending', 'rejected'
                    )),
                    material_type TEXT NOT NULL CHECK(material_type IN (
                        'webpage', 'pdf', 'image', 'text', 'email'
                    )),
                    title TEXT NOT NULL,
                    source_url TEXT,
                    content TEXT,
                    published_at TEXT,
                    parent_company TEXT,
                    imported_job_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_company_recruitment_sources_candidate
                    ON company_recruitment_sources(candidate_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_company_recruitment_sources_verification
                    ON company_recruitment_sources(verification_status, created_at DESC);

                CREATE TABLE IF NOT EXISTS company_wechat_accounts (
                    account_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    account_name TEXT NOT NULL,
                    account_identifier TEXT,
                    biz_id TEXT,
                    scope TEXT NOT NULL CHECK(scope IN ('company', 'group')),
                    parent_company TEXT,
                    attribution_keywords_json TEXT NOT NULL,
                    verification_status TEXT NOT NULL CHECK(verification_status IN (
                        'verified', 'pending', 'rejected'
                    )),
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(candidate_id, account_name)
                );
                CREATE INDEX IF NOT EXISTS idx_company_wechat_accounts_candidate
                    ON company_wechat_accounts(candidate_id, enabled, updated_at DESC);

                CREATE TABLE IF NOT EXISTS wechat_recruitment_scans (
                    scan_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN (
                        'pending', 'running', 'completed', 'partial', 'failed',
                        'interrupted'
                    )),
                    payload_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_wechat_recruitment_scans_candidate
                    ON wechat_recruitment_scans(candidate_id, started_at DESC);

                CREATE TABLE IF NOT EXISTS wechat_recruitment_articles (
                    article_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    account_id TEXT,
                    title TEXT NOT NULL,
                    account_name TEXT,
                    account_identifier TEXT,
                    biz_id TEXT,
                    source_url TEXT NOT NULL,
                    summary TEXT,
                    content TEXT NOT NULL,
                    published_at TEXT,
                    classification TEXT NOT NULL CHECK(classification IN (
                        'official_recruitment', 'third_party_lead', 'non_recruitment'
                    )),
                    verification_status TEXT NOT NULL CHECK(verification_status IN (
                        'verified_official', 'pending', 'rejected'
                    )),
                    reason TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    source_id TEXT,
                    imported_job_id TEXT,
                    first_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(candidate_id, source_url),
                    FOREIGN KEY(account_id) REFERENCES company_wechat_accounts(account_id)
                        ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_wechat_recruitment_articles_candidate
                    ON wechat_recruitment_articles(candidate_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_wechat_recruitment_articles_classification
                    ON wechat_recruitment_articles(classification, updated_at DESC);

                CREATE TABLE IF NOT EXISTS job_reputation_scans (
                    scan_id TEXT PRIMARY KEY,
                    entity_key TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK(status IN ('pending', 'running', 'completed', 'partial', 'failed', 'interrupted')),
                    payload_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    finished_at TEXT,
                    FOREIGN KEY(entity_key) REFERENCES jobs(entity_key) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_job_reputation_scans_job_time
                    ON job_reputation_scans(entity_key, started_at DESC);

                CREATE TABLE IF NOT EXISTS job_reputation_evidence (
                    scan_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    title TEXT NOT NULL,
                    excerpt TEXT NOT NULL,
                    source_url TEXT,
                    published_at TEXT,
                    interaction_count INTEGER NOT NULL DEFAULT 0,
                    search_query TEXT NOT NULL,
                    PRIMARY KEY(scan_id, evidence_id),
                    FOREIGN KEY(scan_id) REFERENCES job_reputation_scans(scan_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_job_reputation_evidence_platform
                    ON job_reputation_evidence(platform, scan_id);

                CREATE TABLE IF NOT EXISTS application_runs (
                    application_id TEXT PRIMARY KEY,
                    job_entity_key TEXT NOT NULL,
                    job_content_hash TEXT NOT NULL,
                    profile_hash TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN (
                        'created', 'evaluating', 'waiting_for_approval', 'drafting',
                        'factual_review', 'recruiter_review', 'revising', 'rendering',
                        'verifying', 'ready', 'rejected', 'failed'
                    )),
                    failed_step TEXT,
                    error TEXT,
                    cover_letter_mode TEXT NOT NULL
                        CHECK(cover_letter_mode IN ('auto', 'always', 'never')),
                    resume_page_target INTEGER NOT NULL
                        CHECK(resume_page_target BETWEEN 1 AND 3),
                    job_snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_at TEXT,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_application_runs_job_time
                    ON application_runs(job_entity_key, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_application_runs_status_time
                    ON application_runs(status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS application_profile_snapshots (
                    application_id TEXT PRIMARY KEY,
                    profile_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(application_id) REFERENCES application_runs(application_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS application_evaluations (
                    application_id TEXT PRIMARY KEY,
                    prompt_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(application_id) REFERENCES application_runs(application_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS application_drafts (
                    application_id TEXT NOT NULL,
                    document_kind TEXT NOT NULL CHECK(document_kind IN ('resume', 'cover_letter')),
                    version INTEGER NOT NULL CHECK(version >= 1),
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(application_id, document_kind, version),
                    FOREIGN KEY(application_id) REFERENCES application_runs(application_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS application_reviews (
                    application_id TEXT NOT NULL,
                    reviewer TEXT NOT NULL CHECK(reviewer IN ('factual', 'recruiter_ats')),
                    version INTEGER NOT NULL CHECK(version >= 1),
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(application_id, reviewer, version),
                    FOREIGN KEY(application_id) REFERENCES application_runs(application_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS application_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    application_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(application_id) REFERENCES application_runs(application_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_application_artifacts_run
                    ON application_artifacts(application_id, created_at DESC);
                """
            )
            candidate_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(company_candidate_state)"
                ).fetchall()
            }
            candidate_migrations = {
                "recruitment_channel_status": (
                    "TEXT NOT NULL DEFAULT 'official_site_pending'"
                ),
                "parent_company": "TEXT",
                "group_recruitment_url": "TEXT",
                "attribution_keywords_json": "TEXT",
            }
            for column, declaration in candidate_migrations.items():
                if column not in candidate_columns:
                    connection.execute(
                        f"ALTER TABLE company_candidate_state "
                        f"ADD COLUMN {column} {declaration}"
                    )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _identity_matches(
        self,
        connection: sqlite3.Connection,
        job: JobPosting,
    ) -> list[tuple[sqlite3.Row, JobPosting]]:
        """只加载同公司同名候选，再用共享身份规则做内存判定。"""

        rows = connection.execute(
            """
            SELECT entity_key, content_hash, payload_json, first_seen_at
            FROM jobs WHERE company = ? AND title = ?
            ORDER BY first_seen_at ASC
            """,
            (job.company, job.title),
        ).fetchall()
        matches: list[tuple[sqlite3.Row, JobPosting]] = []
        for row in rows:
            previous = JobPosting.model_validate_json(row["payload_json"])
            if is_same_job(
                job,
                previous,
                allow_missing_location=True,
                require_shared_url=True,
            ):
                matches.append((row, previous))
        return matches

    def _merge_duplicate_state(
        self,
        connection: sqlite3.Connection,
        canonical_key: str,
        duplicate_key: str,
        updated_at: str,
    ) -> None:
        """把旧重复记录的用户状态、历史和口碑任务迁移到保留主键。"""

        rows = connection.execute(
            """
            SELECT entity_key, is_favorite, is_applied, not_interested
            FROM web_job_state WHERE entity_key IN (?, ?)
            """,
            (canonical_key, duplicate_key),
        ).fetchall()
        if rows:
            favorite = max(row["is_favorite"] for row in rows)
            applied = max(row["is_applied"] for row in rows)
            not_interested = max(row["not_interested"] for row in rows)
            connection.execute(
                """
                INSERT INTO web_job_state(
                    entity_key, is_favorite, is_applied, not_interested, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(entity_key) DO UPDATE SET
                    is_favorite = excluded.is_favorite,
                    is_applied = excluded.is_applied,
                    not_interested = excluded.not_interested,
                    updated_at = excluded.updated_at
                """,
                (canonical_key, favorite, applied, not_interested, updated_at),
            )
        connection.execute(
            "UPDATE job_history SET entity_key = ? WHERE entity_key = ?",
            (canonical_key, duplicate_key),
        )
        connection.execute(
            "UPDATE job_reputation_scans SET entity_key = ? WHERE entity_key = ?",
            (canonical_key, duplicate_key),
        )
        connection.execute(
            "DELETE FROM web_job_state WHERE entity_key = ?",
            (duplicate_key,),
        )
        connection.execute("DELETE FROM jobs WHERE entity_key = ?", (duplicate_key,))

    def _resolve_identity(
        self,
        connection: sqlite3.Connection,
        incoming: JobPosting,
        detected_at: str,
    ) -> tuple[str, JobPosting]:
        """决定本次写入使用的稳定主键，并合并历史重复记录。"""

        proposed_key = compute_job_hashes(incoming)[0]
        matches = self._identity_matches(connection, incoming)
        if not matches:
            return proposed_key, incoming

        canonical_row = matches[0][0]
        canonical_key = canonical_row["entity_key"]
        richest_previous = max(
            (previous for _row, previous in matches),
            key=lambda item: len(item.description) + len(item.requirements or ""),
        )
        job = preserve_richer_previous_content(incoming, richest_previous)
        for row, _previous in matches[1:]:
            duplicate_key = row["entity_key"]
            if duplicate_key != canonical_key:
                self._merge_duplicate_state(
                    connection,
                    canonical_key,
                    duplicate_key,
                    detected_at,
                )
        return canonical_key, job

    def _write_job(
        self,
        connection: sqlite3.Connection,
        entity_key: str,
        job: JobPosting,
        detected_at: str,
    ) -> StoredJobEvent:
        """写入单个已完成身份解析的岗位，并生成 new/updated/unchanged 事件。"""

        _computed_key, fingerprint, prefix_hash, content_hash = compute_job_hashes(job)
        payload = json.dumps(job.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        existing = connection.execute(
            "SELECT content_hash FROM jobs WHERE entity_key = ?", (entity_key,)
        ).fetchone()
        if existing is None:
            event_type = "new"
            connection.execute(
                """
                INSERT INTO jobs (
                    entity_key, fingerprint, jd_prefix_hash, content_hash,
                    company, title, published_at, match_level, apply_url,
                    source_url, payload_json, first_seen_at, last_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_key,
                    fingerprint,
                    prefix_hash,
                    content_hash,
                    job.company,
                    job.title,
                    job.published_at,
                    job.match_level.value,
                    job.apply_url,
                    job.source_url,
                    payload,
                    detected_at,
                    detected_at,
                    detected_at,
                ),
            )
        elif existing["content_hash"] != content_hash:
            event_type = "updated"
            connection.execute(
                """
                UPDATE jobs SET
                    fingerprint = ?, jd_prefix_hash = ?, content_hash = ?,
                    company = ?, title = ?, published_at = ?, match_level = ?,
                    apply_url = ?, source_url = ?, payload_json = ?,
                    last_seen_at = ?, updated_at = ?
                WHERE entity_key = ?
                """,
                (
                    fingerprint,
                    prefix_hash,
                    content_hash,
                    job.company,
                    job.title,
                    job.published_at,
                    job.match_level.value,
                    job.apply_url,
                    job.source_url,
                    payload,
                    detected_at,
                    detected_at,
                    entity_key,
                ),
            )
        else:
            event_type = "unchanged"
            connection.execute(
                "UPDATE jobs SET last_seen_at = ? WHERE entity_key = ?",
                (detected_at, entity_key),
            )

        if event_type != "unchanged":
            connection.execute(
                """
                INSERT INTO job_history (
                    entity_key, event_type, fingerprint, content_hash,
                    payload_json, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (entity_key, event_type, fingerprint, content_hash, payload, detected_at),
            )
        return StoredJobEvent(
            event_type=event_type,
            job=job,
            entity_key=entity_key,
            fingerprint=fingerprint,
            detected_at=detected_at,
        )

    def store_jobs(
        self,
        jobs: Iterable[JobPosting],
        detected_at: str,
    ) -> list[StoredJobEvent]:
        """原子写入一批职位，并为新增/变化生成事件。"""

        incoming_jobs = list(jobs)
        events: list[StoredJobEvent] = []
        with self.transaction() as connection:
            for incoming in incoming_jobs:
                entity_key, job = self._resolve_identity(
                    connection,
                    incoming,
                    detected_at,
                )
                events.append(self._write_job(connection, entity_key, job, detected_at))
        return events

    def load_all_jobs(self) -> list[JobPosting]:
        """读取当前最新版职位，可用于手工导出或后续做 Web UI。"""

        self.initialize()
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM jobs ORDER BY company, title"
            ).fetchall()
        return [JobPosting.model_validate_json(row["payload_json"]) for row in rows]
