"""本地合成岗位的真实前端验收：资格、排序、评估、画像失效和响应式。"""

from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

import uvicorn
from playwright.sync_api import expect, sync_playwright

from career_radar.api import create_app
from career_radar.config import load_settings
from career_radar.models import JobPosting
from career_radar.storage import JobStorage


class LocalGateway:
    def generate(self, model, _system, user):
        prompt = json.loads(user)
        candidate_quote = next(q for q in prompt["candidate"]["allowed_evidence_quotes"] if q.startswith("合成项目"))
        return model.model_validate({
            "direction": "ai_application", "direction_score": 90, "evidence_score": 80,
            "summary": "合成项目中的 API 开发与岗位职责相关，优先准备真实演示。",
            "matches": [{"requirement": "API 开发", "job_quote": "Python API 开发", "candidate_quote": candidate_quote, "reason": "已有可展示 API 项目"}],
            "gaps": [{"job_quote": "Python API 开发", "detail": "需要补充项目测试证据"}],
            "next_steps": ["提供 API 演示和测试结果"],
        })


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    captures = root / "tmp/official-screening-ui"
    captures.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="career-radar-screening-ui-") as directory:
        temp = Path(directory)
        config = temp / "config.yaml"
        config.write_text("""
app:
  database_path: data/test.db
crawler:
  render_mode: never
  user_agent: Career Radar official screening UI verification
llm:
  provider: mimo
  model: local-no-network
candidate:
  graduation_year: 2026
  graduation_month: 2026-06
  education_level: 本科
  school_background: 普通本科（二本），非985/211
  major: 计算机
  student_status: graduated
  education_mode: full_time
  formal_work_years: 0
  skills: [Python]
  skill_levels: {Python: 熟悉}
  projects: [合成项目：Python API 开发与数据处理]
  target_roles: [AI 应用开发]
  preferred_locations: [不限]
  constraints: [应届优先]
companies:
  - name: 合成官网企业
    url: https://example.com/jobs
    enabled: false
""", encoding="utf-8")
        settings = load_settings(config)
        storage = JobStorage(settings.app.database_path)
        storage.initialize()
        base = dict(company="合成官网企业", description="Python API 开发。", requirements="本科及以上，接受应届生，无需工作经验。", source_url="https://example.com/jobs", apply_url="https://example.com/apply")
        yesterday = (datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)).isoformat()
        events = storage.store_jobs([
            JobPosting(title="2026届 AI 应用后端", source_job_id="test:1", recruitment_type="校招", **base),
            JobPosting(title="AI 交付开发", source_job_id="test:2", recruitment_type="全职", **{**base, "requirements": "本科及以上，相关项目经验。"}),
            JobPosting(title="2027届 FDE岗位", source_job_id="test:3", recruitment_type="校招", **base),
            JobPosting(title="2026届 AI 已截止", source_job_id="test:4", recruitment_type="校招", valid_until=yesterday, **base),
        ], datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        app = create_app(config, web_dist=root / "web/dist")
        app.state.official_screening.gateway_factory = lambda _config: LocalGateway()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 15
        while True:
            try:
                with urlopen(origin + "/api/health", timeout=1) as response:  # noqa: S310
                    if response.status == 200:
                        break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
        errors: list[str] = []
        external: list[str] = []
        results = {}
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda req: external.append(req.url) if req.url.startswith(("http://", "https://")) and not req.url.startswith(origin) else None)
                page.goto(origin + "/jobs?source=official", wait_until="networkidle")
                expect(page.get_by_text("2026届 AI 应用后端", exact=True)).to_be_visible()
                expect(page.get_by_text("2027届 FDE岗位", exact=True)).to_have_count(0)
                page.get_by_role("button", name="AI 评估并排序", exact=True).click()
                expect(page.get_by_role("status").filter(has_text="本轮评估完成")).to_be_visible(timeout=15000)
                expect(page.get_by_role("row").filter(has_text="2026届 AI 应用后端").get_by_text("优先投递 · 84", exact=True)).to_be_visible()
                titles = page.locator("tbody tr").all_text_contents()
                assert "2026届 AI 应用后端" in titles[0] and "AI 交付开发" in titles[1]
                page.screenshot(path=str(captures / "desktop-list.png"))
                page.get_by_role("combobox", name="资格筛选").click()
                page.get_by_role("option", name="明确不符", exact=True).click()
                expect(page.get_by_text("2027届 FDE岗位", exact=True)).to_be_visible()
                expect(page.get_by_text("2026届 AI 已截止", exact=True)).to_be_visible()
                page.goto(f"{origin}/jobs/{events[0].entity_key}", wait_until="networkidle")
                expect(page.get_by_role("heading", name="资格与投递优先级")).to_be_visible()
                page.get_by_text("画像匹配判断与引用依据 · 展开分析", exact=True).click()
                expect(page.get_by_text("画像原文：", exact=False)).to_be_visible()
                expect(page.get_by_text("提供 API 演示和测试结果", exact=True)).to_be_visible()
                page.screenshot(path=str(captures / "desktop-detail.png"))
                page.goto(origin + "/profile", wait_until="networkidle")
                expect(page.get_by_label("当前学籍状态")).to_have_text("已毕业")
                page.get_by_label("正式工作年限").fill("1")
                page.get_by_role("button", name="保存画像", exact=True).click()
                expect(page.get_by_text("画像已保存", exact=True)).to_be_visible()
                page.goto(f"{origin}/jobs/{events[0].entity_key}", wait_until="networkidle")
                page.get_by_text("画像匹配判断与引用依据 · 展开分析", exact=True).click()
                expect(page.get_by_text("画像、岗位正文或模型配置已变化", exact=False)).to_be_visible()
                page.get_by_role("button", name="AI 评估方向", exact=True).click()
                expect(page.get_by_text("画像原文：", exact=False)).to_be_visible(timeout=15000)
                page.set_viewport_size({"width": 390, "height": 844})
                page.goto(origin + "/jobs?source=official", wait_until="networkidle")
                expect(page.get_by_role("combobox", name="资格筛选")).to_be_visible()
                page.screenshot(path=str(captures / "mobile-list.png"))
                results["mobile_list_overflow"] = page.evaluate("document.documentElement.scrollWidth > innerWidth")
                page.goto(f"{origin}/jobs/{events[0].entity_key}", wait_until="networkidle")
                page.screenshot(path=str(captures / "mobile-detail.png"))
                results["mobile_detail_overflow"] = page.evaluate("document.documentElement.scrollWidth > innerWidth")
                browser.close()
            assert not errors, errors
            assert not external, external
            assert not any(results.values()), results
            print(json.dumps({"passed": True, "checks": ["eligibility_filter", "priority_sort", "background_evaluation", "jd_candidate_evidence", "profile_invalidation", "reevaluation", "mobile_layout"], "screenshots": str(captures), "overflow": results}, ensure_ascii=False))
        finally:
            server.should_exit = True
            thread.join(timeout=15)


if __name__ == "__main__":
    main()
