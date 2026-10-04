"""One-off repair for BOSS exports whose job_id is a local MD5 surrogate.

Dry-run by default. Pass --apply and --backup to migrate an offline database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path
from urllib.parse import urlsplit

from career_radar.platform_leads import BossLead

_BOSS_PATH = re.compile(r"^/job_detail/([A-Za-z0-9_-]{1,128})\.html$")
_SURROGATE = re.compile(r"^[0-9a-f]{16}$")


def load_mapping(paths: list[Path]) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("jobs", []):
            link = str(row.get("job_link") or "")
            parsed = urlsplit(link)
            match = _BOSS_PATH.fullmatch(parsed.path)
            if parsed.scheme != "https" or parsed.hostname not in {"zhipin.com", "www.zhipin.com"} or not match:
                continue
            surrogate = hashlib.md5(link.encode("utf-8")).hexdigest()[:16]
            candidate = (match.group(1), f"https://www.zhipin.com{parsed.path}")
            if surrogate in mapping and mapping[surrogate] != candidate:
                raise ValueError("旧 ID 映射发生冲突，已停止")
            mapping[surrogate] = candidate
    return mapping


def repair(database: Path, mapping: dict[str, tuple[str, str]], backup: Path | None) -> int:
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT id, external_id, payload_json FROM platform_job_leads WHERE source = 'boss'"
        ).fetchall()
        legacy = [row for row in rows if _SURROGATE.fullmatch(row[1])]
        missing = [row[1] for row in legacy if row[1] not in mapping]
        if missing:
            raise ValueError(f"旧 ID 映射不全（缺 {len(missing)} 条），未修改数据库")
        changes = []
        existing_ids = {row[0] for row in rows}
        for old_id, surrogate, payload_json in legacy:
            true_id, url = mapping[surrogate]
            lead = BossLead(**json.loads(payload_json))
            if lead.source_url != f"https://www.zhipin.com/job_detail/{surrogate}.html":
                raise ValueError("旧职位链接不符合预期，未修改数据库")
            corrected = replace(lead, external_id=true_id, source_url=url)
            if corrected.id in existing_ids or any(item[0] == corrected.id for item in changes):
                raise ValueError("修复后的 ID 与已有记录冲突，未修改数据库")
            changes.append((corrected.id, true_id, json.dumps(asdict(corrected), ensure_ascii=False), old_id))
        if backup is None:
            print(f"dry-run: 将修复 {len(changes)} 条；未修改数据库")
            return len(changes)
        backup.parent.mkdir(parents=True, exist_ok=True)
        if backup.exists():
            raise FileExistsError("备份文件已存在，未修改数据库")
        with sqlite3.connect(backup) as target:
            connection.backup(target)
        with connection:
            connection.executemany(
                "UPDATE platform_job_leads SET id = ?, external_id = ?, payload_json = ? WHERE id = ?",
                changes,
            )
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("数据库完整性检查失败，请使用备份恢复")
        print(f"已修复 {len(changes)} 条；备份：{backup}")
        return len(changes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("lists", nargs="+", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if args.apply and args.backup is None:
        parser.error("--apply 必须提供 --backup")
    repair(args.database, load_mapping(args.lists), args.backup if args.apply else None)


if __name__ == "__main__":
    main()
