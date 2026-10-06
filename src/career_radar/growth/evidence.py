"""Deterministic levels and spaced review, derived from auditable evidence."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

INTERVALS = [1, 3, 7, 14, 30]
ZONE = ZoneInfo("Asia/Shanghai")
NON_RESULT = re.compile(r"未(?:实际)?运行|未执行|未测试|未实跑|尚未|没有(?:测试|运行)|暂无|预期|预计|计划|not\s+(?:run|tested|executed)", re.I)


def submitted_run_result(record):
    """A missing or expressly hypothetical record is not a submitted result."""
    return bool(record and record.strip() and not NON_RESULT.search(record))


def local_date(timestamp):
    return datetime.fromisoformat(timestamp).astimezone(ZONE).date()


def skill_state(skill, evidence, today, not_learned=None):
    points = {point["id"]: {**point, "status": "unassessed", "evidenceId": None} for point in skill["points"]}
    dimensions = set()
    level = highest = streak = 0
    last_recall = next_review = last_day = last_hash = None
    project_ids = set()
    reviewed_implementations = set()
    proof_ids = []
    history = sorted(evidence, key=lambda item: item["createdAt"])
    for item in history:
        if item.get("rubricVersion") != skill["rubricVersion"]:
            continue
        if item["type"] == "project":
            has_record = item.get("hasRunRecord", submitted_run_result(item.get("runRecord", "")))
            if item.get("code") and has_record and item.get("passed"):
                project_ids.add(item["id"])
                proof_ids.append(item["id"])
            continue
        if item.get("skipped"):
            continue
        assisted = item.get("assisted", False)
        for result in item.get("points", []):
            if result["pointId"] in points:
                if assisted and points[result["pointId"]]["status"] == "independent":
                    continue  # Practice never replaces an existing independent proof.
                points[result["pointId"]].update(
                    status="independent" if result["passed"] and not assisted else "needs_hint",
                    evidenceId=item["id"],
                )
        if item.get("passed") and not assisted:
            dimensions.add(item["mode"])
            proof_ids.append(item["id"])
            if item.get("projectId") in project_ids and item["mode"] == "implementation":
                reviewed_implementations.add(item["projectId"])
        if item["type"] == "recall" and not assisted:
            day = local_date(item["createdAt"])
            last_recall = day.isoformat()
            if not item.get("passed"):
                streak = 0
                last_day = day
                last_hash = item.get("questionHash")
                next_review = (day + timedelta(days=1)).isoformat()
            elif last_day != day and last_hash != item.get("questionHash"):
                streak += 1
                last_day = day
                last_hash = item.get("questionHash")
                next_review = (day + timedelta(days=INTERVALS[min(streak - 1, 4)])).isoformat()
        elif item["type"] == "recall" and assisted and not next_review:
            next_review = (local_date(item["createdAt"]) + timedelta(days=1)).isoformat()
        independent_count = sum(point["status"] == "independent" for point in points.values())
        level = 1 if independent_count else 0
        if independent_count == len(points) and dimensions & {"explain", "apply", "code", "implementation", "transfer"}:
            level = 2
            if {"apply", "code"} <= dimensions and streak >= 2:
                level = 3
                if reviewed_implementations:
                    level = 4
                    if "transfer" in dimensions:
                        level = 5
        highest = max(highest, level)
    for point_id, marked_at in (not_learned or {}).items():
        if point_id not in points:
            continue
        last_evidence = next((item for item in reversed(history) if item["type"] != "project" and any(p["pointId"] == point_id for p in item.get("points", []))), None)
        if last_evidence is None or last_evidence["createdAt"] < marked_at:
            points[point_id]["status"] = "not_learned"
    assessed = any(point["status"] in {"independent", "needs_hint"} for point in points.values())
    return {
        "level": level, "highestLevel": highest, "points": list(points.values()),
        "status": "needs_practice" if any(p["status"] == "needs_hint" for p in points.values()) else "mastered" if level >= 2 else "developing" if assessed else "unverified",
        "lastRecall": last_recall, "streak": streak, "nextReview": next_review,
        "reviewDue": bool(next_review and next_review <= today.isoformat()),
        "proofIds": proof_ids, "evidenceCount": len(history),
    }
