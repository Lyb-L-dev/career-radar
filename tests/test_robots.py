"""robots.txt 允许、禁止和不可用时的保守行为测试。"""

from typing import Any

import pytest

from career_radar.crawler import RateLimiter, RobotsDeniedError, RobotsPolicy
from career_radar.models import CrawlerConfig


class FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def get(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        return self.response


def _config() -> CrawlerConfig:
    return CrawlerConfig(
        render_mode="never",
        request_delay_min_seconds=0,
        request_delay_max_seconds=0,
        user_agent="Mozilla/5.0 test browser agent",
    )


def test_robots_disallow_is_enforced() -> None:
    policy = RobotsPolicy(
        FakeSession(FakeResponse(200, "User-agent: *\nDisallow: /private")),  # type: ignore[arg-type]
        _config(),
        RateLimiter(0, 0),
    )
    with pytest.raises(RobotsDeniedError):
        policy.ensure_allowed("https://example.com/private/jobs")


def test_missing_robots_allows_public_page() -> None:
    policy = RobotsPolicy(
        FakeSession(FakeResponse(404)),  # type: ignore[arg-type]
        _config(),
        RateLimiter(0, 0),
    )
    policy.ensure_allowed("https://example.com/careers")


def test_server_error_uses_conservative_policy() -> None:
    policy = RobotsPolicy(
        FakeSession(FakeResponse(503)),  # type: ignore[arg-type]
        _config(),
        RateLimiter(0, 0),
    )
    with pytest.raises(RobotsDeniedError):
        policy.ensure_allowed("https://example.com/careers")

