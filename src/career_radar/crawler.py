"""遵守 robots.txt、带友好限速的 HTTP/Playwright 页面抓取器。"""

from __future__ import annotations

import logging
import random
import re
import time
import urllib.robotparser
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from trafilatura.sitemaps import extract_robots_sitemaps

from .models import CrawlerConfig
from .network_policy import PublicTargetPolicy, UnsafeTargetError
from .url_utils import canonicalize_url, is_spa_route, normalize_request_url, origin_of

LOGGER = logging.getLogger(__name__)


class CrawlError(RuntimeError):
    """单页抓取失败；上层会记录错误并继续下一页或下一家公司。"""


class RobotsDeniedError(CrawlError):
    """目标 URL 被 robots.txt 明确禁止或策略文件暂时不可用。"""


@dataclass(slots=True)
class FetchedPage:
    """抓取完成后的页面正文和元数据。"""

    requested_url: str
    final_url: str
    html: str
    rendered: bool
    status_code: int
    not_modified: bool = False
    etag: str | None = None
    last_modified: str | None = None


class RateLimiter:
    """按站点记录上次请求时间，确保每个域名之间有 5~10 秒友好间隔。"""

    def __init__(
        self,
        minimum: float,
        maximum: float,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.minimum = minimum
        self.maximum = maximum
        self.sleeper = sleeper
        self.clock = clock
        self.random_uniform = random_uniform
        self._last_request: dict[str, float] = {}

    def wait(self, url: str) -> None:
        """只在同一站点距离上次请求不足随机间隔时等待。"""

        origin = origin_of(url)
        now = self.clock()
        target_interval = self.random_uniform(self.minimum, self.maximum)
        previous = self._last_request.get(origin)
        if previous is not None:
            remaining = target_interval - (now - previous)
            if remaining > 0:
                self.sleeper(remaining)
                now = self.clock()
        self._last_request[origin] = now


@dataclass(slots=True)
class _RobotsEntry:
    parser: urllib.robotparser.RobotFileParser | None
    deny_all: bool = False
    sitemaps: tuple[str, ...] = ()


class RobotsPolicy:
    """通过当前 HTTP 会话读取并缓存每个站点的 robots.txt。"""

    def __init__(
        self,
        session: requests.Session,
        config: CrawlerConfig,
        limiter: RateLimiter,
        target_policy: PublicTargetPolicy | None = None,
    ) -> None:
        self.session = session
        self.config = config
        self.limiter = limiter
        self.target_policy = target_policy or PublicTargetPolicy()
        self._cache: dict[str, _RobotsEntry] = {}

    def _load(self, url: str) -> _RobotsEntry:
        origin = origin_of(url)
        if origin in self._cache:
            return self._cache[origin]

        robots_url = f"{origin}/robots.txt"
        try:
            current = robots_url
            response = None
            for _redirect in range(6):
                self.target_policy.ensure_public(current)
                self.limiter.wait(current)
                response = self.session.get(
                    current,
                    timeout=self.config.request_timeout_seconds,
                    allow_redirects=False,
                    headers={"User-Agent": self.config.user_agent},
                )
                if response.status_code not in {301, 302, 303, 307, 308}:
                    break
                location = response.headers.get("Location")
                close = getattr(response, "close", None)
                if callable(close):
                    close()
                if not location:
                    raise requests.RequestException("robots.txt 重定向缺少 Location")
                current = normalize_request_url(urljoin(current, location))
            else:
                raise requests.RequestException("robots.txt 重定向次数过多")
            if response is None:  # pragma: no cover - loop always performs one request
                raise requests.RequestException("robots.txt 未返回响应")
        except (requests.RequestException, UnsafeTargetError) as exc:
            # 无法确认规则时采取保守策略：本轮跳过该站点，而不是绕过合规检查。
            LOGGER.warning("robots.txt 获取失败，保守跳过站点 %s：%s", origin, exc)
            entry = _RobotsEntry(parser=None, deny_all=True)
        else:
            try:
                if response.status_code == 200:
                    parser = urllib.robotparser.RobotFileParser()
                    parser.set_url(current)
                    parser.parse(response.text.splitlines())
                    entry = _RobotsEntry(
                        parser=parser,
                        sitemaps=tuple(extract_robots_sitemaps(response.text, origin)),
                    )
                elif response.status_code in {401, 403} or response.status_code >= 500:
                    # 认证拒绝或服务端暂时不可达时不冒险抓取。
                    entry = _RobotsEntry(parser=None, deny_all=True)
                else:
                    # 404 等状态表示站点没有可用 robots.txt，允许访问公开页面。
                    entry = _RobotsEntry(parser=None, deny_all=False)
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        self._cache[origin] = entry
        return entry

    def sitemaps_for(self, url: str) -> tuple[str, ...]:
        """复用已缓存的 robots 声明；规则不可确认时不扩展站点地图。"""

        entry = self._load(url)
        return () if entry.deny_all else entry.sitemaps

    def ensure_allowed(self, url: str) -> None:
        """禁止时抛出专门异常，便于日报清楚说明跳过原因。"""

        try:
            self.target_policy.ensure_public(url)
        except UnsafeTargetError as exc:
            raise RobotsDeniedError(f"目标不是公开网络地址：{url}") from exc
        entry = self._load(url)
        if entry.deny_all:
            raise RobotsDeniedError(f"robots.txt 不可确认或禁止访问：{url}")
        # 使用通配组判断，因为请求头模拟浏览器而不是声明一个专有爬虫组。
        if entry.parser and not entry.parser.can_fetch("*", url):
            raise RobotsDeniedError(f"robots.txt 禁止访问：{url}")


class _PlaywrightRenderer:
    """延迟启动浏览器；未启用 JS 渲染时不会产生额外进程。"""

    def __init__(
        self,
        config: CrawlerConfig,
        limiter: RateLimiter,
        target_policy: PublicTargetPolicy,
    ) -> None:
        self.config = config
        self.limiter = limiter
        self.target_policy = target_policy
        self._manager = None
        self._browser = None
        self._context = None

    def _start(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise CrawlError("未安装 Playwright，请执行 pip install playwright") from exc
        self._manager = sync_playwright().start()
        try:
            self._browser = self._manager.chromium.launch(headless=True)
            self._context = self._browser.new_context(user_agent=self.config.user_agent)
            self._context.route("**/*", self._guard_request)
        except Exception:
            self.close()
            raise

    def _guard_request(self, route: Any, request: Any) -> None:
        """Block top-level redirects and subresources that target local networks."""

        request_url = str(request.url)
        if not request_url.startswith(("http://", "https://")):
            route.continue_()
            return
        try:
            self.target_policy.ensure_public(request_url)
        except UnsafeTargetError:
            LOGGER.warning("Playwright 已阻止非公开网络请求：%s", request_url)
            route.abort("blockedbyclient")
            return
        route.continue_()

    def render(self, url: str, *, wait_selector: str | None = None) -> tuple[str, str]:
        """渲染公开页面，不填写表单、不点击登录，也不保存 Cookie。"""

        try:
            self.target_policy.ensure_public(url)
        except UnsafeTargetError as exc:
            raise CrawlError(f"Playwright 拒绝非公开网络目标：{url}") from exc
        self._start()
        assert self._context is not None
        self.limiter.wait(url)
        page = self._context.new_page()
        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=int(self.config.playwright_timeout_seconds * 1000),
            )
            if wait_selector:
                page.wait_for_selector(
                    wait_selector,
                    state="visible",
                    timeout=int(self.config.playwright_timeout_seconds * 1000),
                )
            if self.config.playwright_wait_after_load_ms:
                page.wait_for_timeout(self.config.playwright_wait_after_load_ms)
            return page.content(), page.url
        except Exception as exc:
            raise CrawlError(f"Playwright 渲染失败：{url}：{exc}") from exc
        finally:
            page.close()

    def close(self) -> None:
        """按 context → browser → manager 顺序释放本地浏览器资源。"""

        for resource in (self._context, self._browser, self._manager):
            if resource is not None:
                try:
                    resource.close() if hasattr(resource, "close") else resource.stop()
                except Exception:
                    LOGGER.debug("关闭 Playwright 资源时出现非致命异常", exc_info=True)
        self._context = self._browser = self._manager = None


class PageFetcher:
    """统一处理 robots、重定向、响应大小、静态抓取和 JS 回退。"""

    def __init__(
        self,
        config: CrawlerConfig,
        *,
        session: requests.Session | None = None,
        limiter: RateLimiter | None = None,
        target_policy: PublicTargetPolicy | None = None,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": config.user_agent})
        self.limiter = limiter or RateLimiter(
            config.request_delay_min_seconds,
            config.request_delay_max_seconds,
        )
        self.target_policy = target_policy or PublicTargetPolicy()
        self.robots = RobotsPolicy(
            self.session,
            config,
            self.limiter,
            self.target_policy,
        )
        self.renderer = _PlaywrightRenderer(config, self.limiter, self.target_policy)

    def __enter__(self) -> PageFetcher:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        """释放 requests 连接池与可能启动的 Chromium。"""

        self.renderer.close()
        self.session.close()

    def _decode(self, data: bytes, headers: Mapping[str, str], encoding: str | None) -> str:
        """按响应声明解码，声明缺失时优先尝试 UTF-8，再回退替换错误字符。"""

        content_type = headers.get("Content-Type", "")
        charset = None
        match = re.search(r"charset=([^;\s]+)", content_type, re.I)
        if match:
            charset = match.group(1).strip('"\'')
        detected = None
        try:
            # requests 的依赖通常包含 charset-normalizer；它可识别未声明的 GBK/GB18030。
            from charset_normalizer import from_bytes

            best = from_bytes(data).best()
            detected = best.encoding if best is not None else None
        except ImportError:
            pass
        # 没有 charset 声明时，requests 可能把 HTML 默认为 ISO-8859-1；检测结果应优先。
        for candidate in (charset, detected, "utf-8", encoding):
            if not candidate:
                continue
            try:
                return data.decode(candidate)
            except (LookupError, UnicodeDecodeError):
                continue
        return data.decode("utf-8", errors="replace")

    def _static_fetch(
        self,
        url: str,
        conditional_headers: Mapping[str, str] | None = None,
        *,
        sitemap: bool = False,
    ) -> FetchedPage:
        """手动处理重定向，以便每个新目标在请求前都经过 robots 检查。"""

        current = canonicalize_url(url)
        original_host = urlsplit(current).hostname if sitemap else None
        for _redirect in range(6):
            if original_host and urlsplit(current).hostname != original_host:
                raise CrawlError(f"站点地图重定向到站外：{current}")
            self.robots.ensure_allowed(current)
            self.limiter.wait(current)
            try:
                response = self.session.get(
                    current,
                    timeout=self.config.request_timeout_seconds,
                    allow_redirects=False,
                    stream=True,
                    headers=(
                        dict(conditional_headers)
                        if _redirect == 0 and conditional_headers is not None
                        else None
                    ),
                )
            except requests.RequestException as exc:
                raise CrawlError(f"网络请求失败：{current}：{exc}") from exc

            with response:
                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        raise CrawlError(f"重定向缺少 Location：{current}")
                    current = normalize_request_url(urljoin(current, location))
                    continue
                if response.status_code == 304:
                    return FetchedPage(
                        url,
                        current,
                        "",
                        False,
                        304,
                        not_modified=True,
                        etag=response.headers.get("ETag"),
                        last_modified=response.headers.get("Last-Modified"),
                    )
                if response.status_code >= 400:
                    raise CrawlError(f"HTTP {response.status_code}：{current}")
                content_type = response.headers.get("Content-Type", "").casefold()
                accepted_types = (
                    ("application/xml", "text/xml", "application/rss+xml", "text/plain")
                    if sitemap
                    else ("text/html", "application/xhtml+xml")
                )
                if content_type and not any(kind in content_type for kind in accepted_types):
                    label = "XML 站点地图" if sitemap else "HTML 页面"
                    raise CrawlError(f"不是{label}（{content_type}）：{current}")

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > self.config.max_download_bytes:
                        raise CrawlError(f"页面超过下载上限：{current}")
                    chunks.append(chunk)
                html = self._decode(b"".join(chunks), response.headers, response.encoding)
                return FetchedPage(
                    url,
                    current,
                    html,
                    False,
                    response.status_code,
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                )
        raise CrawlError(f"重定向次数过多：{url}")

    def fetch_sitemap(self, url: str) -> FetchedPage:
        """经同一 robots、限速和响应大小保护读取 XML，不触发浏览器渲染。"""

        return self._static_fetch(url, sitemap=True)

    def _static_text_length(self, html: str) -> int:
        """计算静态 HTML 的可见正文长度，供渲染判断和失败回退共同使用。"""

        from bs4 import BeautifulSoup

        return len(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))

    def _looks_like_js_shell(self, html: str) -> bool:
        """文本过少或带常见 SPA 空壳标记时，自动尝试浏览器渲染。"""

        text_length = self._static_text_length(html)
        markers = ("__NEXT_DATA__", "id=\"root\"", "id=\"app\"", "webpack")
        return text_length < self.config.min_static_text_chars or (
            text_length < self.config.min_static_text_chars * 3
            and any(marker in html for marker in markers)
        )

    def fetch(
        self,
        url: str,
        conditional_headers: Mapping[str, str] | None = None,
        *,
        wait_selector: str | None = None,
    ) -> FetchedPage:
        """抓取一个页面；Playwright 失败时保留可用的静态 HTML。"""

        static_page = (
            self._static_fetch(url, conditional_headers)
            if conditional_headers
            else self._static_fetch(url)
        )
        if static_page.not_modified:
            return static_page
        if wait_selector and self.config.render_mode == "never":
            raise CrawlError("已配置动态招聘入口等待元素，但 Playwright 渲染已关闭")
        should_render = self.config.render_mode == "always" or (
            self.config.render_mode == "auto"
            and (
                bool(wait_selector)
                or
                is_spa_route(static_page.final_url)
                or self._looks_like_js_shell(static_page.html)
            )
        )
        if not should_render:
            return static_page
        try:
            if wait_selector:
                html, final_url = self.renderer.render(
                    static_page.final_url, wait_selector=wait_selector
                )
            else:
                html, final_url = self.renderer.render(static_page.final_url)
            final_url = canonicalize_url(final_url)
            self.robots.ensure_allowed(final_url)
            return FetchedPage(
                url,
                final_url,
                html,
                True,
                static_page.status_code,
                etag=static_page.etag,
                last_modified=static_page.last_modified,
            )
        except CrawlError as exc:
            if self.config.render_mode == "always" or wait_selector:
                raise
            static_length = self._static_text_length(static_page.html)
            if static_length < self.config.min_static_text_chars:
                raise CrawlError(
                    "Playwright 渲染失败，且静态 HTML 只有 "
                    f"{static_length} 字正文（最低要求 "
                    f"{self.config.min_static_text_chars}），页面可能是 SPA 空壳："
                    f"{static_page.final_url}"
                ) from exc
            LOGGER.warning("Playwright 回退失败，继续使用静态 HTML：%s", static_page.final_url)
            return static_page
