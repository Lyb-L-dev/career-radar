"""Public-network target validation shared by APIs and outbound crawlers."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit


class UnsafeTargetError(ValueError):
    """A URL is not a valid public HTTP(S) target."""


AddressResolver = Callable[[str, int], Iterable[str]]


def _system_resolver(hostname: str, port: int) -> list[str]:
    """Resolve all stream addresses without opening an application connection."""

    records = socket.getaddrinfo(
        hostname,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
    )
    return list(dict.fromkeys(str(record[4][0]) for record in records))


@dataclass(frozen=True, slots=True)
class ValidatedTarget:
    """Normalized validation result useful to diagnostics and tests."""

    url: str
    hostname: str
    port: int
    addresses: tuple[str, ...] = ()


class PublicTargetPolicy:
    """Reject local and non-global HTTP targets, including DNS answers."""

    def __init__(self, resolver: AddressResolver = _system_resolver) -> None:
        self._resolver = resolver

    @staticmethod
    def _parse(value: str) -> tuple[str, str, int]:
        value = value.strip()
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
        ):
            raise UnsafeTargetError("必须填写不含账号密码的公开 HTTP(S) URL")
        try:
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError as exc:
            raise UnsafeTargetError("URL 端口无效") from exc

        hostname = parts.hostname.casefold().rstrip(".")
        if (
            hostname in {"localhost", "localhost.localdomain"}
            or hostname.endswith(".localhost")
            or hostname.endswith(".local")
        ):
            raise UnsafeTargetError("不允许监控本机或 .local 地址")
        return value, hostname, port

    @staticmethod
    def _ensure_global(address: str) -> str:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeTargetError("域名解析结果不是有效 IP 地址") from exc
        if not parsed.is_global:
            raise UnsafeTargetError("不允许监控私网、回环、链路本地或保留 IP")
        return parsed.compressed

    def validate(self, value: str, *, resolve: bool = True) -> ValidatedTarget:
        """Validate syntax and, by default, every A/AAAA answer."""

        url, hostname, port = self._parse(value)
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            literal = None
        if literal is not None:
            return ValidatedTarget(
                url=url,
                hostname=hostname,
                port=port,
                addresses=(self._ensure_global(hostname),),
            )
        if not resolve:
            return ValidatedTarget(url=url, hostname=hostname, port=port)

        try:
            resolved = tuple(
                dict.fromkeys(
                    self._ensure_global(address)
                    for address in self._resolver(hostname, port)
                )
            )
        except (OSError, UnicodeError) as exc:
            raise UnsafeTargetError("域名暂时无法解析为公开地址") from exc
        if not resolved:
            raise UnsafeTargetError("域名没有可用的公开地址")
        return ValidatedTarget(
            url=url,
            hostname=hostname,
            port=port,
            addresses=resolved,
        )

    def ensure_public(self, value: str) -> str:
        """Return the original URL after full public-network validation."""

        return self.validate(value, resolve=True).url
