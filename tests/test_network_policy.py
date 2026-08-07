"""Offline tests for outbound public-network target validation."""

from __future__ import annotations

import pytest

from career_radar.network_policy import PublicTargetPolicy, UnsafeTargetError


def test_public_target_policy_accepts_all_global_dns_answers() -> None:
    policy = PublicTargetPolicy(
        lambda hostname, port: (
            ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"]
            if (hostname, port) == ("example.com", 443)
            else []
        )
    )

    target = policy.validate("https://example.com/jobs")

    assert target.hostname == "example.com"
    assert target.port == 443
    assert target.addresses == (
        "93.184.216.34",
        "2606:2800:220:1:248:1893:25c8:1946",
    )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.8",
        "169.254.1.1",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_public_target_policy_rejects_non_global_dns_answer(address: str) -> None:
    policy = PublicTargetPolicy(lambda _hostname, _port: [address])

    with pytest.raises(UnsafeTargetError, match="不允许监控"):
        policy.validate("https://careers.example.com/jobs")


def test_public_target_policy_rejects_mixed_public_and_private_answers() -> None:
    policy = PublicTargetPolicy(
        lambda _hostname, _port: ["93.184.216.34", "127.0.0.1"]
    )

    with pytest.raises(UnsafeTargetError, match="不允许监控"):
        policy.validate("https://example.com/jobs")


def test_public_target_policy_rejects_credentials_and_invalid_ports() -> None:
    policy = PublicTargetPolicy(lambda _hostname, _port: ["93.184.216.34"])

    with pytest.raises(UnsafeTargetError, match="账号密码"):
        policy.validate("https://user:secret@example.com/jobs")
    with pytest.raises(UnsafeTargetError, match="端口"):
        policy.validate("https://example.com:99999/jobs")


def test_public_target_policy_rejects_localhost_subdomains_without_dns() -> None:
    policy = PublicTargetPolicy(
        lambda _hostname, _port: pytest.fail("localhost must not reach DNS")
    )

    with pytest.raises(UnsafeTargetError, match="本机"):
        policy.validate("http://service.localhost/admin")
