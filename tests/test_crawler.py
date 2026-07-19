"""静态抓取与 Playwright 自动回退的可靠性测试。"""

from __future__ import annotations

import pytest

from career_radar.crawler import CrawlError, FetchedPage, PageFetcher
from career_radar.models import CrawlerConfig


class _FailingRenderer:
    def render(self, url: str) -> tuple[str, str]:
        raise CrawlError(f"模拟渲染失败：{url}")

    def close(self) -> None:
        pass


def _fetcher(monkeypatch: pytest.MonkeyPatch, html: str, *, minimum: int = 100) -> PageFetcher:
    config = CrawlerConfig(
        render_mode="auto",
        request_delay_min_seconds=0,
        request_delay_max_seconds=0,
        min_static_text_chars=minimum,
        user_agent="Mozilla/5.0 Career Radar crawler test",
    )
    fetcher = PageFetcher(config)
    static_page = FetchedPage(
        requested_url="https://example.com/jobs",
        final_url="https://example.com/jobs",
        html=html,
        rendered=False,
        status_code=200,
    )
    monkeypatch.setattr(fetcher, "_static_fetch", lambda _url: static_page)
    fetcher.renderer = _FailingRenderer()  # type: ignore[assignment]
    return fetcher


def test_auto_render_failure_rejects_spa_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    fetcher = _fetcher(monkeypatch, '<div id="root"></div>')

    with pytest.raises(CrawlError, match="SPA 空壳"):
        fetcher.fetch("https://example.com/jobs")


def test_auto_render_failure_keeps_meaningful_static_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = '<div id="root"></div><main>' + ("公开招聘正文" * 20) + "</main>"
    fetcher = _fetcher(monkeypatch, html, minimum=100)

    page = fetcher.fetch("https://example.com/jobs")

    assert page.html == html
    assert page.rendered is False
