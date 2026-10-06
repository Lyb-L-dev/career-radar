"""历史日报邮件重建与通知筛选。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .mailer import send_job_email
from .models import Settings, SMTPConfig, StoredJobEvent
from .storage import JobStorage

MailSender = Callable[[SMTPConfig, list[StoredJobEvent], str], None]


class ReportDeliveryError(RuntimeError):
    """历史日报无法形成可发送邮件。"""


@dataclass(frozen=True)
class ReportDeliveryResult:
    report_date: str
    event_count: int


def notification_events(
    settings: Settings,
    events: list[StoredJobEvent],
) -> list[StoredJobEvent]:
    """按当前通知策略选择可发送的新增和变化岗位。"""

    notify_levels = set(settings.app.notify_match_levels)
    notify_profile_levels = set(settings.app.notify_profile_fit_levels)
    return [
        event
        for event in events
        if event.event_type in {"new", "updated"}
        and event.job.match_level in notify_levels
        and event.job.profile_fit_level in notify_profile_levels
        and event.job.difficulty_score <= settings.app.notify_max_difficulty_score
    ]


class HistoricalReportDelivery:
    """以 ``deliver`` interface 隐藏历史事件恢复、筛选和 SMTP 投递细节。"""

    def __init__(self, settings: Settings, sender: MailSender | None = None) -> None:
        self.settings = settings
        self.sender = sender or send_job_email

    def deliver(self, date_text: str) -> ReportDeliveryResult:
        try:
            report_date = date.fromisoformat(date_text)
        except ValueError as exc:
            raise ReportDeliveryError("日报日期必须使用 YYYY-MM-DD 格式") from exc
        if report_date.isoformat() != date_text:
            raise ReportDeliveryError("日报日期必须使用 YYYY-MM-DD 格式")
        if not self.settings.smtp.enabled:
            raise ReportDeliveryError("SMTP 尚未启用，请先在设置页完成邮件配置")

        stored_events = JobStorage(
            self.settings.app.database_path
        ).load_events_for_date(report_date)
        selected = notification_events(self.settings, stored_events)
        if not selected:
            raise ReportDeliveryError("当天没有符合当前通知筛选条件的岗位事件")

        self.sender(self.settings.smtp, selected, date_text)
        return ReportDeliveryResult(report_date=date_text, event_count=len(selected))
