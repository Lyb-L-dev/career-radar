"""构建并验证由 FastAPI 托管的真实前端产物，全程使用临时本地数据。"""

from __future__ import annotations

import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn
from playwright.sync_api import expect, sync_playwright

from career_radar.api import create_app
from career_radar.config import load_settings
from career_radar.models import JobPosting, MatchLevel, ProfileFitLevel
from career_radar.storage import JobStorage


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_config(root: Path, origin: str) -> Path:
    config_path = root / "config.yaml"
    config_path.write_text(
        f"""
app:
  timezone: Asia/Shanghai
  database_path: data/e2e.db
  output_dir: output
  log_dir: logs
  cors_origins: [{origin}]
crawler:
  render_mode: never
  request_delay_min_seconds: 0
  request_delay_max_seconds: 0
  user_agent: Career Radar packaged E2E
llm:
  provider: deepseek
  model: e2e-no-call
smtp:
  enabled: false
candidate:
  graduation_year: 2026
  education_level: 本科
  school_background: 本科
  major: 数据科学与大数据技术
  skills: [Python, MySQL]
  target_roles: [数据开发]
  preferred_locations: [上海]
companies:
  - name: E2E 示例企业
    url: https://example.com/careers
    enabled: false
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return config_path


def _seed_report(config_path: Path) -> None:
    settings = load_settings(config_path)
    job = JobPosting(
        company="E2E 示例企业",
        title="数据开发工程师",
        location="上海",
        description="只用于本地打包形态 E2E 的岗位记录。",
        requirements="熟悉 Python 与 MySQL。",
        recruitment_type="校招",
        is_2026_target=True,
        source_url="https://example.com/jobs/e2e",
        apply_url="https://example.com/apply/e2e",
        match_level=MatchLevel.HIGH,
        profile_fit_level=ProfileFitLevel.HIGH,
        difficulty_score=4,
    )
    storage = JobStorage(settings.app.database_path)
    storage.initialize()
    storage.store_jobs([job], "2026-08-10T08:00:00+08:00")
    settings.app.output_dir.mkdir(parents=True, exist_ok=True)
    (settings.app.output_dir / "2026-08-10-jobs.md").write_text(
        "# E2E 日报\n",
        encoding="utf-8",
    )
    (settings.app.output_dir / "2026-08-10-jobs.csv").write_text(
        "company,title\nE2E 示例企业,数据开发工程师\n",
        encoding="utf-8-sig",
    )


def _build_frontend(repo_root: Path, output_dir: Path) -> None:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise RuntimeError("未找到 npm，请先安装 Node.js 22")
    subprocess.run(
        [
            npm,
            "run",
            "build",
            "--",
            "--outDir",
            str(output_dir),
            "--emptyOutDir",
        ],
        cwd=repo_root / "web",
        check=True,
    )


def _wait_until_ready(origin: str, timeout_seconds: float = 15) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{origin}/api/health", timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.1)
    raise RuntimeError("临时 FastAPI 服务未在预期时间内启动")


def _run_browser(origin: str) -> None:
    page_errors: list[str] = []
    server_errors: list[str] = []
    external_requests: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "response",
            lambda response: server_errors.append(f"{response.status} {response.url}")
            if response.url.startswith(origin) and response.status >= 500
            else None,
        )
        page.on(
            "request",
            lambda request: external_requests.append(request.url)
            if request.url.startswith(("http://", "https://"))
            and not request.url.startswith(origin)
            else None,
        )

        settings_response = page.goto(
            f"{origin}/settings?tab=llm",
            wait_until="networkidle",
        )
        assert settings_response is not None and settings_response.status == 200
        expect(
            page.locator("main").get_by_role("heading", name="系统设置")
        ).to_be_visible()
        expect(page.get_by_text("DeepSeek", exact=True)).to_be_visible()
        expect(page.get_by_text("由本机配置决定", exact=False)).to_be_visible()
        assert page.get_by_text("LiteLLM", exact=False).count() == 0

        page.get_by_role("button", name="测试连接").click()
        expect(page.get_by_role("alertdialog")).to_be_visible()
        expect(page.get_by_text("确认测试 DeepSeek 连接？", exact=True)).to_be_visible()
        page.get_by_role("button", name="取消").click()

        page.goto(f"{origin}/settings?tab=data", wait_until="networkidle")
        expect(page.get_by_text("还没有本地备份")).to_be_visible()
        page.get_by_role("button", name="创建备份").click()
        page.get_by_role("button", name="创建本地备份").click()
        backup_row = page.locator("li").filter(has_text="career-radar-backup-")
        expect(backup_row).to_have_count(1)
        backup_row.get_by_role("button", name="校验").click()
        expect(backup_row.get_by_text("校验通过")).to_be_visible()
        backup_row.get_by_role("button", name="删除").click()
        page.get_by_role("button", name="确认删除备份").click()
        expect(page.get_by_text("还没有本地备份")).to_be_visible()

        report_response = page.goto(f"{origin}/reports", wait_until="networkidle")
        assert report_response is not None and report_response.status == 200
        expect(
            page.locator("main").get_by_role("heading", name="日报中心")
        ).to_be_visible()
        expect(page.get_by_role("button", name="2026-08-10")).to_be_visible()
        expect(page.get_by_text("显示 1 / 1 份日报", exact=True)).to_be_visible()

        browser.close()

    assert not page_errors, f"浏览器脚本错误：{page_errors}"
    assert not server_errors, f"本地接口 5xx：{server_errors}"
    assert not external_requests, f"E2E 不应访问外部网络：{external_requests}"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="career-radar-e2e-") as directory:
        temp_root = Path(directory)
        web_dist = temp_root / "web-dist"
        port = _free_port()
        origin = f"http://127.0.0.1:{port}"
        _build_frontend(repo_root, web_dist)
        config_path = _write_config(temp_root, origin)
        _seed_report(config_path)

        app = create_app(config_path, web_dist=web_dist)
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            _wait_until_ready(origin)
            _run_browser(origin)
        finally:
            server.should_exit = True
            thread.join(timeout=10)
        if thread.is_alive():
            raise RuntimeError("临时 FastAPI 服务未正常停止")

    print("Packaged web E2E passed: no external requests or paid model calls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
