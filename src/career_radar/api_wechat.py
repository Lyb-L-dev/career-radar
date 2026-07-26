"""Verified WeChat recruitment account and scan routes."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .company_catalog import find_catalog_candidate, load_company_catalog
from .web_repository import WebRepository
from .wechat_recruitment import WechatRecruitmentManager


class WechatAccountPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accountName: str = Field(min_length=1, max_length=200)
    accountIdentifier: str | None = Field(default=None, max_length=200)
    bizId: str | None = Field(default=None, max_length=200)
    scope: str = Field(default="company", pattern=r"^(company|group)$")
    parentCompany: str | None = Field(default=None, max_length=200)
    attributionKeywords: list[str] = Field(default_factory=list, max_length=20)
    verificationStatus: str = Field(
        default="pending",
        pattern=r"^(verified|pending|rejected)$",
    )
    enabled: bool = True

    @model_validator(mode="after")
    def validate_identity_and_scope(self) -> WechatAccountPayload:
        if self.verificationStatus == "verified" and not (
            self.accountIdentifier or self.bizId or self.accountName
        ):
            raise ValueError("核验公众号必须至少保留一种公开账号身份")
        if self.scope == "group":
            if not self.parentCompany or not self.parentCompany.strip():
                raise ValueError("集团招聘公众号必须填写母集团名称")
            if not any(item.strip() for item in self.attributionKeywords):
                raise ValueError("集团招聘公众号必须填写目标子公司归属关键词")
        return self


def _account_response(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": account["account_id"],
        "candidateId": account["candidate_id"],
        "accountName": account["account_name"],
        "accountIdentifier": account.get("account_identifier"),
        "bizId": account.get("biz_id"),
        "scope": account["scope"],
        "parentCompany": account.get("parent_company"),
        "attributionKeywords": account.get("attribution_keywords") or [],
        "verificationStatus": account["verification_status"],
        "enabled": bool(account["enabled"]),
        "createdAt": account["created_at"],
        "updatedAt": account["updated_at"],
    }


def _article_response(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": article["article_id"],
        "candidateId": article["candidate_id"],
        "accountId": article.get("account_id"),
        "title": article["title"],
        "accountName": article.get("account_name"),
        "url": article["source_url"],
        "summary": article.get("summary"),
        "publishedAt": article.get("published_at"),
        "classification": article["classification"],
        "verificationStatus": article["verification_status"],
        "reason": article["reason"],
        "sourceId": article.get("source_id"),
        "importedJobId": article.get("imported_job_id"),
        "firstSeenAt": article["first_seen_at"],
        "updatedAt": article["updated_at"],
    }


def create_wechat_router(
    repository: WebRepository,
    manager: WechatRecruitmentManager,
) -> APIRouter:
    router = APIRouter(tags=["wechat-recruitment"])

    def candidate(candidate_id: str) -> dict[str, Any]:
        catalog = load_company_catalog(
            repository.settings.app.company_catalog_path
        )
        item = find_catalog_candidate(catalog, candidate_id)
        if item is None:
            raise HTTPException(404, "候选企业不存在")
        return item

    @router.get("/api/wechat-recruitment/health")
    def wechat_health() -> dict[str, Any]:
        return manager.health()

    @router.get("/api/company-candidates/{candidate_id}/wechat-accounts")
    def list_wechat_accounts(candidate_id: str) -> list[dict[str, Any]]:
        candidate(candidate_id)
        return [
            _account_response(item)
            for item in repository.list_wechat_accounts(candidate_id)
        ]

    @router.post("/api/company-candidates/{candidate_id}/wechat-accounts")
    def create_wechat_account(
        candidate_id: str,
        payload: WechatAccountPayload,
    ) -> dict[str, Any]:
        item = candidate(candidate_id)
        normalized = re.sub(r"\s+", "", payload.accountName).casefold()
        if any(
            re.sub(r"\s+", "", account["account_name"]).casefold() == normalized
            for account in repository.list_wechat_accounts(candidate_id)
        ):
            raise HTTPException(409, "该公众号已经登记")
        now = datetime.now(
            ZoneInfo(repository.settings.app.timezone)
        ).isoformat(timespec="seconds")
        account = {
            "account_id": f"wechat-account-{uuid.uuid4().hex}",
            "candidate_id": candidate_id,
            "account_name": payload.accountName.strip(),
            "account_identifier": (
                payload.accountIdentifier.strip()
                if payload.accountIdentifier
                else None
            ),
            "biz_id": payload.bizId.strip() if payload.bizId else None,
            "scope": payload.scope,
            "parent_company": (
                payload.parentCompany.strip() if payload.parentCompany else None
            ),
            "attribution_keywords": [
                keyword.strip()
                for keyword in (
                    payload.attributionKeywords
                    or ([item["name"]] if payload.scope == "company" else [])
                )
                if keyword.strip()
            ],
            "verification_status": payload.verificationStatus,
            "enabled": payload.enabled,
            "created_at": now,
            "updated_at": now,
        }
        repository.save_wechat_account(account)
        return _account_response(account)

    @router.put(
        "/api/company-candidates/{candidate_id}/wechat-accounts/{account_id}"
    )
    def update_wechat_account(
        candidate_id: str,
        account_id: str,
        payload: WechatAccountPayload,
    ) -> dict[str, Any]:
        item = candidate(candidate_id)
        existing = repository.get_wechat_account(account_id)
        if existing is None or existing["candidate_id"] != candidate_id:
            raise HTTPException(404, "公众号绑定不存在")
        normalized = re.sub(r"\s+", "", payload.accountName).casefold()
        if any(
            account["account_id"] != account_id
            and re.sub(r"\s+", "", account["account_name"]).casefold()
            == normalized
            for account in repository.list_wechat_accounts(candidate_id)
        ):
            raise HTTPException(409, "该公众号已经登记")
        account = {
            **existing,
            "account_name": payload.accountName.strip(),
            "account_identifier": (
                payload.accountIdentifier.strip()
                if payload.accountIdentifier
                else None
            ),
            "biz_id": payload.bizId.strip() if payload.bizId else None,
            "scope": payload.scope,
            "parent_company": (
                payload.parentCompany.strip() if payload.parentCompany else None
            ),
            "attribution_keywords": [
                keyword.strip()
                for keyword in (
                    payload.attributionKeywords
                    or ([item["name"]] if payload.scope == "company" else [])
                )
                if keyword.strip()
            ],
            "verification_status": payload.verificationStatus,
            "enabled": payload.enabled,
            "updated_at": datetime.now(
                ZoneInfo(repository.settings.app.timezone)
            ).isoformat(timespec="seconds"),
        }
        repository.save_wechat_account(account)
        return _account_response(account)

    @router.delete(
        "/api/company-candidates/{candidate_id}/wechat-accounts/{account_id}"
    )
    def delete_wechat_account(
        candidate_id: str,
        account_id: str,
    ) -> dict[str, bool]:
        candidate(candidate_id)
        if not repository.delete_wechat_account(account_id, candidate_id):
            raise HTTPException(404, "公众号绑定不存在")
        return {"ok": True}

    @router.post("/api/company-candidates/{candidate_id}/wechat-scans", status_code=202)
    def start_wechat_scan(candidate_id: str) -> dict[str, Any]:
        item = candidate(candidate_id)
        try:
            scan = manager.start(
                candidate_id=candidate_id,
                company_name=item["name"],
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"ok": True, "scanId": scan["id"]}

    @router.get("/api/company-candidates/{candidate_id}/wechat-scans/latest")
    def latest_wechat_scan(candidate_id: str) -> dict[str, Any] | None:
        candidate(candidate_id)
        return repository.latest_wechat_scan(candidate_id)

    @router.get("/api/wechat-recruitment/scans/{scan_id}")
    def get_wechat_scan(scan_id: str) -> dict[str, Any]:
        scan = repository.get_wechat_scan(scan_id)
        if scan is None:
            raise HTTPException(404, "公众号扫描任务不存在")
        return scan

    @router.get("/api/company-candidates/{candidate_id}/wechat-articles")
    def list_wechat_articles(
        candidate_id: str,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> list[dict[str, Any]]:
        candidate(candidate_id)
        return [
            _article_response(item)
            for item in repository.list_wechat_articles(
                candidate_id,
                limit=limit,
            )
        ]

    return router
