from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from career_radar.platform_leads import BossLead, BossLeadRepository
from scripts.repair_boss_legacy_ids import repair


def test_repair_keeps_manual_state_and_writes_backup(tmp_path: Path) -> None:
    link = "https://www.zhipin.com/job_detail/real-123.html"
    surrogate = hashlib.md5(link.encode()).hexdigest()[:16]
    legacy = BossLead(
        external_id=surrogate,
        title="AI 应用开发工程师",
        company="示例企业",
        location="杭州",
        salary="",
        tags="本科",
        description="",
        source_url=f"https://www.zhipin.com/job_detail/{surrogate}.html",
    )
    database = tmp_path / "jobs.db"
    repo = BossLeadRepository(database)
    repo.initialize()
    repo.import_leads([legacy])
    assert repo.set_state(legacy.id, "favorite", True)
    mapping = {surrogate: ("real-123", link)}
    assert repair(database, mapping, None) == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT external_id FROM platform_job_leads").fetchone()[0] == surrogate
    backup = tmp_path / "before.db"
    assert repair(database, mapping, backup) == 1
    corrected = BossLead(
        external_id="real-123", title=legacy.title, company=legacy.company,
        location=legacy.location, salary="", tags="本科", description="", source_url=link,
    )
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT id, external_id, is_favorite FROM platform_job_leads"
        ).fetchone()
    assert row == (corrected.id, "real-123", 1)
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT external_id FROM platform_job_leads").fetchone()[0] == surrogate
