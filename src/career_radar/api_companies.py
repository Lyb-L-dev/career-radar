"""Company CRUD, connection testing, and monitoring audit routes."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .api_validations import safe_public_url
from .config_editor import mutate_config_blocks
from .crawler import PageFetcher
from .discovery import parse_html, ranked_prompt_links
from .web_repository import WebRepository, company_id


class CompanyCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    website: str
    careersUrl: str | None = None
    companyType: str = Field(
        default="private",
        pattern=r"^(central_soe|local_soe|private|foreign|joint_venture|other)$",
    )
    industryCategory: str = Field(
        default="other",
        pattern=r"^(internet|gaming|pet|enterprise_software|ai_data|iot|fintech|telecom|energy|manufacturing|consumer|other)$",
    )
    province: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    priority: str = Field(default="medium", pattern=r"^(high|medium|low)$")
    monitorMode: str = Field(default="jobs", pattern=r"^(jobs|notices|both)$")
    governmentHonors: list[str] = Field(default_factory=list, max_length=50)
    evidenceUrls: list[str] = Field(default_factory=list, max_length=50)
    renderMode: str = Field(default="auto", pattern=r"^(auto|static|dynamic)$")
    maxPages: int = Field(default=120, ge=1, le=5000)
    enabled: bool = True
    recruitmentChannel: str = Field(
        default="official_careers",
        pattern=r"^(official_careers|official_homepage|group_recruitment|official_notice_source)$",
    )
    parentCompany: str | None = Field(default=None, max_length=200)
    attributionKeywords: list[str] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_group_scope(self) -> CompanyCreatePayload:
        if self.recruitmentChannel == "group_recruitment":
            if not self.parentCompany or not self.parentCompany.strip():
                raise ValueError("集团招聘平台必须填写母集团名称")
            if not any(item.strip() for item in self.attributionKeywords):
                raise ValueError("集团招聘平台必须填写子公司归属关键词")
        return self


class CompanyPatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website: str | None = None
    careersUrl: str | None = None
    companyType: str | None = Field(
        default=None,
        pattern=r"^(central_soe|local_soe|private|foreign|joint_venture|other)$",
    )
    industryCategory: str | None = Field(
        default=None,
        pattern=r"^(internet|gaming|pet|enterprise_software|ai_data|iot|fintech|telecom|energy|manufacturing|consumer|other)$",
    )
    province: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    priority: str | None = Field(default=None, pattern=r"^(high|medium|low)$")
    monitorMode: str | None = Field(default=None, pattern=r"^(jobs|notices|both)$")
    governmentHonors: list[str] | None = Field(default=None, max_length=50)
    evidenceUrls: list[str] | None = Field(default=None, max_length=50)
    maxPages: int | None = Field(default=None, ge=1, le=5000)
    recruitmentChannel: str | None = Field(
        default=None,
        pattern=r"^(official_careers|official_homepage|group_recruitment|official_notice_source)$",
    )
    parentCompany: str | None = Field(default=None, max_length=200)
    attributionKeywords: list[str] | None = Field(default=None, max_length=20)
    enabled: bool | None = None
    status: str | None = Field(default=None, pattern=r"^(active|paused)$")
    note: str | None = Field(default=None, max_length=2000)


class CompanyBulkDeletePayload(BaseModel):
    """Atomically delete companies; any invalid ID aborts the whole update."""

    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=5000)


class CompanyTestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    website: str
    careersUrl: str | None = None


def create_companies_router(
    repository: WebRepository,
    config_file: Path,
) -> APIRouter:
    router = APIRouter(prefix="/api/companies", tags=["companies"])

    @router.get("")
    def list_companies() -> list[dict[str, Any]]:
        return repository.list_companies()

    @router.post("/bulk-delete")
    def bulk_delete_companies(
        payload: CompanyBulkDeletePayload,
    ) -> dict[str, bool | int]:
        identifiers = list(dict.fromkeys(item.strip() for item in payload.ids))
        if any(not item or len(item) > 100 for item in identifiers):
            raise HTTPException(422, "企业 ID 格式无效")

        def delete_selected(raw: dict[str, Any]) -> tuple[dict[str, Any], int]:
            companies = list(raw.get("companies") or [])
            index_by_id = {
                company_id(str(company.get("name", ""))): index
                for index, company in enumerate(companies)
            }
            unknown = [identifier for identifier in identifiers if identifier not in index_by_id]
            if unknown:
                raise HTTPException(404, "所选企业中包含不存在或已经删除的记录，请刷新后重试")
            indexes = {index_by_id[identifier] for identifier in identifiers}
            remaining = [item for index, item in enumerate(companies) if index not in indexes]
            if not remaining:
                raise HTTPException(422, "至少保留一家企业配置")
            return {"companies": remaining}, len(indexes)

        deleted = mutate_config_blocks(config_file, delete_selected)
        return {"ok": True, "deleted": deleted}

    @router.get("/{identifier}")
    def get_company(identifier: str) -> dict[str, Any]:
        company = next(
            (item for item in repository.list_companies() if item["id"] == identifier),
            None,
        )
        if company is None:
            raise HTTPException(404, "企业不存在")
        return company

    @router.post("")
    def add_company(payload: CompanyCreatePayload) -> dict[str, Any]:
        try:
            url = safe_public_url(payload.careersUrl or payload.website)
            safe_public_url(payload.website)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        normalized_name = payload.name.strip().casefold()

        def append_company(raw: dict[str, Any]) -> tuple[dict[str, Any], None]:
            companies = list(raw.get("companies") or [])
            if any(
                str(item.get("name", "")).strip().casefold() == normalized_name
                for item in companies
            ):
                raise HTTPException(409, "企业名称已存在")
            companies.append(
                {
                    "name": payload.name.strip(),
                    "url": url,
                    "company_type": payload.companyType,
                    "industry_category": payload.industryCategory,
                    "province": payload.province,
                    "city": payload.city,
                    "priority": payload.priority,
                    "monitor_mode": payload.monitorMode,
                    "government_honors": payload.governmentHonors,
                    "evidence_urls": payload.evidenceUrls,
                    "enabled": payload.enabled,
                    "discover_from_homepage": False if payload.careersUrl else "auto",
                    "max_pages": payload.maxPages,
                    "recruitment_channel": payload.recruitmentChannel,
                    "parent_company": (
                        payload.parentCompany.strip()
                        if payload.parentCompany
                        else None
                    ),
                    "attribution_keywords": [
                        item.strip()
                        for item in payload.attributionKeywords
                        if item.strip()
                    ],
                    "notes": payload.note,
                }
            )
            return {"companies": companies}, None

        mutate_config_blocks(config_file, append_company)
        return next(
            item
            for item in repository.list_companies()
            if item["name"] == payload.name.strip()
        )

    @router.patch("/{identifier}")
    def update_company(identifier: str, payload: CompanyPatchPayload) -> dict[str, bool]:
        patch = payload.model_dump(exclude_unset=True)

        def patch_company(raw: dict[str, Any]) -> tuple[dict[str, Any], None]:
            companies = list(raw.get("companies") or [])
            index = next(
                (
                    index
                    for index, company in enumerate(companies)
                    if company_id(str(company.get("name", ""))) == identifier
                ),
                None,
            )
            if index is None:
                raise HTTPException(404, "企业不存在")
            item = dict(companies[index])
            if "name" in patch:
                new_name = str(patch["name"]).strip()
                if any(
                    other_index != index
                    and str(other.get("name", "")).strip().casefold()
                    == new_name.casefold()
                    for other_index, other in enumerate(companies)
                ):
                    raise HTTPException(409, "企业名称已存在")
                item["name"] = new_name
            if "website" in patch or "careersUrl" in patch:
                value = patch.get("careersUrl") or patch.get("website") or item.get("url")
                try:
                    item["url"] = safe_public_url(str(value))
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from exc
            mappings = {
                "companyType": "company_type",
                "industryCategory": "industry_category",
                "province": "province",
                "city": "city",
                "priority": "priority",
                "monitorMode": "monitor_mode",
                "governmentHonors": "government_honors",
                "evidenceUrls": "evidence_urls",
                "maxPages": "max_pages",
                "recruitmentChannel": "recruitment_channel",
                "parentCompany": "parent_company",
                "attributionKeywords": "attribution_keywords",
                "note": "notes",
            }
            for source, target in mappings.items():
                if source in patch:
                    item[target] = patch[source]
            if "enabled" in patch:
                item["enabled"] = bool(patch["enabled"])
            if patch.get("status") == "paused":
                item["enabled"] = False
            elif patch.get("status") == "active":
                item["enabled"] = True
            companies[index] = item
            return {"companies": companies}, None

        mutate_config_blocks(config_file, patch_company)
        return {"ok": True}

    @router.delete("/{identifier}")
    def remove_company(identifier: str) -> dict[str, bool]:
        def delete_company(raw: dict[str, Any]) -> tuple[dict[str, Any], None]:
            companies = list(raw.get("companies") or [])
            index = next(
                (
                    index
                    for index, company in enumerate(companies)
                    if company_id(str(company.get("name", ""))) == identifier
                ),
                None,
            )
            if index is None:
                raise HTTPException(404, "企业不存在")
            del companies[index]
            if not companies:
                raise HTTPException(422, "至少保留一家企业配置")
            return {"companies": companies}, None

        mutate_config_blocks(config_file, delete_company)
        return {"ok": True}

    @router.post("/test")
    async def test_company(payload: CompanyTestPayload) -> dict[str, Any]:
        try:
            target = safe_public_url(payload.careersUrl or payload.website)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        def probe() -> dict[str, Any]:
            settings = repository.settings
            with PageFetcher(settings.crawler) as fetcher:
                page = fetcher.fetch(target)
            document = parse_html(page.html, page.final_url)
            links = ranked_prompt_links(document, 100)
            entry = next(
                (link.url for link in links if link.career_score > 0 or link.job_score > 0),
                None,
            )
            return {
                "robotsAllowed": True,
                "homepageReachable": True,
                "entryFound": bool(entry or payload.careersUrl),
                "entryUrl": entry or (target if payload.careersUrl else None),
                "needsBrowserRender": page.rendered,
                "estimatedPages": sum(
                    link.career_score > 0 or link.job_score > 0 for link in links
                ),
            }

        try:
            return await asyncio.to_thread(probe)
        except Exception as exc:
            raise HTTPException(400, f"连接测试失败：{type(exc).__name__}: {exc}") from exc

    @router.get("/{identifier}/pages")
    def company_pages(identifier: str) -> list[dict[str, Any]]:
        if repository.find_company(identifier) is None:
            raise HTTPException(404, "企业不存在")
        return repository.list_company_pages(identifier)

    @router.get("/{identifier}/errors")
    def company_errors(identifier: str) -> list[dict[str, Any]]:
        found = repository.find_company(identifier)
        if found is None:
            raise HTTPException(404, "企业不存在")
        _index, company = found
        errors = []
        for run in repository.list_runs()[:50]:
            for result in run.get("companies", []):
                if result.get("companyName") == company.name and result.get("error"):
                    errors.append(
                        {
                            "time": run.get("finishedAt") or run["startedAt"],
                            "message": result["error"].splitlines()[0],
                            "technicalDetail": result["error"],
                        }
                    )
        return errors

    return router
