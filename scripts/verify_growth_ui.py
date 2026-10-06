"""Exercise the real growth frontend/API with a fake model and temporary data."""

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

import uvicorn
from playwright.sync_api import expect, sync_playwright

from career_radar.api import create_app
from career_radar.growth.evidence import ZONE

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_growth import FakeGateway  # noqa: E402


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="career-growth-browser-") as temporary:
        config = Path(temporary) / "config.yaml"
        config.write_text("""app:
  database_path: data/test.db
crawler:
  render_mode: never
  user_agent: Career Radar offline UI verification
llm:
  provider: mimo
  model: offline-fixture
smtp:
  enabled: false
companies:
  - name: 离线测试企业
    url: https://example.com/careers
""", encoding="utf-8")
        app = create_app(config, web_dist=ROOT / "web" / "dist")
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
                page = browser.new_page(viewport={"width": 1600, "height": 1050})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: requests.append(request.url))
                page.goto(f"{origin}/growth?tab=targets")
                page.get_by_label("岗位名称", exact=True).fill("QA 测试岗位：AI 应用开发")
                page.get_by_label("企业名称（选填）").fill("离线测试企业")
                page.get_by_label("完整 JD", exact=True).fill("要求熟悉 HTTP、Python 和 RAG。能解释请求响应，编写 API 并核对模型引用。")
                page.get_by_role("button", name="加入目标岗位组", exact=True).click()
                expect(page.get_by_role("heading", name="QA 测试岗位：AI 应用开发", exact=True)).to_be_visible()
                page.get_by_role("button", name="分析岗位要求", exact=True).click()
                expect(page.get_by_text("已提取 3 项要求", exact=False)).to_be_visible(timeout=20_000)
                page.get_by_role("button", name="能力路线图", exact=True).click()
                page.get_by_role("button", name="HTTP，待验证", exact=False).click()
                expect(page.get_by_role("complementary", name="HTTP的能力证据")).to_be_visible()
                page.get_by_role("button", name="开始回忆", exact=True).click()
                expect(page.get_by_label("我的回答", exact=True)).to_be_visible(timeout=20_000)
                page.screenshot(path=str(output / "growth-session.png"), full_page=True, animations="disabled")
                page.get_by_label("我的回答", exact=True).fill("不会")
                page.get_by_role("button", name="提交回答", exact=True).click()
                expect(page.get_by_text("针对本次回答的讲解", exact=True)).to_be_visible(timeout=20_000)
                # Advance only the temporary app clock to verify cross-day replanning.
                now[0] += timedelta(days=1)
                page.get_by_role("button", name="查看更新后的能力证据", exact=True).click()
                page.goto(f"{origin}/growth?skill=http")
                page.get_by_role("button", name="开始回忆", exact=True).click()
                expect(page.get_by_label("我的回答", exact=True)).to_be_visible(timeout=20_000)
                page.get_by_label("我的回答", exact=True).fill("HTTP 请求由客户端发出，包含方法、路径和 Headers；响应包含状态码和正文。GET 读取资源，POST 提交数据。400 是请求错误，500 是服务端错误。Cookie 随请求发送，Session 在服务端保存会话。")
                page.get_by_role("button", name="提交回答", exact=True).click()
                expect(page.get_by_text("本轮已完成，证据已保存。", exact=True)).to_be_visible(timeout=20_000)
                page.get_by_role("button", name="查看更新后的能力证据", exact=True).click()
                page.goto(f"{origin}/growth?skill=http")
                expect(page.get_by_text("Level 2 / 5", exact=False)).to_be_visible()
                expect(page.get_by_text("2026-10-07", exact=True)).to_be_visible()
                page.screenshot(path=str(output / "growth-desktop.png"), full_page=True, animations="disabled")
                page.get_by_role("button", name="JD 对照", exact=True).click()
                expect(page.get_by_text("已有对应证据 · 当前 L2", exact=True)).to_be_visible()
                page.screenshot(path=str(output / "growth-jd.png"), full_page=True, animations="disabled")
                page.get_by_role("button", name="今日行动", exact=True).click()
                expect(page.get_by_text("2026-10-06 · 今日两份证据", exact=True)).to_be_visible()
                expect(page.get_by_role("heading", name="完成后留下什么")).to_have_count(2)
                page.screenshot(path=str(output / "growth-today.png"), full_page=True, animations="disabled")
                page.get_by_text("记录完成情况与卡点", exact=True).first.click()
                page.get_by_label("卡在哪里", exact=True).first.fill("Headers 还需要一个真实接口例子")
                assert page.get_by_label("卡在哪里", exact=True).first.input_value() == "Headers 还需要一个真实接口例子"
                with page.expect_response(lambda response: response.request.method == "PATCH" and "/api/growth/plans/" in response.url) as saved:
                    page.get_by_role("button", name="保存反馈", exact=True).first.click()
                assert saved.value.status == 200
                assert saved.value.request.post_data_json["blocker"] == "Headers 还需要一个真实接口例子", saved.value.request.post_data_json
                assert saved.value.json()["tasks"][0]["blocker"] == "Headers 还需要一个真实接口例子", saved.value.json()
                assert app.state.growth_service.repo.get("plans", "2026-10-06")["tasks"][0]["blocker"] == "Headers 还需要一个真实接口例子"
                page.reload()
                assert page.request.get(f"{origin}/api/growth").json()["plan"]["tasks"][0]["blocker"] == "Headers 还需要一个真实接口例子"
                expect(page.get_by_label("卡在哪里", exact=True).first).to_have_value("Headers 还需要一个真实接口例子")
                page.goto(f"{origin}/growth?skill=http")
                page.get_by_role("button", name="提交项目证据", exact=True).click()
                page.get_by_label("代码或项目材料", exact=True).fill("return JSONResponse(status_code=400, content={'error': 'invalid'})")
                page.get_by_label("我做了什么，为什么这样设计", exact=True).fill("请求非法时返回400，服务端异常返回500。")
                page.get_by_label("真实运行或测试记录（选填）", exact=True).fill("用户提交的测试记录：正常输入200，非法输入400。")
                page.get_by_role("button", name="审阅并开始追问", exact=True).click()
                expect(page.get_by_role("heading", name="项目实现追问", exact=False)).to_be_visible(timeout=20_000)
                page.get_by_label("我的回答", exact=True).fill("请求非法时返回400，服务端异常返回500。")
                page.get_by_role("button", name="提交回答", exact=True).click()
                expect(page.get_by_text("本轮已完成，证据已保存。", exact=True)).to_be_visible(timeout=20_000)
                page.goto(f"{origin}/growth?skill=http")
                page.set_viewport_size({"width": 390, "height": 844})
                expect(page.get_by_role("complementary", name="HTTP的能力证据")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "窄屏发生横向溢出"
                page.screenshot(path=str(output / "growth-mobile.png"), full_page=True, animations="disabled")
                page.goto(origin)
                expect(page.get_by_role("heading", name="今天，留下两份能力证据", exact=True)).to_be_visible()
                page.screenshot(path=str(output / "growth-home.png"), full_page=True, animations="disabled")
                assert not errors, errors
                assert all(not url.startswith(("http://", "https://")) or url.startswith(origin) for url in requests), "验证期间存在外部网络请求"
                browser.close()
                print(json.dumps({"status": "passed", "screenshots": [str(output / name) for name in ("growth-desktop.png", "growth-jd.png", "growth-mobile.png")], "modelCalls": len(gateway.calls), "liveModelCalls": 0}, ensure_ascii=False))
        finally:
            server.should_exit = True
            thread.join(timeout=30)
            assert not thread.is_alive(), "临时服务未正常停止"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output.resolve())
