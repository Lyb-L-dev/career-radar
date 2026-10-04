"""本地管理端的 Host 与浏览器写请求来源保护。"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_TRUSTED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "testserver"})


def _normalized_origin(value: str) -> str | None:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme.casefold()}://{parsed.netloc.casefold()}"


def _hostname(host_header: str) -> str | None:
    try:
        return urlsplit(f"//{host_header}").hostname
    except ValueError:
        return None


class LocalRequestGuardMiddleware:
    """把本地管理端的网络假设集中为一个可测试的深模块。"""

    def __init__(self, app: ASGIApp, allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.allowed_origins = frozenset(
            origin
            for value in allowed_origins
            if (origin := _normalized_origin(value)) is not None
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        host_header = headers.get("host", "")
        host = _hostname(host_header)
        if host is None or host.casefold() not in _TRUSTED_HOSTS:
            await JSONResponse(
                {"detail": "本地管理端只接受来自本机地址的请求"},
                status_code=400,
            )(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET")).upper()
        if path.startswith("/api/") and method in _MUTATING_METHODS:
            source = headers.get("origin")
            if source is None:
                referer = headers.get("referer")
                source = _normalized_origin(referer) if referer else None
            else:
                source = _normalized_origin(source)

            request_origin = _normalized_origin(
                f"{scope.get('scheme', 'http')}://{host_header}"
            )
            allowed = self.allowed_origins | ({request_origin} if request_origin else set())
            if source is not None and source not in allowed:
                await JSONResponse(
                    {"detail": "已拒绝非本地页面发起的写操作"},
                    status_code=403,
                )(scope, receive, send)
                return

        await self.app(scope, receive, send)
