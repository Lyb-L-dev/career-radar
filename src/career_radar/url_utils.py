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

# 列表页筛选器通常会产生“职位类别 × 城市 × 部门”的大量等价 URL。抓取队列
# 只保留分页和具体岗位标识；原始 URL 仍会保存在页面记录中，不影响审计。
_LIST_FILTER_PARAMETERS = {
    "campus",
    "category",
    "city",
    "department",
    "jobcategory",
    "jobtype",
    "keyword",
    "location",
    "type",
}
_IDENTITY_PARAMETERS = {
    "id",
    "jobid",
    "job_id",
    "positionid",
    "position_id",
    "requisitionid",
    "requisition_id",
}
def resolve_http_url(base_url: str, href: str) -> str | None:
    """把锚点转换为绝对 HTTP(S) URL，并排除脚本、邮件和电话链接。"""

    href = href.strip()
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return None
    absolute, _fragment = urldefrag(urljoin(base_url, href))
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
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, query, "")
    )


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
        (canonical.scheme, canonical.netloc, path, canonical.query, "")
    )


def canonicalize_crawl_url(url: str) -> str:
    """生成抓取队列键，折叠空参数和列表筛选器组合。

    带非空岗位 ID 的详情 URL 原样保留；没有岗位 ID 时移除已知列表筛选器，
    但保留 ``brandCode`` 等站点入口参数，避免把官网入口改写成错误页面。
    """

    canonical = canonicalize_url(url)
    parts = urlsplit(canonical)
    items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if value.strip()
    ]
    has_identity = any(
        key.casefold() in _IDENTITY_PARAMETERS and value.strip() for key, value in items
    )
    if has_identity:
        kept = items
    else:
        kept = [
            (key, value)
            for key, value in items
            if key.casefold() not in _LIST_FILTER_PARAMETERS
        ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(sorted(kept), doseq=True), "")
    )


def crawl_path_key(url: str) -> str:
    """返回不含查询参数的站点路径键，用于限制单路径参数变体数量。"""

    parts = urlsplit(canonicalize_url(url))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def origin_of(url: str) -> str:
    """返回 ``scheme://host``，用于 robots.txt 缓存和按站点限速。"""

    parts = urlsplit(url)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"
