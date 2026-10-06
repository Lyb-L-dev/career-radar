"""Verify the career-to-growth flow with isolated data, fake models and axe."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import uvicorn
from playwright.sync_api import expect, sync_playwright

from career_radar.api import create_app
from career_radar.config import load_settings
from career_radar.growth.evidence import ZONE
from career_radar.models import JobPosting, MatchLevel
from career_radar.platform_leads import BossLeadRepository, parse_boss_export
from career_radar.storage import JobStorage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_growth import FakeGateway  # noqa: E402


def audit(page, reports, name):
    # Audit the settled interface, not a frame halfway through opening a dialog.
    page.evaluate("""async () => {
      await Promise.allSettled(document.getAnimations()
        .filter(animation => Number.isFinite(animation.effect?.getComputedTiming().endTime))
        .map(animation => animation.finished));
    }""")
    if not page.evaluate("typeof window.axe !== 'undefined'"):
        page.add_script_tag(path=str(ROOT / "web/node_modules/axe-core/axe.min.js"))
    result = page.evaluate("""async () => {
      const result = await axe.run(document, {runOnly: {type: 'tag', values:
        ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}});
      return result.violations.map(v => ({id:v.id, impact:v.impact,
        nodes:v.nodes.map(n => ({target:n.target, html:n.html, reason:n.failureSummary}))}));
    }""")
    reports.append({"page": name, "violations": result, "overflow": page.evaluate("document.documentElement.scrollWidth > innerWidth"), "mainHeadings": page.locator("main h1").count()})


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    metrics = {}
    with tempfile.TemporaryDirectory(prefix="career-frontend-") as directory:
        config = Path(directory) / "config.yaml"
        config.write_text("""app:
  database_path: data/test.db
crawler:
  render_mode: never
  user_agent: Career Radar isolated frontend verification
llm:
  provider: mimo
  model: offline-fixture
smtp:
  enabled: false
companies:
  - name: 离线验证企业
    url: https://example.com/careers
""", encoding="utf-8")
        settings = load_settings(config)
        storage = JobStorage(settings.app.database_path)
        storage.initialize()
        title = "HTTP 与 AI 应用开发（离线验证）"
        job = JobPosting(company="离线验证企业", title=title, location="上海",
                         description="要求熟悉 HTTP、Python 和 RAG。能解释请求响应，编写 API 并核对模型引用。" * 8,
                         requirements="本科，熟悉 HTTP、Python 和 RAG。", recruitment_type="校招",
                         source_url="https://example.com/jobs/http", apply_url="https://example.com/apply/http",
                         match_level=MatchLevel.MEDIUM)
        storage.store_jobs([job], "2026-10-05T09:00:00+08:00")
        boss_title = "HTTP Agent 开发（平台离线验证）"
        boss_repository = BossLeadRepository(settings.app.database_path)
        boss_repository.initialize()
        boss_repository.import_leads(parse_boss_export(json.dumps({"jobs": [{"job_id": "offline123", "title": boss_title, "boss_name": "平台离线企业", "location": "上海", "tags": "应届生 | 本科", "job_link": "https://www.zhipin.com/job_detail/offline123.html", "jd": "负责 AI Agent 应用开发、Python HTTP API 服务与客户场景部署。 " * 6}]}, ensure_ascii=False)))
        app = create_app(config, web_dist=ROOT / "web/dist")
        gateway = FakeGateway()
        app.state.growth_manager.gateway_factory = lambda _: gateway
        now = [datetime(2026, 10, 5, 9, tzinfo=ZONE)]
        app.state.growth_service.clock = lambda: now[0]
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started
        origin = f"http://127.0.0.1:{port}"
        errors = []
        requests = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: requests.append(request.url))
                page.goto(origin, wait_until="networkidle")
                expect(page.get_by_role("heading", name="今日岗位机会", exact=True)).to_be_visible()
                expect(page.get_by_role("link", name=title, exact=True)).to_be_visible()
                assert not any("/api/reports" in url for url in requests), "Hidden global search fetched reports"
                assert not any("CommandPalette-" in url for url in requests), "Global search was eagerly loaded"
                metrics["homeJsBytes"] = page.evaluate("performance.getEntriesByType('resource').filter(e=>e.name.endsWith('.js')).reduce((sum,e)=>sum+e.encodedBodySize,0)")
                expect(page.get_by_text("资格待核对", exact=True)).to_be_visible()
                audit(page, reports, "home-desktop")
                page.get_by_role("link", name="跳转到主内容").focus()
                page.keyboard.press("Enter")
                assert page.locator("#main-content").evaluate("el=>el===document.activeElement")
                page.get_by_role("button", name="打开全局搜索").focus()
                page.keyboard.press("Control+k")
                expect(page.get_by_placeholder("搜索岗位、企业、技能关键词、城市、运行记录…")).to_be_visible()
                audit(page, reports, "search-dialog")
                page.keyboard.press("Escape")
                expect(page.get_by_role("button", name="打开全局搜索")).to_be_focused()
                page.get_by_role("link", name="查看全部来源岗位", exact=True).click()
                search = page.get_by_label("搜索全部岗位", exact=True)
                page.evaluate("""window.__paintDelays=[]; document.querySelector('main').addEventListener('input', () => {
                  const start=performance.now(); requestAnimationFrame(()=>requestAnimationFrame(()=>window.__paintDelays.push(performance.now()-start)));
                }, true);""")
                for text in ["HT", "HTTP", "HTTP 与"]:
                    search.fill(text)
                    page.wait_for_function("window.__paintDelays.length > 0")
                    page.wait_for_function("value => new URL(location.href).searchParams.get('q')===value", arg=text)
                metrics["filterInputToPaintMs"] = page.evaluate("window.__paintDelays")
                search.fill("HTTP")
                page.wait_for_function("new URL(location.href).searchParams.get('q')==='HTTP'")
                page.goto(f"{origin}/jobs?q=HTTP&excluded=1&shown=120", wait_until="networkidle")
                list_url = page.url
                audit(page, reports, "jobs-all")
                page.locator("main a[href*='source=boss']").filter(has_text=boss_title).click()
                page.get_by_role("button", name="关闭选中详情，返回列表", exact=True).click()
                assert page.url == list_url
                expect(page.get_by_label("搜索全部岗位", exact=True)).to_have_value("HTTP")
                page.locator("main a[href^='/jobs/']").filter(has_text=title).first.click()
                expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
                audit(page, reports, "job-detail")
                page.reload(wait_until="networkidle")
                page.get_by_role("link", name="返回岗位中心", exact=True).click()
                assert page.url == list_url
                expect(page.get_by_label("搜索全部岗位", exact=True)).to_have_value("HTTP")
                page.locator("main a[href^='/jobs/']").filter(has_text=title).first.click()
                page.get_by_role("button", name="加入成长目标", exact=True).click()
                page.goto(f"{origin}/growth?tab=targets")
                expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
                page.get_by_role("button", name="分析岗位要求", exact=True).click()
                expect(page.get_by_text("已提取 3 项要求", exact=False)).to_be_visible(timeout=20000)
                page.get_by_role("button", name="能力路线图", exact=True).click()
                page.get_by_role("button", name="HTTP，待验证", exact=False).focus()
                page.keyboard.press("Enter")
                audit(page, reports, "growth-map")
                page.get_by_role("button", name="开始回忆", exact=True).click()
                expect(page.get_by_label("我的回答", exact=True)).to_be_visible(timeout=20000)
                page.get_by_label("我的回答", exact=True).fill("不会")
                gateway.fail = True
                page.get_by_role("button", name="提交回答", exact=True).click()
                expect(page.get_by_role("button", name="重试", exact=True)).to_be_visible(timeout=20000)
                page.reload(wait_until="networkidle")
                expect(page.get_by_label("我的回答", exact=True)).to_have_value("不会")
                audit(page, reports, "scoring-failed-answer-recovered")
                gateway.fail = False
                page.get_by_role("button", name="重试", exact=True).click()
                expect(page.get_by_text("针对本次回答的讲解", exact=True)).to_be_visible(timeout=20000)
                audit(page, reports, "recall-teaching")
                now[0] += timedelta(days=1)
                page.goto(f"{origin}/growth?skill=http")
                page.get_by_role("button", name="开始回忆", exact=True).click()
                expect(page.get_by_label("我的回答", exact=True)).to_be_visible(timeout=20000)
                page.get_by_label("我的回答", exact=True).fill("HTTP 请求由客户端发出，包含方法、路径和 Headers；响应包含状态码和正文。GET 读取资源，POST 提交数据。400 是请求错误，500 是服务端错误。Cookie 随请求发送，Session 是会话机制。")
                page.get_by_role("button", name="提交回答", exact=True).click()
                expect(page.get_by_text("本轮已完成，证据已保存。", exact=True)).to_be_visible(timeout=20000)
                page.get_by_role("button", name="查看更新后的能力证据", exact=True).click()
                expect(page.get_by_text("Level 2 / 5", exact=False)).to_be_visible()
                page.get_by_role("button", name="提交项目证据", exact=True).click()
                code = "def api_route():\n    return {'answer': '合成验证内容'}"
                page.get_by_label("代码或项目材料", exact=True).fill(code)
                page.reload(wait_until="networkidle")
                page.get_by_role("button", name="提交项目证据", exact=True).click()
                expect(page.get_by_label("代码或项目材料", exact=True)).to_have_value(code)
                page.get_by_role("button", name="提交项目证据", exact=True).click()
                for width in [390, 768, 1280, 1440]:
                    page.set_viewport_size({"width": width, "height": 1000})
                    for name, path in [("home", "/"), ("jobs", "/jobs?q=HTTP"), ("growth", "/growth?skill=http")]:
                        page.goto(origin + path, wait_until="networkidle")
                        audit(page, reports, f"{name}-{width}")
                        page.screenshot(path=str(output / f"frontend-{name}-{width}.png"), full_page=True, animations="disabled")
                page.set_viewport_size({"width": 720, "height": 500})
                page.emulate_media(reduced_motion="reduce")
                page.goto(origin, wait_until="networkidle")
                audit(page, reports, "home-200-percent-equivalent")
                page.goto(f"{origin}/jobs?source=boss&category=review&q=HTTP&handled=1", wait_until="networkidle")
                expect(page.get_by_label("搜索 BOSS 岗位")).to_have_value("HTTP")
                assert page.locator("#boss-category").input_value() == "review"
                page.reload(wait_until="networkidle")
                assert parse_qs(urlparse(page.url).query)["handled"] == ["1"]
                audit(page, reports, "boss-filter-restored")
                page.goto(f"{origin}/jobs?source=boss&category=priority&q=HTTP&handled=1", wait_until="networkidle")
                expect(page.get_by_role("heading", name=boss_title, exact=True)).to_be_visible()
                page.route("**/api/platform-leads", lambda route: route.fulfill(status=503, content_type="application/json", body='{"detail":"离线模拟刷新失败"}'))
                page.get_by_role("button", name="刷新机会", exact=True).click()
                expect(page.get_by_text("刷新失败，保留上次结果。", exact=False)).to_be_visible(timeout=10000)
                expect(page.get_by_role("heading", name=boss_title, exact=True)).to_be_visible()
                audit(page, reports, "boss-refresh-failed-cached")
                page.unroute("**/api/platform-leads")
                page.goto(origin, wait_until="networkidle")
                page.get_by_role("link", name=title, exact=True).evaluate("el=>el.textContent='VeryLongUnbrokenTechnicalJobTitle'.repeat(12)")
                audit(page, reports, "home-long-unbroken-title")
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            (output / "frontend-verification.partial.json").write_text(json.dumps({"axe": reports, "metrics": metrics}, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [report for report in reports if report["violations"] or report["overflow"] or report["mainHeadings"] != 1]
    result = {"status": "failed" if failures else "passed", "axe": reports, "metrics": metrics, "liveModelCalls": 0}
    (output / "frontend-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    assert not failures, json.dumps(failures, ensure_ascii=False)
    print(json.dumps({"status": "passed", "axePages": len(reports), "metrics": metrics, "liveModelCalls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
