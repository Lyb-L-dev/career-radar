"""URL 规范化与安全的相对链接解析。"""

from __future__ import annotations

from urllib.parse import parse_qsl, urldefrag, urlencode, urljoin, urlsplit, urlunsplit

_TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "spm",
}

def is_spa_route(url: str) -> bool:
    """Hash-router paths select different views; ordinary page anchors do not."""

    return urlsplit(url).fragment.startswith(("/", "!/"))


def resolve_http_url(base_url: str, href: str) -> str | None:
    """把锚点转换为绝对 HTTP(S) URL，并排除脚本、邮件和电话链接。"""

    href = href.strip()
    if not href or href.startswith(("javascript:", "mailto:", "tel:", "data:")):
        return None
    if href.startswith("#") and not is_spa_route(href):
        return None
    absolute = urljoin(base_url, href)
    if not is_spa_route(absolute):
        absolute, _fragment = urldefrag(absolute)
    parts = urlsplit(absolute)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return None
    return absolute


def canonicalize_url(url: str) -> str:
    """生成去重 URL。

    只删除公认的广告追踪参数，保留 ``jobId``、``requisition`` 等可能决定
    具体岗位的查询参数；查询参数排序后，同一链接不会因参数顺序不同而重复抓取。
    """

    parts = urlsplit(url)
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMETERS
    ]
    query = urlencode(sorted(query_items), doseq=True)
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    fragment = parts.fragment if is_spa_route(url) else ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, fragment))


def normalize_request_url(url: str) -> str:
    """规范请求 URL，但保留服务端明确给出的目录尾斜杠。

    去重键可把 ``/careers`` 与 ``/careers/`` 视为同一页面；实际 HTTP 请求却
    必须尊重重定向 Location 中的尾斜杠，否则部分政府网站会在两者之间循环。
    """

    original = urlsplit(url)
    canonical = urlsplit(canonicalize_url(url))
    path = canonical.path
    if original.path.endswith("/") and original.path != "/" and not path.endswith("/"):
        path += "/"
    return urlunsplit(
        (canonical.scheme, canonical.netloc, path, canonical.query, canonical.fragment)
    )


def canonicalize_crawl_url(url: str) -> str:
    """生成抓取队列键，保留决定岗位列表内容的筛选条件与 SPA 路由。

    空参数和广告参数仍可去掉；同路径不同条件的抓取数量由流水线限制，
    不在请求前改写站点的职位类别、校招或城市条件。
    """

    canonical = canonicalize_url(url)
    parts = urlsplit(canonical)
    items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if value.strip()
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(sorted(items), doseq=True), parts.fragment)
    )


def crawl_path_key(url: str) -> str:
    """返回不含查询参数的站点路径键，用于限制单路径参数变体数量。"""

    parts = urlsplit(canonicalize_url(url))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def origin_of(url: str) -> str:
    """返回 ``scheme://host``，用于 robots.txt 缓存和按站点限速。"""

    parts = urlsplit(url)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"
