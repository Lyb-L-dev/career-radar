"""robots.txt 允许、禁止和不可用时的保守行为测试。"""

from typing import Any

import pytest

from career_radar.crawler import RateLimiter, RobotsDeniedError, RobotsPolicy
from career_radar.models import CrawlerConfig
from career_radar.network_policy import PublicTargetPolicy


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def close(self) -> None:
        pass


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls = 0

    def get(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        self.calls += 1
        return self.response


def _config() -> CrawlerConfig:
    return CrawlerConfig(
        render_mode="never",
        request_delay_min_seconds=0,
        request_delay_max_seconds=0,
        user_agent="Mozilla/5.0 test browser agent",
    )


def _public_policy() -> PublicTargetPolicy:
    return PublicTargetPolicy(lambda _host, _port: ["93.184.216.34"])


def test_robots_disallow_is_enforced() -> None:
    policy = RobotsPolicy(
        FakeSession(FakeResponse(200, "User-agent: *\nDisallow: /private")),  # type: ignore[arg-type]
        _config(),
        RateLimiter(0, 0),
        _public_policy(),
    )
    with pytest.raises(RobotsDeniedError):
        policy.ensure_allowed("https://example.com/private/jobs")


def test_missing_robots_allows_public_page() -> None:
    policy = RobotsPolicy(
        FakeSession(FakeResponse(404)),  # type: ignore[arg-type]
        _config(),
        RateLimiter(0, 0),
        _public_policy(),
    )
    policy.ensure_allowed("https://example.com/careers")


def test_server_error_uses_conservative_policy() -> None:
    policy = RobotsPolicy(
        FakeSession(FakeResponse(503)),  # type: ignore[arg-type]
        _config(),
        RateLimiter(0, 0),
        _public_policy(),
    )
    with pytest.raises(RobotsDeniedError):
        policy.ensure_allowed("https://example.com/careers")


def test_robots_redirect_to_private_network_is_denied() -> None:
    policy = RobotsPolicy(
        FakeSession(
            FakeResponse(302, headers={"Location": "http://127.0.0.1/robots.txt"})
        ),  # type: ignore[arg-type]
        _config(),
        RateLimiter(0, 0),
        _public_policy(),
    )

    with pytest.raises(RobotsDeniedError):
        policy.ensure_allowed("https://example.com/careers")


def test_robots_sitemap_declaration_is_reused_without_second_request() -> None:
    session = FakeSession(
        FakeResponse(
            200,
            "User-agent: *\nAllow: /\nSitemap: https://example.com/careers.xml\n",
        )
    )
    policy = RobotsPolicy(session, _config(), RateLimiter(0, 0), _public_policy())  # type: ignore[arg-type]

    policy.ensure_allowed("https://example.com/")

    assert policy.sitemaps_for("https://example.com/") == (
        "https://example.com/careers.xml",
    )
    assert session.calls == 1
