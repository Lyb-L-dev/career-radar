"""Company candidate catalog review, discovery, and promotion routes."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .api_validations import safe_public_url
from .company_catalog import (
    CompanyCatalogError,
    catalog_response,
    find_catalog_candidate,
    load_company_catalog,
)
from .company_website import discover_official_website
from .config_editor import mutate_config_blocks
from .models import JobPosting
from .reputation import OpenCLIConnector, OpenCLIError
from .storage import JobStorage
from .web_repository import WebRepository

CHANNEL_STATUS_PATTERN = (
    r"^(official_site_pending|no_official_site|no_careers_channel|"
    r"official_careers|group_recruitment|official_notice_source|manual_only|"
    r"third_party_lead|not_hiring)$"
)
MONITOR_CHANNEL_PATTERN = (
    r"^(official_careers|official_homepage|group_recruitment|"
    r"official_notice_source)$"
)
SOURCE_KIND_PATTERN = (
    r"^(official_homepage|official_careers|group_recruitment|"
    r"government_notice|official_account|official_document|official_email|"
    r"third_party_lead)$"
)


class CandidateReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern=r"^(pending|shortlisted|rejected)$")
    officialWebsite: str | None = None
    careersUrl: str | None = None
    companyType: str | None = Field(
        default=None,
        pattern=r"^(central_soe|local_soe|private|foreign|joint_venture|other)$",
    )
    industryCategory: str | None = Field(
        default=None,
        pattern=r"^(internet|gaming|pet|enterprise_software|ai_data|iot|fintech|telecom|energy|manufacturing|consumer|other)$",
    )
    recruitmentChannelStatus: str | None = Field(
        default=None,
        pattern=CHANNEL_STATUS_PATTERN,
    )
    parentCompany: str | None = Field(default=None, max_length=200)
    groupRecruitmentUrl: str | None = None
    attributionKeywords: list[str] | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_group_mapping(self) -> CandidateReviewPayload:
        if self.recruitmentChannelStatus == "group_recruitment":
            if not self.parentCompany or not self.parentCompany.strip():
                raise ValueError("集团招聘渠道必须填写母集团名称")
            if not self.groupRecruitmentUrl:
                raise ValueError("集团招聘渠道必须填写集团招聘网址")
            if not self.attributionKeywords or not any(
                item.strip() for item in self.attributionKeywords
            ):
                raise ValueError("集团招聘渠道必须填写子公司归属关键词")
        return self


class CandidateBulkReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=500)
    decision: str = Field(pattern=r"^(pending|shortlisted|rejected)$")


class CandidateMonitorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    website: str
    careersUrl: str | None = None
    companyType: str = Field(
        default="other",
        pattern=r"^(central_soe|local_soe|private|foreign|joint_venture|other)$",
    )
    industryCategory: str | None = Field(
        default=None,
        pattern=r"^(internet|gaming|pet|enterprise_software|ai_data|iot|fintech|telecom|energy|manufacturing|consumer|other)$",
    )
    monitorMode: str = Field(default="jobs", pattern=r"^(jobs|notices|both)$")
    maxPages: int = Field(default=20, ge=1, le=5000)
    enabled: bool = False
    recruitmentChannel: str = Field(
        default="official_careers",
        pattern=MONITOR_CHANNEL_PATTERN,
    )
    parentCompany: str | None = Field(default=None, max_length=200)
    attributionKeywords: list[str] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_group_scope(self) -> CandidateMonitorPayload:
        if self.recruitmentChannel == "group_recruitment":
            if not self.parentCompany or not self.parentCompany.strip():
                raise ValueError("集团招聘平台必须填写母集团名称")
            if not any(item.strip() for item in self.attributionKeywords):
                raise ValueError("集团招聘平台必须填写子公司归属关键词")
        return self


class CandidateSourcePayload(BaseModel):
    """人工登记的公开招聘材料或待核验线索。"""

    model_config = ConfigDict(extra="forbid")
    sourceKind: str = Field(pattern=SOURCE_KIND_PATTERN)
    verificationStatus: str = Field(pattern=r"^(verified_official|pending|rejected)$")
    materialType: str = Field(pattern=r"^(webpage|pdf|image|text|email)$")
    title: str = Field(min_length=1, max_length=300)
    sourceUrl: str | None = None
    content: str | None = Field(default=None, max_length=100_000)
    publishedAt: str | None = Field(default=None, max_length=50)
    parentCompany: str | None = Field(default=None, max_length=200)
    importAsNotice: bool = False

    @model_validator(mode="after")
    def validate_source_boundary(self) -> CandidateSourcePayload:
        if not self.sourceUrl and not (self.content and self.content.strip()):
            raise ValueError("招聘来源至少需要公开链接或人工摘录正文")
        if self.sourceKind == "third_party_lead":
            if self.verificationStatus != "pending":
                raise ValueError("第三方来源只能保存为待核验线索")
            if self.importAsNotice:
                raise ValueError("第三方线索不能直接导入为官方招聘通知")
        if self.sourceKind == "group_recruitment" and not self.parentCompany:
            raise ValueError("集团招聘来源必须填写母集团名称")
        if self.importAsNotice:
            if self.verificationStatus != "verified_official":
                raise ValueError("只有已核验的官方来源才能导入招聘通知")
            if not self.content or not self.content.strip():
                raise ValueError("导入招聘通知必须提供完整正文")
        return self


def _source_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["source_id"],
        "candidateId": row["candidate_id"],
        "sourceKind": row["source_kind"],
        "verificationStatus": row["verification_status"],
        "materialType": row["material_type"],
        "title": row["title"],
        "sourceUrl": row.get("source_url"),
        "content": row.get("content"),
        "publishedAt": row.get("published_at"),
        "parentCompany": row.get("parent_company"),
        "importedJobId": row.get("imported_job_id"),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def create_candidates_router(
    repository: WebRepository,
    config_file: Path,
) -> APIRouter:
    router = APIRouter(prefix="/api/company-candidates", tags=["company-candidates"])

    def current_catalog() -> dict[str, Any]:
        try:
            return load_company_catalog(repository.settings.app.company_catalog_path)
        except CompanyCatalogError as exc:
            raise HTTPException(500, str(exc)) from exc

    @router.get("")
    def list_company_candidates(
        q: str = Query(default="", max_length=200),
        province: str | None = Query(default=None, max_length=100),
        city: str | None = Query(default=None, max_length=100),
        fitLevel: str | None = Query(default=None, pattern=r"^(high|medium|low)$"),
        decision: str | None = Query(
            default=None,
            pattern=r"^(pending|shortlisted|rejected|monitored)$",
        ),
        channelStatus: str | None = Query(
            default=None,
            pattern=CHANNEL_STATUS_PATTERN,
        ),
        sourceKey: str | None = Query(default=None, max_length=200),
        techOnly: bool = False,
        page: int = Query(default=1, ge=1),
        pageSize: int = Query(default=50, ge=10, le=100),
    ) -> dict[str, Any]:
        return catalog_response(
            current_catalog(),
            profile=repository.settings.candidate,
            states=repository.candidate_states(),
            monitored_names={company.name for company in repository.settings.companies},
            query=q,
            province=province,
            city=city,
            fit_level=fitLevel,
            decision=decision,
            channel_status=channelStatus,
            source_key=sourceKey,
            tech_only=techOnly,
            page=page,
            page_size=pageSize,
        )

    @router.patch("/review-many")
    def review_many_candidates(payload: CandidateBulkReviewPayload) -> dict[str, Any]:
        catalog = current_catalog()
        known_ids = {item["id"] for item in catalog["items"]}
        unknown = [candidate_id for candidate_id in payload.ids if candidate_id not in known_ids]
        if unknown:
            raise HTTPException(404, f"存在未知候选企业：{unknown[0]}")
        repository.set_candidate_state(payload.ids, decision=payload.decision)
        return {"ok": True, "updated": len(payload.ids)}

    @router.get("/{candidate_id}")
    def get_company_candidate(candidate_id: str) -> dict[str, Any]:
        catalog = current_catalog()
        raw = find_catalog_candidate(catalog, candidate_id)
        if raw is None:
            raise HTTPException(404, "候选企业不存在")
        response = catalog_response(
            catalog,
            profile=repository.settings.candidate,
            states=repository.candidate_states(),
            monitored_names={company.name for company in repository.settings.companies},
            query=raw["name"],
            page=1,
            page_size=100,
        )
        item = next(
            (entry for entry in response["items"] if entry["id"] == candidate_id),
            None,
        )
        if item is None:  # pragma: no cover
            raise HTTPException(500, "候选企业索引异常")
        return item

    @router.patch("/{candidate_id}")
    def review_company_candidate(
        candidate_id: str,
        payload: CandidateReviewPayload,
    ) -> dict[str, bool]:
        if find_catalog_candidate(current_catalog(), candidate_id) is None:
            raise HTTPException(404, "候选企业不存在")
        patch = payload.model_dump(exclude_unset=True)
        website = patch.get("officialWebsite")
        careers_url = patch.get("careersUrl")
        group_url = patch.get("groupRecruitmentUrl")
        try:
            if website:
                website = safe_public_url(website)
            if careers_url:
                careers_url = safe_public_url(careers_url)
            if group_url:
                group_url = safe_public_url(group_url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        channel_status = patch.get("recruitmentChannelStatus")
        if channel_status == "no_official_site":
            website = None
            careers_url = None
        elif channel_status == "no_careers_channel":
            careers_url = None
        if channel_status != "group_recruitment" and "groupRecruitmentUrl" in patch:
            group_url = None
        repository_fields = {
            "officialWebsite": "official_website",
            "careersUrl": "careers_url",
            "companyType": "company_type",
            "industryCategory": "industry_category",
            "recruitmentChannelStatus": "recruitment_channel_status",
            "parentCompany": "parent_company",
            "groupRecruitmentUrl": "group_recruitment_url",
            "attributionKeywords": "attribution_keywords",
            "note": "note",
        }
        values = {
            target: patch[source]
            for source, target in repository_fields.items()
            if source in patch
        }
        if "officialWebsite" in patch or channel_status == "no_official_site":
            values["official_website"] = website
        if "careersUrl" in patch or channel_status in {
            "no_official_site",
            "no_careers_channel",
        }:
            values["careers_url"] = careers_url
        if "groupRecruitmentUrl" in patch:
            values["group_recruitment_url"] = group_url
        if channel_status and channel_status != "group_recruitment":
            values["parent_company"] = None
            values["group_recruitment_url"] = None
            values["attribution_keywords"] = None
        repository.set_candidate_state(
            [candidate_id],
            decision=payload.decision,
            **values,
        )
        return {"ok": True}

    @router.get("/{candidate_id}/sources")
    def list_candidate_sources(candidate_id: str) -> list[dict[str, Any]]:
        if find_catalog_candidate(current_catalog(), candidate_id) is None:
            raise HTTPException(404, "候选企业不存在")
        return [
            _source_response(row)
            for row in repository.list_candidate_sources(candidate_id)
        ]

    @router.post("/{candidate_id}/sources")
    def add_candidate_source(
        candidate_id: str,
        payload: CandidateSourcePayload,
    ) -> dict[str, Any]:
        candidate = find_catalog_candidate(current_catalog(), candidate_id)
        if candidate is None:
            raise HTTPException(404, "候选企业不存在")
        source_url = payload.sourceUrl
        try:
            if source_url:
                source_url = safe_public_url(source_url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        now = datetime.now(
            ZoneInfo(repository.settings.app.timezone)
        ).isoformat(timespec="seconds")
        source = {
            "source_id": f"source-{uuid4().hex}",
            "candidate_id": candidate_id,
            "source_kind": payload.sourceKind,
            "verification_status": payload.verificationStatus,
            "material_type": payload.materialType,
            "title": payload.title.strip(),
            "source_url": source_url,
            "content": payload.content.strip() if payload.content else None,
            "published_at": payload.publishedAt.strip() if payload.publishedAt else None,
            "parent_company": (
                payload.parentCompany.strip() if payload.parentCompany else None
            ),
            "imported_job_id": None,
            "created_at": now,
            "updated_at": now,
        }
        repository.save_candidate_source(source)

        if payload.importAsNotice:
            event = JobStorage(repository.settings.app.database_path).store_jobs(
                [
                    JobPosting(
                        record_type="notice",
                        company=candidate["name"],
                        title=source["title"],
                        description=source["content"] or "",
                        published_at=source["published_at"],
                        source_url=source_url or "",
                        application_method="人工导入的已核验官方招聘材料",
                        match_reason="人工导入，尚未使用 DeepSeek 评估届别匹配",
                        profile_fit_reason="人工导入，尚未使用 DeepSeek 评估能力匹配",
                        difficulty_reason="人工导入，尚未使用 DeepSeek 评估投递难度",
                    )
                ],
                now,
            )[0]
            source["imported_job_id"] = event.entity_key
            repository.set_candidate_source_imported_job(
                source["source_id"],
                event.entity_key,
            )

        return _source_response(source)

    @router.post("/{candidate_id}/discover-website")
    def discover_company_candidate_website(candidate_id: str) -> dict[str, Any]:
        candidate = find_catalog_candidate(current_catalog(), candidate_id)
        if candidate is None:
            raise HTTPException(404, "候选企业不存在")
        state = repository.candidate_states().get(candidate_id, {})
        stored_website = state.get("official_website") or candidate.get("officialWebsite")
        if stored_website:
            return {
                "status": "found",
                "confidence": "high",
                "website": stored_website,
                "message": "已使用此前核验并保存的企业官网。",
                "candidates": [],
                "cached": True,
            }
        try:
            connector = OpenCLIConnector(repository.settings.reputation)
            rows = connector.search_web(f"{candidate['name']} 官网")
            result = discover_official_website(candidate["name"], rows)
        except (OpenCLIError, subprocess.SubprocessError) as exc:
            raise HTTPException(
                503,
                f"官网自动查找暂不可用：{exc}。请确认 OpenCLI 扩展已连接，或手动填写官网。",
            ) from exc

        if result["status"] == "found" and result.get("website"):
            try:
                website = safe_public_url(str(result["website"]))
            except ValueError as exc:  # pragma: no cover
                raise HTTPException(422, str(exc)) from exc
            result["website"] = website
            repository.set_candidate_state(
                [candidate_id],
                decision=state.get("decision", "pending"),
                official_website=website,
            )
        result["cached"] = False
        return result

    @router.post("/{candidate_id}/monitor")
    def monitor_company_candidate(
        candidate_id: str,
        payload: CandidateMonitorPayload,
    ) -> dict[str, Any]:
        candidate = find_catalog_candidate(current_catalog(), candidate_id)
        if candidate is None:
            raise HTTPException(404, "候选企业不存在")
        try:
            website = safe_public_url(payload.website)
            careers_url = safe_public_url(payload.careersUrl) if payload.careersUrl else None
            target_url = careers_url or website
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        normalized_name = candidate["name"].strip().casefold()
        industry = (
            payload.industryCategory
            or candidate.get("suggestedIndustryCategory")
            or "other"
        )
        source_titles = candidate.get("sourceTitles") or [candidate["sourceTitle"]]
        evidence_urls = candidate.get("evidenceUrls") or [candidate["evidenceUrl"]]
        source_note = (
            f"候选库来源：{'；'.join(source_titles)}。员工体验与劳动风险仍需人工背调。"
        )

        def append_candidate(raw: dict[str, Any]) -> tuple[dict[str, Any], None]:
            companies = list(raw.get("companies") or [])
            if any(
                str(item.get("name", "")).strip().casefold() == normalized_name
                for item in companies
            ):
                raise HTTPException(409, "该候选企业已经在监控列表中")
            companies.append(
                {
                    "name": candidate["name"],
                    "url": target_url,
                    "company_type": payload.companyType,
                    "industry_category": industry,
                    "province": candidate.get("province"),
                    "city": candidate.get("city"),
                    "priority": "high"
                    if candidate.get("province") == "福建"
                    else "medium",
                    "monitor_mode": payload.monitorMode,
                    "government_honors": source_titles,
                    "evidence_urls": evidence_urls,
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
                    "notes": payload.note.strip() if payload.note else source_note,
                }
            )
            return {"companies": companies}, None

        mutate_config_blocks(config_file, append_candidate)
        state_values: dict[str, Any] = {
            "company_type": payload.companyType,
            "industry_category": industry,
            "recruitment_channel_status": {
                "official_careers": "official_careers",
                "official_homepage": "official_site_pending",
                "group_recruitment": "group_recruitment",
                "official_notice_source": "official_notice_source",
            }[payload.recruitmentChannel],
            "parent_company": payload.parentCompany,
            "group_recruitment_url": (
                target_url
                if payload.recruitmentChannel == "group_recruitment"
                else None
            ),
            "attribution_keywords": (
                [
                    item.strip()
                    for item in payload.attributionKeywords
                    if item.strip()
                ]
                if payload.recruitmentChannel == "group_recruitment"
                else None
            ),
            "note": payload.note,
        }
        if payload.recruitmentChannel in {"official_careers", "official_homepage"}:
            state_values["official_website"] = website
            state_values["careers_url"] = careers_url
        elif payload.recruitmentChannel == "official_notice_source":
            state_values["careers_url"] = target_url
        repository.set_candidate_state(
            [candidate_id],
            decision="shortlisted",
            **state_values,
        )
        return next(
            item
            for item in repository.list_companies()
            if item["name"] == candidate["name"]
        )

    return router
