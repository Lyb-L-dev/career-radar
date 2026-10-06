"""Offline synthetic probe; no private configuration or network is read."""
import json
import sys
from importlib.metadata import version

import trafilatura
from bs4 import BeautifulSoup
from career_radar.discovery import _clean_visible_text, parse_html

body = "".join(
    f"<p>职责{i}：参与平台服务研发，负责需求分析、方案设计、开发测试及持续维护，与团队合作完成项目交付并保障系统质量。</p>"
    for i in range(12)
)
table = "<table><tr><th>岗位</th><th>专业要求</th></tr><tr><td>数据工程师</td><td>统计学硕士</td></tr></table>"
html = f"<html><body><article><h1>2026招聘公告</h1>{body}{table}</article></body></html>"
baseline = _clean_visible_text(BeautifulSoup(html, "html.parser"))
document = parse_html(html, "https://example.com/jobs/1")
with_tables = trafilatura.extract(html, include_comments=False, include_tables=True, favor_precision=True)
without_tables = trafilatura.extract(html, include_comments=False, include_tables=False, favor_precision=True)
jsonld_html = '<html><head><script type="application/ld+json">{"@type":"JobPosting","title":"算法工程师","description":"必须熟悉优化算法"}</script></head><body>招聘</body></html>'
result = {
    "python": sys.version.split()[0],
    "trafilatura": version("trafilatura"),
    "baseline_chars": len(baseline),
    "current_chars": len(document.text),
    "baseline_has_table_requirement": "统计学硕士" in baseline,
    "current_has_table_requirement": "统计学硕士" in document.text,
    "include_tables_true_has_requirement": bool(with_tables and "统计学硕士" in with_tables),
    "include_tables_false_has_requirement": bool(without_tables and "统计学硕士" in without_tables),
    "jsonld_only_title_retained": "算法工程师" in parse_html(jsonld_html, "https://example.com/jobs/2").text,
}
print(json.dumps(result, ensure_ascii=False, indent=2))
