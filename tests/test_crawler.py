"""静态抓取与 Playwright 自动回退的可靠性测试。"""

from __future__ import annotations

import pytest

from career_radar.crawler import CrawlError, FetchedPage, PageFetcher
from career_radar.models import CrawlerConfig
from career_radar.network_policy import PublicTargetPolicy


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


class _Route:
    def __init__(self) -> None:
        self.aborted = False
        self.continued = False

    def abort(self, _reason: str) -> None:
        self.aborted = True

    def continue_(self) -> None:
        self.continued = True


class _Request:
    def __init__(self, url: str) -> None:
        self.url = url


def test_playwright_guard_blocks_private_subresources() -> None:
    config = CrawlerConfig(
        render_mode="never",
        request_delay_min_seconds=0,
        request_delay_max_seconds=0,
        user_agent="Mozilla/5.0 Career Radar crawler test",
    )
    fetcher = PageFetcher(
        config,
        target_policy=PublicTargetPolicy(
            lambda _hostname, _port: ["93.184.216.34"]
        ),
    )
    route = _Route()

    fetcher.renderer._guard_request(  # noqa: SLF001 - focused security boundary test
        route,
        _Request("http://127.0.0.1:9000/private"),
    )

    assert route.aborted is True
    assert route.continued is False


class _NotModifiedResponse:
    status_code = 304
    is_redirect = False
    is_permanent_redirect = False
    headers = {"ETag": '"page-v1"'}
    encoding = None

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        pass


def test_static_fetch_sends_validators_and_returns_not_modified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = CrawlerConfig(
        render_mode="never",
        request_delay_min_seconds=0,
        request_delay_max_seconds=0,
        user_agent="Mozilla/5.0 Career Radar crawler test",
    )
    fetcher = PageFetcher(
        config,
        target_policy=PublicTargetPolicy(
            lambda _hostname, _port: ["93.184.216.34"]
        ),
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(fetcher.robots, "ensure_allowed", lambda _url: None)

    def fake_get(_url: str, **kwargs: object) -> _NotModifiedResponse:
        captured.update(kwargs)
        return _NotModifiedResponse()

    monkeypatch.setattr(fetcher.session, "get", fake_get)

    page = fetcher.fetch(
        "https://example.com/jobs",
        {"If-None-Match": '"page-v1"'},
    )

    assert captured["headers"] == {"If-None-Match": '"page-v1"'}
    assert page.not_modified is True
    assert page.status_code == 304
    assert page.etag == '"page-v1"'
