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


def test_hash_route_renders_even_when_static_shell_has_navigation_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = CrawlerConfig(
        render_mode="auto",
        request_delay_min_seconds=0,
        request_delay_max_seconds=0,
        min_static_text_chars=100,
        user_agent="Mozilla/5.0 Career Radar crawler test",
    )
    fetcher = PageFetcher(config)
    route_url = "https://example.com/careers#/job/1001"
    static_page = FetchedPage(
        requested_url=route_url,
        final_url=route_url,
        html="<nav>" + "导航内容" * 100 + "</nav>",
        rendered=False,
        status_code=200,
    )
    monkeypatch.setattr(fetcher, "_static_fetch", lambda _url: static_page)
    monkeypatch.setattr(fetcher.robots, "ensure_allowed", lambda _url: None)
    rendered: list[str] = []

    def render(url: str) -> tuple[str, str]:
        rendered.append(url)
        return "<main>AI 应用工程师完整 JD</main>", url

    monkeypatch.setattr(fetcher.renderer, "render", render)

    page = fetcher.fetch(route_url)

    assert rendered == [route_url]
    assert page.rendered is True
    assert "完整 JD" in page.html


def test_configured_job_selector_forces_render_and_waits_for_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = CrawlerConfig(
        render_mode="auto",
        request_delay_min_seconds=0,
        request_delay_max_seconds=0,
        min_static_text_chars=100,
        user_agent="Mozilla/5.0 Career Radar crawler test",
    )
    fetcher = PageFetcher(config)
    static_page = FetchedPage(
        requested_url="https://example.com/careers",
        final_url="https://example.com/careers",
        html="<nav>" + "导航内容" * 100 + "</nav>",
        rendered=False,
        status_code=200,
    )
    monkeypatch.setattr(fetcher, "_static_fetch", lambda _url: static_page)
    monkeypatch.setattr(fetcher.robots, "ensure_allowed", lambda _url: None)
    observed: list[tuple[str, str]] = []

    def render(url: str, *, wait_selector: str) -> tuple[str, str]:
        observed.append((url, wait_selector))
        return "<main class='job-list'>AI 应用工程师</main>", url

    monkeypatch.setattr(fetcher.renderer, "render", render)

    page = fetcher.fetch("https://example.com/careers", wait_selector=".job-list")

    assert observed == [("https://example.com/careers", ".job-list")]
    assert page.rendered is True
    assert "AI 应用工程师" in page.html


def test_configured_selector_failure_does_not_accept_navigation_as_jd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = CrawlerConfig(
        render_mode="auto",
        request_delay_min_seconds=0,
        request_delay_max_seconds=0,
        min_static_text_chars=100,
        user_agent="Mozilla/5.0 Career Radar crawler test",
    )
    fetcher = PageFetcher(config)
    static_page = FetchedPage(
        "https://example.com/careers",
        "https://example.com/careers",
        "<nav>" + "导航内容" * 100 + "</nav>",
        False,
        200,
    )
    monkeypatch.setattr(fetcher, "_static_fetch", lambda _url: static_page)
    monkeypatch.setattr(
        fetcher.renderer,
        "render",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(CrawlError("岗位列表未出现")),
    )

    with pytest.raises(CrawlError, match="岗位列表未出现"):
        fetcher.fetch("https://example.com/careers", wait_selector=".job-list")


def test_renderer_waits_for_configured_selector_before_reading_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = CrawlerConfig(
        render_mode="auto",
        request_delay_min_seconds=0,
        request_delay_max_seconds=0,
        playwright_wait_after_load_ms=0,
        user_agent="Mozilla/5.0 Career Radar crawler test",
    )
    fetcher = PageFetcher(
        config,
        target_policy=PublicTargetPolicy(lambda _host, _port: ["93.184.216.34"]),
    )
    calls: list[str] = []

    class Page:
        url = "https://example.com/jobs"

        def goto(self, *_args: object, **_kwargs: object) -> None:
            calls.append("goto")

        def wait_for_selector(self, selector: str, **_kwargs: object) -> None:
            assert selector == ".job-list"
            calls.append("wait")

        def content(self) -> str:
            calls.append("content")
            return "<div class='job-list'>招聘岗位</div>"

        def close(self) -> None:
            calls.append("close")

    class Context:
        def new_page(self) -> Page:
            return Page()

    monkeypatch.setattr(fetcher.renderer, "_start", lambda: None)
    fetcher.renderer._context = Context()

    html, _url = fetcher.renderer.render(
        "https://example.com/jobs", wait_selector=".job-list"
    )

    assert "招聘岗位" in html
    assert calls == ["goto", "wait", "content", "close"]


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


class _HtmlResponse(_NotModifiedResponse):
    status_code = 200
    headers = {"Content-Type": "text/html; charset=utf-8"}
    encoding = "utf-8"

    def iter_content(self, *, chunk_size: int):
        assert chunk_size > 0
        yield "<main>公开招聘岗位</main>".encode()


def test_static_fetch_without_cache_validators_reaches_homepage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = CrawlerConfig(
        render_mode="never",
        request_delay_min_seconds=0,
        request_delay_max_seconds=0,
        user_agent="Mozilla/5.0 Career Radar crawler test",
    )
    fetcher = PageFetcher(config)
    captured: dict[str, object] = {}
    monkeypatch.setattr(fetcher.robots, "ensure_allowed", lambda _url: None)

    def fake_get(_url: str, **kwargs: object) -> _HtmlResponse:
        captured.update(kwargs)
        return _HtmlResponse()

    monkeypatch.setattr(fetcher.session, "get", fake_get)

    page = fetcher.fetch("https://example.com/jobs")

    assert captured["headers"] is None
    assert page.status_code == 200
    assert "公开招聘岗位" in page.html


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


def test_sitemap_fetch_accepts_xml_without_render_and_rejects_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = CrawlerConfig(
        render_mode="always",
        request_delay_min_seconds=0,
        request_delay_max_seconds=0,
        user_agent="Mozilla/5.0 Career Radar crawler test",
    )
    fetcher = PageFetcher(config)
    monkeypatch.setattr(fetcher.robots, "ensure_allowed", lambda _url: None)

    class XmlResponse(_HtmlResponse):
        headers = {"Content-Type": "application/xml; charset=utf-8"}

        def iter_content(self, *, chunk_size: int):
            assert chunk_size > 0
            yield b"<urlset></urlset>"

    monkeypatch.setattr(fetcher.session, "get", lambda *_args, **_kwargs: XmlResponse())

    assert fetcher.fetch_sitemap("https://example.com/sitemap.xml").html == "<urlset></urlset>"
    monkeypatch.setattr(fetcher.session, "get", lambda *_args, **_kwargs: _HtmlResponse())
    with pytest.raises(CrawlError, match="不是XML 站点地图"):
        fetcher.fetch_sitemap("https://example.com/sitemap.xml")


def test_sitemap_redirect_must_stay_on_official_host(monkeypatch: pytest.MonkeyPatch) -> None:
    config = CrawlerConfig(
        render_mode="never",
        request_delay_min_seconds=0,
        request_delay_max_seconds=0,
        user_agent="Mozilla/5.0 Career Radar crawler test",
    )
    fetcher = PageFetcher(config)
    monkeypatch.setattr(fetcher.robots, "ensure_allowed", lambda _url: None)
    requested: list[str] = []

    class RedirectResponse(_HtmlResponse):
        status_code = 302
        is_redirect = True
        headers = {"Location": "https://other.example/sitemap.xml"}

    def fake_get(url: str, **_kwargs: object) -> RedirectResponse:
        requested.append(url)
        return RedirectResponse()

    monkeypatch.setattr(fetcher.session, "get", fake_get)

    with pytest.raises(CrawlError, match="站外"):
        fetcher.fetch_sitemap("https://example.com/sitemap.xml")
    assert requested == ["https://example.com/sitemap.xml"]
