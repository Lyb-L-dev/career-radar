"""只读核对真实官网岗位资格、AI 缓存版本与原文证据，不调用模型。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter

from career_radar.config import load_settings
from career_radar.models import JobPosting
from career_radar.official_screening import candidate_snapshot
from career_radar.official_screening_service import assessment_view


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    settings = load_settings(args.config)
    conn = sqlite3.connect(settings.app.database_path.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT entity_key,payload_json FROM jobs").fetchall()
        cached = {r["entity_key"]: dict(r) for r in conn.execute("SELECT * FROM official_job_assessments")}
    finally:
        conn.close()
    allowed = set(candidate_snapshot(settings.candidate)["allowed_evidence_quotes"])
    qualifications = Counter()
    assessments = Counter()
    priority = Counter()
    required_status = Counter()
    invalid_evidence = 0
    missing_ids = []
    for row in rows:
        job = JobPosting.model_validate_json(row["payload_json"])
        view = assessment_view(job, settings.candidate, settings.llm.model, cached.get(row["entity_key"]))
        verdict = view["eligibility"]["verdict"]
        ai = view["aiAssessment"]
        qualifications[verdict] += 1
        assessments[ai["status"]] += 1
        priority[view["priority"]["tier"]] += 1
        if job.record_type == "job" and job.jd_complete and verdict != "ineligible":
            required_status[ai["status"]] += 1
            if ai["status"] != "current":
                missing_ids.append(row["entity_key"])
        fit = ai["result"]
        if fit:
            text = f"{job.title}\n{job.recruitment_type or ''}\n{job.description}\n{job.requirements or ''}"
            invalid_evidence += sum(m["job_quote"] not in text or m["candidate_quote"] not in allowed for m in fit["matches"])
            invalid_evidence += sum(g["job_quote"] not in text for g in fit["gaps"])
    print(json.dumps({
        "total": len(rows), "provider": settings.llm.provider, "model": settings.llm.model,
        "qualification": dict(qualifications), "assessment": dict(assessments),
        "priority": dict(priority), "required_assessment": dict(required_status),
        "invalid_evidence": invalid_evidence, "missing_assessment_ids": missing_ids,
        "unconfirmed_profile_fields": [name for name in ("student_status", "graduation_month", "formal_work_years", "education_mode") if getattr(settings.candidate, name) in (None, "", "unknown")],
    }, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
