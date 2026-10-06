"""Versioned SQLite schema for the growth loop."""

import sqlite3


def create_growth_schema(connection: sqlite3.Connection) -> None:
    # Individual statements preserve the caller's migration transaction.
    statements = [
        "CREATE TABLE IF NOT EXISTS growth_targets (id TEXT PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(source, source_id))",
        "CREATE TABLE IF NOT EXISTS growth_skills (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS growth_sessions (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS growth_evidence (id TEXT PRIMARY KEY, skill_id TEXT NOT NULL, session_id TEXT, question_id TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(session_id, question_id))",
        "CREATE INDEX IF NOT EXISTS idx_growth_evidence_skill ON growth_evidence(skill_id, created_at)",
        "CREATE TABLE IF NOT EXISTS growth_plans (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS growth_operations (id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS growth_settings (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)",
    ]
    for statement in statements:
        connection.execute(statement)
