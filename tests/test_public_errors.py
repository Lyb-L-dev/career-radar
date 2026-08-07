"""Privacy boundaries for errors returned by APIs or persisted for polling."""

from __future__ import annotations

from career_radar.public_errors import public_error_message, redact_public_text


def test_redact_public_text_removes_paths_keys_and_contacts() -> None:
    raw = (
        r"E:\AIProjects\work\career-radar\private\profile.yaml "
        "api_key=sk-secret123456789 candidate@example.com 13800000000"
    )

    redacted = redact_public_text(raw)

    assert "E:\\AIProjects" not in redacted
    assert "sk-secret" not in redacted
    assert "candidate@example.com" not in redacted
    assert "13800000000" not in redacted
    assert "[本机路径]" in redacted


def test_expected_error_keeps_safe_actionable_message() -> None:
    message = public_error_message(ValueError("请先登记至少一个公众号"))

    assert message == "请先登记至少一个公众号"


def test_unexpected_error_returns_diagnostic_id_not_raw_exception() -> None:
    message = public_error_message(
        RuntimeError("driver failed at /tmp/private/session.json"),
        context="浏览器检查",
    )

    assert "driver failed" not in message
    assert "/tmp/private" not in message
    assert "诊断编号" in message
