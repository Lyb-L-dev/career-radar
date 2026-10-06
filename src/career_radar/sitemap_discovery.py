"""从官方站点地图发现招聘页；网络请求仍由 Career Radar 的安全抓取器执行。"""

from __future__ import annotations

import logging
import re
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import unquote, urlsplit

from lxml import etree

from .crawler import CrawlError, FetchedPage
from .url_utils import canonicalize_crawl_url, origin_of

LOGGER = logging.getLogger(__name__)
_RECRUITMENT_TERMS = (
    "career", "recruit", "campus", "graduate", "job", "position", "join-us",
    "/join/", "talent", "hiring", "vacancy", "招聘", "校招", "招贤", "招考",
)
_MAX_SITEMAPS = 3
_MAX_RECRUITMENT_URLS = 20
_XML_DECLARATION = re.compile(r"^\s*<\?xml[^>]*\?>", re.I)


class SitemapFetcher(Protocol):
    def fetch_sitemap(self, url: str) -> FetchedPage: ...


@dataclass(frozen=True, slots=True)
class SitemapLinks:
    pages: tuple[str, ...]
    sitemaps: tuple[str, ...]


def _same_official_host(url: str, host: str) -> str | None:
    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme not in {"http", "https"} or parsed.hostname != host:
            return None
        if parsed.username or parsed.password:
            return None
        return canonicalize_crawl_url(url.strip())
    except ValueError:
        return None


def parse_sitemap_xml(content: str, host: str) -> SitemapLinks:
    """只接受规范 urlset/sitemapindex 的直接 loc，不处理实体和跨域链接。"""

    if not content or len(content) > 10_000_000:
        raise ValueError("站点地图为空或超过解析上限")
    if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
        raise ValueError("站点地图不接受 DTD 或实体声明")
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    try:
        root = etree.fromstring(_XML_DECLARATION.sub("", content).encode("utf-8"), parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError("站点地图 XML 格式无效") from exc
    root_name = etree.QName(root).localname
    if root_name not in {"urlset", "sitemapindex"}:
        raise ValueError("不是 urlset 或 sitemapindex")
    item_name = "url" if root_name == "urlset" else "sitemap"
    locations: list[str] = []
    for item in root:
        if not isinstance(item.tag, str) or etree.QName(item).localname != item_name:
            continue
        loc = next(
            (
                child.text
                for child in item
                if isinstance(child.tag, str) and etree.QName(child).localname == "loc"
            ),
            None,
        )
        if loc and (url := _same_official_host(loc, host)) and url not in locations:
            locations.append(url)
    return (
        SitemapLinks(tuple(locations), ())
        if root_name == "urlset"
        else SitemapLinks((), tuple(locations))
    )


def _is_recruitment_url(url: str) -> bool:
    parsed = urlsplit(url)
    searchable = unquote(f"{parsed.path}?{parsed.query}").casefold()
    return any(term in searchable for term in _RECRUITMENT_TERMS)


def discover_recruitment_urls(
    start_url: str,
    fetcher: SitemapFetcher,
    *,
    sitemap_hints: tuple[str, ...] = (),
    should_cancel: Callable[[], bool] | None = None,
) -> list[str]:
    """优先官方 robots 声明，回退常见地址；文件和候选页数均有硬上限。"""

    host = urlsplit(start_url).hostname
    if not host:
        return []
    roots = sitemap_hints or (f"{origin_of(start_url)}/sitemap.xml",)
    sitemap_queue = deque(
        url for value in roots if (url := _same_official_host(value, host)) is not None
    )
    seen_sitemaps: set[str] = set()
    found: list[str] = []
    while sitemap_queue and len(seen_sitemaps) < _MAX_SITEMAPS:
        if should_cancel and should_cancel():
            return found
        sitemap_url = sitemap_queue.popleft()
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            page = fetcher.fetch_sitemap(sitemap_url)
            if urlsplit(page.final_url).hostname != host:
                continue
            links = parse_sitemap_xml(page.html, host)
        except (CrawlError, ValueError) as exc:
            LOGGER.debug("可选站点地图不可用 %s：%s", sitemap_url, exc)
            continue
        for url in links.pages:
            if _is_recruitment_url(url) and url not in found:
                found.append(url)
                if len(found) >= _MAX_RECRUITMENT_URLS:
                    return found
        children = sorted(links.sitemaps, key=lambda value: not _is_recruitment_url(value))
        sitemap_queue.extend(url for url in children if url not in seen_sitemaps)
    return found
