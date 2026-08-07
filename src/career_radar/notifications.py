"""通过 Apprise 把新增岗位摘要推送到 Telegram、企业微信、钉钉、ntfy 等渠道。"""

from __future__ import annotations

from urllib.parse import urlsplit

from .models import AppriseConfig, StoredJobEvent


class NotificationError(RuntimeError):
    """Apprise 配置或发送失败。"""


def _import_apprise():
    """延迟导入 apprise，未安装时给出可操作的错误提示。"""

    try:
        import apprise
    except ImportError as exc:
        raise NotificationError("未安装 apprise SDK：请执行 pip install apprise") from exc
    return apprise


def _mask_url(value: str) -> str:
    """只显示协议和主机，避免把 token/chat_id 写进错误日志。"""

    try:
        parts = urlsplit(value)
        host = parts.hostname or parts.netloc
        if parts.scheme and host:
            if parts.port:
                host = f"{host}:{parts.port}"
            return f"{parts.scheme}://{host}/…"
    except ValueError:
        pass
    return "<无效 URL>"


def _summary(text: str, limit: int) -> str:
    """推送只放摘要以控制体积；完整 JD 始终保存在本地 Markdown/CSV。"""

    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[:limit].rstrip() + "…"


def _render_events(
    config: AppriseConfig,
    events: list[StoredJobEvent],
    date_text: str,
) -> tuple[str, str]:
    title = f"{config.title_prefix} {date_text} 新岗位 {len(events)} 个"
    lines = [f"本次发现 {len(events)} 个符合通知等级的新/变化岗位。", ""]
    for event in events:
        job = event.job
        summary = _summary(job.description, config.jd_summary_chars)
        link = job.apply_url or job.source_url
        lines.extend(
            [
                f"[{event.event_type}] {job.company}～{job.title}",
                f"地点：{job.location or '未提供'}；类型：{job.recruitment_type or '未提供'}；"
                f"届别匹配：{job.match_level.value}；能力匹配：{job.profile_fit_level.value}",
                f"投递难度：{job.difficulty_score}/10（{job.difficulty_level.value}）；"
                f"依据：{job.difficulty_reason}",
                f"摘要：{summary}",
                f"链接：{link}",
                "",
            ]
        )
    return title, "\n".join(lines)


def send_job_notifications(
    config: AppriseConfig,
    events: list[StoredJobEvent],
    date_text: str,
) -> None:
    """把岗位摘要推送到所有已配置的 Apprise 渠道；失败时抛出 NotificationError。"""

    if not config.enabled:
        return
    apprise = _import_apprise()
    notifier = apprise.Apprise()
    invalid: list[str] = []
    for url in config.urls:
        if not notifier.add(url):
            invalid.append(_mask_url(url))
    if invalid:
        raise NotificationError(f"Apprise URL 无效：{', '.join(invalid)}")

    title, body = _render_events(config, events, date_text)
    try:
        delivered = notifier.notify(
            title=title,
            body=body,
            body_format=apprise.NotifyFormat.TEXT,
        )
    except Exception as exc:
        raise NotificationError(f"Apprise 发送失败：{type(exc).__name__}: {exc}") from exc
    if not delivered:
        raise NotificationError("Apprise 未送达任何渠道，请检查 URL 与网络连接")


def send_test_notification(config: AppriseConfig) -> None:
    """发送不含岗位数据的测试消息，供本地管理端验证 Apprise 配置。"""

    if not config.enabled:
        raise NotificationError("Apprise 尚未启用")
    apprise = _import_apprise()
    notifier = apprise.Apprise()
    invalid: list[str] = []
    for url in config.urls:
        if not notifier.add(url):
            invalid.append(_mask_url(url))
    if invalid:
        raise NotificationError(f"Apprise URL 无效：{', '.join(invalid)}")

    try:
        delivered = notifier.notify(
            title=f"{config.title_prefix} 推送测试",
            body="Career Radar 推送配置有效。这是一条由本地管理端触发的测试消息。",
            body_format=apprise.NotifyFormat.TEXT,
        )
    except Exception as exc:
        raise NotificationError(f"Apprise 发送失败：{type(exc).__name__}: {exc}") from exc
    if not delivered:
        raise NotificationError("Apprise 未送达任何渠道，请检查 URL 与网络连接")
