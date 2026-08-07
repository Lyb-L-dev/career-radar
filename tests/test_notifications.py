"""Apprise 多渠道推送的配置与发送测试（不访问真实通知服务）。"""

from types import SimpleNamespace

import pytest

from career_radar.models import (
    AppriseConfig,
    DifficultyLevel,
    JobPosting,
    MatchLevel,
    ProfileFitLevel,
    StoredJobEvent,
)
from career_radar.notifications import (
    NotificationError,
    _mask_url,
    _render_events,
    send_job_notifications,
    send_test_notification,
)


def _event() -> StoredJobEvent:
    return StoredJobEvent(
        event_type="new",
        entity_key="entity-1",
        fingerprint="fp-1",
        detected_at="2026-08-07T08:00:00+08:00",
        job=JobPosting(
            title="后端开发",
            company="甲公司",
            description="负责服务端设计与开发。" + "技术要求。" * 60,
            location="福州",
            apply_url="https://a.example/apply",
            match_level=MatchLevel.HIGH,
            profile_fit_level=ProfileFitLevel.HIGH,
            difficulty_score=6,
            difficulty_level=DifficultyLevel.MEDIUM,
            difficulty_reason="明确 2026 届，岗位与技能匹配",
            recruitment_type="校招",
        ),
    )


def _fake_apprise(notifier: object):
    """返回与真实 apprise 模块接口兼容的桩。"""

    return SimpleNamespace(
        Apprise=lambda: notifier,
        NotifyFormat=SimpleNamespace(TEXT="text"),
    )


def test_render_events_contains_job_summary() -> None:
    config = AppriseConfig(enabled=True, urls=["tgram://bot:token/chat"])
    title, body = _render_events(config, [_event()], "2026-08-07")

    assert "2026-08-07" in title
    assert "甲公司" in body
    assert "https://a.example/apply" in body


def test_disabled_config_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_import() -> None:
        raise AssertionError("禁用时不应导入 apprise")

    monkeypatch.setattr("career_radar.notifications._import_apprise", fail_import)
    send_job_notifications(
        AppriseConfig(enabled=False, urls=[]),
        [_event()],
        "2026-08-07",
    )


def test_invalid_url_raises_and_masks_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier = SimpleNamespace(added=[], notify=lambda **_kwargs: True)
    notifier.add = lambda url: notifier.added.append(url) or url.startswith("ok:")
    monkeypatch.setattr(
        "career_radar.notifications._import_apprise",
        lambda: _fake_apprise(notifier),
    )

    with pytest.raises(NotificationError, match="bad://") as exc:
        send_job_notifications(
            AppriseConfig(enabled=True, urls=["bad://user:secret@host/chat"]),
            [_event()],
            "2026-08-07",
        )
    assert "secret" not in str(exc.value)


def test_notify_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier = SimpleNamespace(add=lambda _url: True, notify=lambda **_kwargs: False)
    monkeypatch.setattr(
        "career_radar.notifications._import_apprise",
        lambda: _fake_apprise(notifier),
    )

    with pytest.raises(NotificationError, match="未送达"):
        send_job_notifications(
            AppriseConfig(enabled=True, urls=["tgram://bot:token/chat"]),
            [_event()],
            "2026-08-07",
        )


def test_send_job_notifications_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class Notifier:
        def add(self, _url: str) -> bool:
            return True

        def notify(self, **kwargs) -> bool:
            calls.append(kwargs)
            return True

    monkeypatch.setattr(
        "career_radar.notifications._import_apprise",
        lambda: _fake_apprise(Notifier()),
    )

    send_job_notifications(
        AppriseConfig(enabled=True, urls=["tgram://bot:token/chat"]),
        [_event()],
        "2026-08-07",
    )
    assert calls
    assert "甲公司" in calls[0]["body"]


def test_test_notification_requires_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_import() -> None:
        raise AssertionError("未启用时不应导入 apprise")

    monkeypatch.setattr("career_radar.notifications._import_apprise", fail_import)
    with pytest.raises(NotificationError, match="尚未启用"):
        send_test_notification(AppriseConfig(enabled=False, urls=[]))


def test_mask_url_hides_query_and_credentials() -> None:
    masked = _mask_url("https://user:pass@example.com/chat?token=abc")
    assert "pass" not in masked
    assert "abc" not in masked
    assert masked.startswith("https://example.com")
