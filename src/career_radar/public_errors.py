"""Consistent redaction for errors persisted or returned by the local API."""

from __future__ import annotations

import re
import tempfile
import uuid
from pathlib import Path

_PUBLIC_EXCEPTION_NAMES = {
    "ApplicationConflictError",
    "ApplicationProfileError",
    "ConfigError",
    "CrawlError",
    "DocumentRenderError",
    "FatalLLMError",
    "LLMError",
    "MailError",
    "OpenCLIError",
    "ReputationConflictError",
    "RetryableLLMError",
    "RobotsDeniedError",
    "RunConflictError",
    "TaskCoordinatorClosed",
    "UnsafeTargetError",
    "WechatRecruitmentError",
}


def redact_public_text(value: object, limit: int = 600) -> str:
    """Remove common local paths, credentials and personal contact fragments."""

    text = str(value or "")
    for root in {str(Path.home()), tempfile.gettempdir()}:
        if root:
            text = re.sub(re.escape(root), "[本机路径]", text, flags=re.IGNORECASE)
    substitutions = (
        (r"(?i)\b[A-Z]:[\\/](?:[^\\/\s:]+[\\/])*[^\\/\s:]*", "[本机路径]"),
        (r"(?i)/(?:home|users|tmp|var/tmp)/[^\s,;，。]+", "[本机路径]"),
        (r"(?i)\bsk-[A-Za-z0-9_-]{8,}\b", "[已隐藏密钥]"),
        (
            r"(?i)\b(?:api[_-]?key|authorization|token|password)\s*[:=]\s*\S+",
            "[已隐藏凭据]",
        ),
        (
            r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            "[已隐藏邮箱]",
        ),
        (r"\b1[3-9]\d{9}\b", "[已隐藏手机号]"),
    )
    for pattern, replacement in substitutions:
        text = re.sub(pattern, replacement, text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def public_error_message(
    exc: BaseException,
    *,
    context: str = "操作",
    limit: int = 600,
) -> str:
    """Return an actionable safe message, keeping raw exceptions in logs only."""

    name = type(exc).__name__
    message = redact_public_text(exc, limit=limit)
    if isinstance(exc, ValueError) or name in _PUBLIC_EXCEPTION_NAMES:
        return message or f"{context}未完成"
    if isinstance(exc, TimeoutError) or name == "TimeoutExpired":
        return f"{context}超时，请稍后重试"
    trace_id = uuid.uuid4().hex[:10]
    return f"{context}未完成，请查看本地日志。诊断编号：{trace_id}"

