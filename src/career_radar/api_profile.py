"""候选人公开画像的读取、转换与安全写回路由。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .config_editor import update_config_blocks
from .models import CandidateProfile
from .web_repository import WebRepository


class SkillPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    level: str = Field(pattern=r"^(了解|熟悉|熟练)$")


class ProjectPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=10_000)
    skills: list[str] = Field(default_factory=list)


class ProfilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gradYear: str
    degree: str
    schoolBackground: str
    major: str
    targetRoles: list[str]
    cities: list[str]
    salaryRange: list[int] = Field(min_length=2, max_length=2)
    acceptInternship: bool
    acceptRelocation: bool
    maxDifficulty: int = Field(ge=1, le=10)
    workTypes: list[str]
    skills: list[SkillPayload]
    projects: list[ProjectPayload]
    internships: list[str]
    excludedDirections: list[str]
    notes: str = ""
    completeness: int = Field(default=0, ge=0, le=100)
    studentStatus: str | None = Field(default=None, pattern=r"^(unknown|enrolled|graduated)$")
    graduationMonth: str | None = Field(default=None, pattern=r"^20\d{2}-(?:0[1-9]|1[0-2])$")
    formalWorkYears: float | None = Field(default=None, ge=0, le=60)
    educationMode: str | None = Field(default=None, pattern=r"^(unknown|full_time|part_time)$")
    rankingFocus: list[str] | None = None


def profile_json(candidate: CandidateProfile) -> dict[str, Any]:
    """把内部画像压缩成不含私有联系方式的稳定前端模型。"""

    skills = [
        {
            "name": name,
            "level": candidate.skill_levels.get(
                name,
                "了解" if any(word in name for word in ("基础", "认知", "了解")) else "熟悉",
            ),
        }
        for name in candidate.skills
    ]
    projects = []
    for index, value in enumerate(candidate.projects, 1):
        name, separator, description = value.partition("：")
        if not separator:
            name, separator, description = value.partition(":")
        if not separator:
            name, description = f"项目 {index}", value
        matched_skills = [skill["name"] for skill in skills if skill["name"] in value]
        projects.append(
            {
                "id": f"project-{index}",
                "name": name.strip(),
                "description": description.strip(),
                "skills": matched_skills,
            }
        )
    completed = sum(
        bool(item)
        for item in (
            candidate.major,
            candidate.skills,
            candidate.projects,
            candidate.target_roles,
            candidate.preferred_locations,
            candidate.constraints,
        )
    )
    degree = "本科" if "本科" in candidate.education_level else candidate.education_level
    return {
        "gradYear": f"{candidate.graduation_year} 届",
        "degree": degree,
        "schoolBackground": candidate.school_background,
        "major": candidate.major,
        "targetRoles": candidate.target_roles,
        "cities": candidate.preferred_locations,
        "salaryRange": candidate.salary_range_k,
        "acceptInternship": candidate.accept_internship,
        "acceptRelocation": candidate.accept_relocation,
        "maxDifficulty": candidate.max_difficulty,
        "workTypes": candidate.work_types,
        "skills": skills,
        "projects": projects,
        "internships": candidate.internships,
        "excludedDirections": candidate.excluded_directions,
        "notes": candidate.notes,
        "completeness": round(completed / 6 * 100),
        "studentStatus": candidate.student_status,
        "graduationMonth": candidate.graduation_month,
        "formalWorkYears": candidate.formal_work_years,
        "educationMode": candidate.education_mode,
        "rankingFocus": candidate.ranking_focus,
    }


def create_profile_router(repository: WebRepository, config_file: Path) -> APIRouter:
    """创建画像路由；配置读取、验证和原子写回都隐藏在此模块后。"""

    router = APIRouter(prefix="/api/profile", tags=["profile"])

    @router.get("")
    def get_profile() -> dict[str, Any]:
        return profile_json(repository.settings.candidate)

    @router.put("")
    def save_profile(payload: ProfilePayload) -> dict[str, bool]:
        current = repository.settings.candidate.model_dump(mode="json")
        match = re.search(r"(20\d{2})", payload.gradYear)
        if not match:
            raise HTTPException(422, "毕业届别必须包含四位年份")
        current.update(
            {
                "graduation_year": int(match.group(1)),
                "education_level": payload.degree,
                "school_background": payload.schoolBackground.strip(),
                "major": payload.major.strip(),
                "skills": [skill.name.strip() for skill in payload.skills],
                "skill_levels": {
                    skill.name.strip(): skill.level for skill in payload.skills
                },
                "projects": [
                    f"{project.name}：{project.description}" for project in payload.projects
                ],
                "internships": [
                    item.strip() for item in payload.internships if item.strip()
                ],
                "target_roles": payload.targetRoles,
                "preferred_locations": payload.cities,
                "salary_range_k": payload.salaryRange,
                "accept_internship": payload.acceptInternship,
                "accept_relocation": payload.acceptRelocation,
                "max_difficulty": payload.maxDifficulty,
                "work_types": payload.workTypes,
                "excluded_directions": payload.excludedDirections,
                "notes": payload.notes.strip(),
            }
        )
        for key, internal in {"studentStatus": "student_status", "graduationMonth": "graduation_month", "formalWorkYears": "formal_work_years", "educationMode": "education_mode", "rankingFocus": "ranking_focus"}.items():
            if key in payload.model_fields_set:
                value = getattr(payload, key)
                if value is not None or key in {"graduationMonth", "formalWorkYears"}:
                    current[internal] = value
        candidate = CandidateProfile.model_validate(current)
        update_config_blocks(config_file, {"candidate": candidate.model_dump(mode="json")})
        return {"ok": True}

    @router.post("/recalculate")
    def recalculate_profile() -> dict[str, Any]:
        return {"ok": True, "updated": 0, "message": "资格按当前画像即时计算；AI 排序按画像和 JD 版本复用，版本变化后需重新评估"}

    return router
