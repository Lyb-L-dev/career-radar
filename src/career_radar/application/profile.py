"""私有申请画像的 YAML 加载与安全摘要。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import ApplicationProfile


class ApplicationProfileError(ValueError):
    """申请画像缺失、格式错误或未通过严格模型校验。"""


def load_application_profile(path: str | Path) -> ApplicationProfile:
    """加载私有画像；错误信息不回显联系方式等原始 YAML 内容。"""

    profile_path = Path(path).expanduser().resolve()
    if not profile_path.is_file():
        raise ApplicationProfileError(f"找不到私有申请画像：{profile_path}")
    try:
        raw: Any = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ApplicationProfileError(f"读取私有申请画像失败：{type(exc).__name__}") from exc
    if not isinstance(raw, dict):
        raise ApplicationProfileError("私有申请画像顶层必须是 YAML 对象")
    try:
        return ApplicationProfile.model_validate(raw)
    except ValidationError as exc:
        raise ApplicationProfileError(f"私有申请画像校验失败：\n{exc}") from exc


def profile_summary(profile: ApplicationProfile) -> dict[str, object]:
    """返回不含姓名、电话、邮箱和文件路径的 CLI/API 安全摘要。"""

    return {
        "schemaVersion": profile.schema_version,
        "verificationStatus": profile.verification_status.value,
        "educationCount": len(profile.education),
        "experienceCount": len(profile.experiences),
        "projectCount": len(profile.projects),
        "skillCount": len(profile.skills),
        "awardCount": len(profile.awards),
        "leadershipCount": len(profile.leadership),
        "sourceCount": len(profile.sources),
        # 自由文本备注可能被用户写入联系方式，因此公开摘要只返回数量。
        "reviewNoteCount": len(profile.review_notes),
    }


def profile_llm_context(profile: ApplicationProfile) -> dict[str, object]:
    """构造可发送给 LLM 的脱敏事实库。

    姓名、电话、邮箱、主页、来源文件路径和自由备注都不参与模型调用。材料渲染阶段
    再从本机画像确定性注入联系方式，避免敏感信息进入第三方模型日志。
    """

    projects = []
    for item in profile.projects:
        payload = item.model_dump(mode="json")
        # 项目主页可能含真实姓名或个人账号；生成正文不需要让模型访问或复述链接。
        payload.pop("links", None)
        projects.append(payload)
    return {
        "education": [item.model_dump(mode="json") for item in profile.education],
        "experiences": [item.model_dump(mode="json") for item in profile.experiences],
        "projects": projects,
        "skills": [item.model_dump(mode="json") for item in profile.skills],
        "awards": [item.model_dump(mode="json") for item in profile.awards],
        "leadership": [item.model_dump(mode="json") for item in profile.leadership],
        "preferences": profile.preferences.model_dump(mode="json"),
        "allowed_source_ids": [source.id for source in profile.sources],
    }
