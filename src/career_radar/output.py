"""把新增/变化职位写入按日期归档的 Markdown 与 Excel 友好 CSV。"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .models import StoredJobEvent

_LEVEL_LABELS = {"high": "高", "medium": "中", "low": "低"}
_PROFILE_LABELS = {"high": "高", "medium": "中", "low": "低", "unknown": "信息不足"}
_DIFFICULTY_LABELS = {"low": "低", "medium": "中", "high": "高", "very_high": "很高"}
_EVENT_LABELS = {"new": "新增", "updated": "更新", "preview": "预览"}


def _single_line(value: str | None) -> str:
    return " ".join((value or "未提供").split())


def _csv_safe(value: object) -> object:
    """防止职位文本被 Excel 当成公式执行，同时保留普通换行和中文。"""

    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


class ReportWriter:
    """同一天多次运行时追加检测批次，避免覆盖早些时候发现的岗位。"""

    CSV_FIELDS = [
        "detected_at",
        "event_type",
        "record_type",
        "match_level",
        "profile_fit_level",
        "difficulty_level",
        "difficulty_score",
        "company",
        "title",
        "location",
        "recruitment_type",
        "is_2026_target",
        "target_graduates",
        "published_at",
        "valid_until",
        "jd_complete",
        "jd_incomplete_reason",
        "contact_email",
        "application_method",
        "apply_url",
        "source_url",
        "match_reason",
        "profile_fit_reason",
        "difficulty_reason",
        "description",
        "requirements",
        "fingerprint",
    ]

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_daily(
        self,
        events: list[StoredJobEvent],
        errors: list[str],
        now: datetime,
        *,
        write_empty: bool,
    ) -> tuple[Path | None, Path | None]:
        """写入当日日报；没有新内容且未要求空报表时不创建文件。"""

        if not events and not write_empty:
            return None, None
        date_name = now.strftime("%Y-%m-%d")
        markdown_path = self.output_dir / f"{date_name}-jobs.md"
        csv_path = self.output_dir / f"{date_name}-jobs.csv"
        self._append_markdown(markdown_path, events, errors, now)
        if events:
            self._append_csv(csv_path, events)
            return markdown_path, csv_path
        return markdown_path, None

    def _append_markdown(
        self,
        path: Path,
        events: list[StoredJobEvent],
        errors: list[str],
        now: datetime,
    ) -> None:
        """Markdown 保存完整 JD；邮件中的摘要不会影响本地归档。"""

        is_new_file = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            if is_new_file:
                handle.write(f"# {now:%Y-%m-%d} 企业官网招聘监控日报\n\n")
            else:
                handle.write("\n---\n\n")
            handle.write(f"## 检测批次 {now:%H:%M:%S}\n\n")
            new_count = sum(event.event_type == "new" for event in events)
            updated_count = sum(event.event_type == "updated" for event in events)
            notice_count = sum(event.job.record_type == "notice" for event in events)
            handle.write(
                f"发现新增记录 **{new_count}** 个，更新记录 **{updated_count}** 个，"
                f"其中官方招聘通知 **{notice_count}** 个。\n\n"
            )
            if errors:
                handle.write("### 本批次异常（其他公司仍已继续运行）\n\n")
                for error in errors:
                    handle.write(f"- {_single_line(error)}\n")
                handle.write("\n")
            for index, event in enumerate(events, 1):
                job = event.job
                event_label = _EVENT_LABELS.get(event.event_type, event.event_type)
                level = _LEVEL_LABELS[job.match_level.value]
                profile_level = _PROFILE_LABELS[job.profile_fit_level.value]
                difficulty = _DIFFICULTY_LABELS[job.difficulty_level.value]
                handle.write(
                    f"### {index}. [{event_label}]"
                    f"[{'招聘通知' if job.record_type == 'notice' else '具体岗位'}]"
                    f"[届别：{level}][能力：{profile_level}]"
                    f"[难度：{job.difficulty_score}/10-{difficulty}] "
                    f"{_single_line(job.company)}｜{_single_line(job.title)}\n\n"
                )
                handle.write(f"- 工作地点：{_single_line(job.location)}\n")
                handle.write(f"- 招聘类型：{_single_line(job.recruitment_type)}\n")
                handle.write(f"- 面向 2026 届：{job.is_2026_target if job.is_2026_target is not None else '未明确'}\n")
                handle.write(f"- 目标毕业届别：{_single_line(job.target_graduates)}\n")
                handle.write(f"- 发布时间：{_single_line(job.published_at)}\n")
                handle.write(f"- 有效期：{_single_line(job.valid_until)}\n")
                handle.write(
                    f"- JD 完整性：{'完整' if job.jd_complete else '不完整'}"
                    f"（{_single_line(job.jd_incomplete_reason) if not job.jd_complete else '已进入详情页或正文信息充分'}）\n"
                )
                handle.write(f"- 投递方式：{_single_line(job.application_method)}\n")
                handle.write(f"- 联系邮箱：{_single_line(job.contact_email)}\n")
                handle.write(f"- 届别匹配理由：{_single_line(job.match_reason)}\n")
                handle.write(f"- 能力匹配理由：{_single_line(job.profile_fit_reason)}\n")
                handle.write(
                    f"- 投递难度：{job.difficulty_score}/10（{difficulty}），"
                    f"{_single_line(job.difficulty_reason)}\n"
                )
                if job.apply_url:
                    handle.write(f"- [申请链接]({job.apply_url})\n")
                handle.write(f"- [来源页面]({job.source_url})\n")
                handle.write(f"- 去重指纹：`{event.fingerprint}`\n\n")
                handle.write(
                    "#### 招聘通知全文\n\n"
                    if job.record_type == "notice"
                    else "#### JD 全文\n\n"
                )
                handle.write((job.description or "页面未提供完整 JD，请打开来源页面查看。") + "\n\n")
                handle.write("#### 任职资格\n\n")
                handle.write((job.requirements or "页面未单独提供任职资格。") + "\n\n")

    def _append_csv(self, path: Path, events: list[StoredJobEvent]) -> None:
        """使用 UTF-8 BOM，Windows Excel 双击打开时中文不会乱码。"""

        needs_header = not path.exists() or path.stat().st_size == 0
        fieldnames = self.CSV_FIELDS
        if not needs_header:
            # 当天早些批次可能由旧版本生成。沿用旧表头可避免升级后追加行列错位；
            # 下一自然日的新文件会自动使用包含 record_type 的新表头。
            with path.open("r", encoding="utf-8-sig", newline="") as existing:
                old_header = next(csv.reader(existing), [])
            if old_header:
                fieldnames = old_header
        with path.open("a", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            if needs_header:
                writer.writeheader()
            for event in events:
                job = event.job
                row = {
                    "detected_at": event.detected_at,
                    "event_type": event.event_type,
                    "record_type": job.record_type,
                    "match_level": job.match_level.value,
                    "profile_fit_level": job.profile_fit_level.value,
                    "difficulty_level": job.difficulty_level.value,
                    "difficulty_score": job.difficulty_score,
                    "company": job.company,
                    "title": job.title,
                    "location": job.location,
                    "recruitment_type": job.recruitment_type,
                    "is_2026_target": job.is_2026_target,
                    "target_graduates": job.target_graduates,
                    "published_at": job.published_at,
                    "valid_until": job.valid_until,
                    "jd_complete": job.jd_complete,
                    "jd_incomplete_reason": job.jd_incomplete_reason,
                    "contact_email": job.contact_email,
                    "application_method": job.application_method,
                    "apply_url": job.apply_url,
                    "source_url": job.source_url,
                    "match_reason": job.match_reason,
                    "profile_fit_reason": job.profile_fit_reason,
                    "difficulty_reason": job.difficulty_reason,
                    "description": job.description,
                    "requirements": job.requirements,
                    "fingerprint": event.fingerprint,
                }
                writer.writerow({key: _csv_safe(value) for key, value in row.items()})
