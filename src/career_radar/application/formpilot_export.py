"""把已确认的私有申请画像转换为 FormPilot 1.2.1 的导入格式。

FormPilot 是独立浏览器扩展；这里只生成它的 JSON 资料，不运行扩展代码，
也不接触招聘站点。未证实的字段保持为空，交由用户在官网表单中填写。
"""

from __future__ import annotations

import re
from typing import Any

from .models import ApplicationProfile

_PROGRAMMING_LANGUAGES = frozenset(
    {"python", "java", "javascript", "typescript", "c", "c++", "c#", "go", "golang", "rust", "swift", "kotlin", "php", "ruby", "r", "scala", "matlab", "sql"}
)


def _month(value: str | None) -> str:
    """FormPilot 的日期字段使用 YYYY-MM；无法确认的日期不猜测。"""

    if not value:
        return ""
    match = re.fullmatch(r"\s*(20\d{2})[.\-/年](0?[1-9]|1[0-2])(?:月)?\s*", value)
    return f"{match.group(1)}-{int(match.group(2)):02d}" if match else ""


def _prose(*parts: str | list[str]) -> str:
    lines: list[str] = []
    for part in parts:
        lines.extend(part if isinstance(part, list) else [part])
    return "\n".join(line.strip() for line in lines if line.strip())


def to_formpilot_resume(profile: ApplicationProfile) -> dict[str, Any]:
    """只映射画像中已有事实；联系方式用上游已测试的字符串导入兼容层。"""

    contact = profile.contact
    skills = [item.name.strip() for item in profile.skills if item.name.strip()]
    languages = [item for item in skills if item.casefold() in _PROGRAMMING_LANGUAGES]
    tools = [item for item in skills if item not in languages]
    accepted_types = profile.preferences.accepted_work_types

    return {
        "meta": {"name": "Career Radar 私有画像"},
        "basic": {
            "name": contact.name,
            "phone": contact.phone,
            "email": contact.email,
            "location": contact.location or "",
            "socialLinks": {
                key: value
                for key, value in {"github": contact.github, "linkedin": contact.linkedin}.items()
                if value
            },
        },
        "education": [
            {
                "school": item.institution,
                "schoolEn": "",
                "degree": item.degree,
                "major": item.major,
                "majorEn": "",
                "gpa": item.gpa or "",
                "gpaScale": "",
                "startDate": _month(item.start_date),
                "endDate": _month(item.end_date),
                "honors": [],
            }
            for item in profile.education
        ],
        "work": [
            {
                "company": item.organization,
                "companyEn": "",
                "title": item.role,
                "titleEn": "",
                "department": "",
                "startDate": _month(item.start_date),
                "endDate": _month(item.end_date),
                "description": _prose(item.responsibilities, item.achievements),
                "location": item.location or "",
            }
            for item in profile.experiences
        ],
        "projects": [
            {
                "name": item.name,
                "role": "",
                "startDate": _month(item.start_date),
                "endDate": _month(item.end_date),
                "description": _prose(item.description, item.responsibilities),
                "techStack": item.technologies,
                "link": item.links[0] if item.links else "",
            }
            for item in profile.projects
        ],
        "skills": {"languages": languages, "tools": tools, "certificates": []},
        "jobPreference": {
            "positions": profile.preferences.target_roles,
            "industries": [],
            "salaryRange": "",
            "jobType": accepted_types[0] if len(accepted_types) == 1 else "",
            "availableDate": "",
        },
        "custom": [],
    }
