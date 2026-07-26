"""Local API input validation shared by focused route modules."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


def safe_public_url(value: str) -> str:
    """Reject local/private targets so Web forms cannot become an SSRF proxy."""

    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
        raise ValueError("必须填写不含账号密码的公开 HTTP(S) URL")
    hostname = parts.hostname.casefold()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ValueError("不允许监控本机或 .local 地址")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return value
    if not address.is_global:
        raise ValueError("不允许监控私网、回环、链路本地或保留 IP")
    return value
