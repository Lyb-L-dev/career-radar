"""Offline feasibility probes, not a full upstream/product integration test.

Upstream classes are loaded selectively via AST from an inspected pinned source;
top-level imports and application initialization are never executed.
Run from career-radar with .venv/Scripts/python.exe research/verify_monitoring_reuse.py.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "tmp/reuse-research/changedetection_processor.py"
SHA = "fd7c9db23e371803bf1892b827b03d9c9c946bcd"


def main() -> None:
    if not UPSTREAM.exists():
        raise SystemExit(
            "Missing inspected upstream source. Fetch changedetectionio/processors/"
            f"text_json_diff/processor.py at {SHA} into {UPSTREAM}, retaining its Apache-2.0 license."
        )
    tree = ast.parse(UPSTREAM.read_text(encoding="utf-8"))
    names = {"FilterConfig", "ContentTransformer"}
    selected = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in names]
    assert len(selected) == 2
    namespace = {"hashlib": hashlib, "json": json, "PRICE_DATA_TRACK_ACCEPT": "yes"}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(UPSTREAM), "exec"), namespace)
    filters = namespace["FilterConfig"]
    transformer = namespace["ContentTransformer"]
    store = SimpleNamespace(
        data={"settings": {"application": {}}},
        get_tag_overrides_for_watch=lambda **kwargs: [],
    )
    watch = {"uuid": "offline-probe", "include_filters": [".job"]}
    initial = filters(watch, store).get_filter_config_hash()
    assert initial == filters(dict(watch), store).get_filter_config_hash()
    store.data["settings"]["application"]["global_ignore_text"] = ["访问量"]
    changed = filters(watch, store).get_filter_config_hash()
    assert initial != changed

    # Full-page sorting hides a real reassignment between two jobs.
    first = "后端工程师\n要求 Python\n测试工程师\n要求 Java"
    second = "后端工程师\n要求 Java\n测试工程师\n要求 Python"
    assert first != second
    assert transformer.sort_alphabetically(first) == transformer.sort_alphabetically(second)
    # Global deduplication also loses repeated labels belonging to separate jobs.
    duplicate = "后端工程师\n任职要求\nPython\n测试工程师\n任职要求\nJava"
    assert transformer.remove_duplicate_lines(duplicate).count("任职要求") == 1

    # A scoped selector can suppress navigation noise without dropping JD table data.
    html = """<nav>访问量 100</nav><main class="job"><h1>后端开发</h1>
    <p>职责：服务端研发</p><table><tr><th>学历</th><td>本科</td></tr>
    <tr><th>截止日期</th><td>2026-10-01</td></tr></table></main>"""
    soup = BeautifulSoup(html, "html.parser")
    selected_text = soup.select_one(".job").get_text("\n", strip=True)
    assert all(value in selected_text for value in ("本科", "2026-10-01", "服务端研发"))
    assert "访问量" not in selected_text
    assert soup.select_one(".job-v2") is None
    results = {
        "upstream_commit": SHA,
        "upstream_source_sha256": hashlib.sha256(UPSTREAM.read_bytes()).hexdigest(),
        "scope": "AST-isolated upstream classes and a synthetic local HTML fixture only",
        "checks": {
            "stable_filter_hash": True,
            "global_filter_change_invalidates_hash": True,
            "sorting_can_hide_job_requirement_reassignment": True,
            "global_dedup_can_remove_per_job_labels": True,
            "scoped_selector_preserves_critical_table_values": True,
            "missing_selector_detectable": True,
        },
        "full_upstream_suite_run": False,
        "production_integration_run": False,
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
