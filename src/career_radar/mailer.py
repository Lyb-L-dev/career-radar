"""通过 SMTP 发送只包含指定匹配等级的新增职位摘要。"""

from __future__ import annotations

import html
import os
import smtplib
import ssl
from email.message import EmailMessage

from .models import SMTPConfig, StoredJobEvent


class MailError(RuntimeError):
    """邮件配置或 SMTP 发送失败。"""


def _summary(text: str, limit: int) -> str:
    """邮件只放摘要以控制体积；完整 JD 始终保存在 Markdown/CSV。"""

    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[:limit].rstrip() + "…"


def send_job_email(config: SMTPConfig, events: list[StoredJobEvent], date_text: str) -> None:
    """同时生成纯文本和 HTML 邮件，兼容不同客户端。"""

    password = os.getenv(config.password_env)
    if not password:
        raise MailError(f"缺少 SMTP 密码环境变量：{config.password_env}")

    message = EmailMessage()
    message["Subject"] = f"{config.subject_prefix} {date_text} 新岗位 {len(events)} 个"
    message["From"] = config.from_address
    message["To"] = ", ".join(config.to_addresses)

    plain_lines = [f"本次发现 {len(events)} 个符合通知等级的新/变化岗位。", ""]
    html_items: list[str] = []
    for event in events:
        job = event.job
        summary = _summary(job.description, config.jd_summary_chars)
        link = job.apply_url or job.source_url
        plain_lines.extend(
            [
                f"[{event.event_type}] {job.company}｜{job.title}",
                f"地点：{job.location or '未提供'}；类型：{job.recruitment_type or '未提供'}；"
                f"届别匹配：{job.match_level.value}；能力匹配：{job.profile_fit_level.value}；"
                f"投递难度：{job.difficulty_score}/10（{job.difficulty_level.value}）",
                f"难度依据：{job.difficulty_reason}",
                f"摘要：{summary}",
                f"链接：{link}",
                "",
            ]
        )
        html_items.append(
            "<li>"
            f"<strong>{html.escape(job.company)}｜{html.escape(job.title)}</strong><br>"
            f"地点：{html.escape(job.location or '未提供')}；"
            f"类型：{html.escape(job.recruitment_type or '未提供')}；"
            f"届别匹配：{html.escape(job.match_level.value)}；"
            f"能力匹配：{html.escape(job.profile_fit_level.value)}；"
            f"难度：{job.difficulty_score}/10（{html.escape(job.difficulty_level.value)}）<br>"
            f"难度依据：{html.escape(job.difficulty_reason)}<br>"
            f"摘要：{html.escape(summary)}<br>"
            f'<a href="{html.escape(link, quote=True)}">查看/申请</a>'
            "</li>"
        )
    message.set_content("\n".join(plain_lines))
    message.add_alternative(
        f"<html><body><p>本次发现 {len(events)} 个符合通知等级的新/变化岗位。</p>"
        f"<ol>{''.join(html_items)}</ol></body></html>",
        subtype="html",
    )

    context = ssl.create_default_context()
    try:
        if config.use_ssl:
            with smtplib.SMTP_SSL(config.host, config.port, context=context, timeout=30) as smtp:
                smtp.login(config.username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(config.host, config.port, timeout=30) as smtp:
                if config.use_starttls:
                    smtp.starttls(context=context)
                smtp.login(config.username, password)
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailError(f"SMTP 发送失败：{exc}") from exc


def send_test_email(config: SMTPConfig) -> None:
    """发送不包含岗位数据的测试邮件，供本地 Web 设置页验证 SMTP。"""

    password = os.getenv(config.password_env)
    if not password:
        raise MailError(f"缺少 SMTP 密码环境变量：{config.password_env}")
    if not config.enabled:
        raise MailError("SMTP 尚未启用")

    message = EmailMessage()
    message["Subject"] = f"{config.subject_prefix} SMTP 测试"
    message["From"] = config.from_address
    message["To"] = ", ".join(config.to_addresses)
    message.set_content("Career Radar SMTP 配置有效。这是一封由本地管理端触发的测试邮件。")

    context = ssl.create_default_context()
    try:
        if config.use_ssl:
            with smtplib.SMTP_SSL(config.host, config.port, context=context, timeout=30) as smtp:
                smtp.login(config.username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(config.host, config.port, timeout=30) as smtp:
                if config.use_starttls:
                    smtp.starttls(context=context)
                smtp.login(config.username, password)
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailError(f"SMTP 发送失败：{exc}") from exc
