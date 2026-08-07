"""ATS 公开接口适配器测试（离线，不访问真实接口）。"""

import pytest
import requests

import career_radar.ats_source as ats_module
from career_radar.ats_source import (
    ATSJob,
    ATSSourceError,
    ats_jobs_to_postings,
    fetch_ats_jobs,
)
from career_radar.models import AtsSourceConfig, AtsSourceType, CompanyConfig


class FakeResponse:
    def __init__(
        self,
        payload: object = None,
        status: int = 200,
        location: str | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status
        self.headers = {"Location": location} if location else {}
        self.closed = False

    def json(self) -> object:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, responder) -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, dict]] = []
        self.responder = responder

    def get(self, url: str, **kwargs: object):
        self.calls.append((url, kwargs))
        return self.responder(url, kwargs)


class PermitAllPolicy:
    def ensure_public(self, _url: str) -> None:
        return None


def test_greenhouse_parses_jobs() -> None:
    payload = {
        "jobs": [
            {
                "id": 101,
                "title": "后端开发工程师",
                "location": {"name": "福州"},
                "absolute_url": "https://boards.greenhouse.io/acme/101",
                "updated_at": "2026-08-01T02:00:00Z",
                "content": "<p>负责后端开发。</p><ul><li>熟悉 Python</li></ul>",
            }
        ]
    }
    session = FakeSession(lambda _url, _kw: FakeResponse(payload))
    source = AtsSourceConfig(type=AtsSourceType.GREENHOUSE, tenant="acme")

    jobs = fetch_ats_jobs(source, session=session)

    assert jobs[0].title == "后端开发工程师"
    assert "负责后端开发" in jobs[0].description
    assert "熟悉 Python" in jobs[0].description
    assert jobs[0].location == "福州"
    assert jobs[0].apply_url == "https://boards.greenhouse.io/acme/101"
    assert jobs[0].published_at == "2026-08-01T02:00:00+00:00"


def test_lever_parses_jobs() -> None:
    payload = [
        {
            "id": "abc-123",
            "text": "前端工程师",
            "descriptionPlain": "负责前端开发与性能优化。",
            "categories": {"location": "上海", "commitment": "Full-time"},
            "hostedUrl": "https://jobs.lever.co/acme/abc-123",
            "applyUrl": "https://jobs.lever.co/acme/abc-123/apply",
            "createdAt": 1780000000000,
        }
    ]
    session = FakeSession(lambda _url, _kw: FakeResponse(payload))
    source = AtsSourceConfig(type=AtsSourceType.LEVER, tenant="acme")

    jobs = fetch_ats_jobs(source, session=session)

    assert jobs[0].title == "前端工程师"
    assert jobs[0].location == "上海"
    assert jobs[0].recruitment_type == "Full-time"
    assert jobs[0].apply_url == "https://jobs.lever.co/acme/abc-123/apply"
    assert jobs[0].published_at and jobs[0].published_at.startswith("2026-")


def test_ashby_parses_jobs() -> None:
    payload = {
        "jobs": [
            {
                "id": "ashby-1",
                "title": "算法工程师",
                "location": "Remote",
                "employmentType": "Full-time",
                "descriptionPlain": "负责推荐系统优化。",
                "jobUrl": "https://jobs.ashbyhq.com/acme/ashby-1",
                "applyUrl": "https://jobs.ashbyhq.com/acme/ashby-1/apply",
                "publishedAt": "2026-07-01T00:00:00.000Z",
            }
        ]
    }
    session = FakeSession(lambda _url, _kw: FakeResponse(payload))
    source = AtsSourceConfig(type=AtsSourceType.ASHBY, tenant="acme")

    jobs = fetch_ats_jobs(source, session=session)

    assert jobs[0].title == "算法工程师"
    assert jobs[0].location == "Remote"
    assert jobs[0].remote is True
    assert jobs[0].published_at.startswith("2026-07-01")


def test_json_feed_with_mapping_and_html_description(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "data": {
            "list": [
                {
                    "jobTitle": "算法工程师",
                    "jobDescription": "<p>模型优化</p><p>特征工程</p>",
                    "city": "厦门",
                    "applyUrl": "https://example.com/apply/1",
                    "postDate": "2026-07-01",
                }
            ]
        }
    }
    session = FakeSession(lambda _url, _kw: FakeResponse(payload))
    monkeypatch.setattr(ats_module, "PublicTargetPolicy", PermitAllPolicy)
    source = AtsSourceConfig(
        type=AtsSourceType.JSON_FEED,
        json_url="https://api.example.com/jobs",
        json_items_path="data.list",
    )

    jobs = fetch_ats_jobs(source, session=session)

    assert jobs[0].title == "算法工程师"
    assert jobs[0].description == "模型优化\n特征工程"
    assert jobs[0].location == "厦门"
    assert jobs[0].apply_url == "https://example.com/apply/1"


def test_json_feed_rejects_non_public_url() -> None:
    session = FakeSession(lambda _url, _kw: FakeResponse({}))
    source = AtsSourceConfig(
        type=AtsSourceType.JSON_FEED,
        json_url="http://127.0.0.1/jobs",
    )

    with pytest.raises(ATSSourceError, match="私网|回环|不允许"):
        fetch_ats_jobs(source, session=session)


def test_invalid_tenant_is_rejected() -> None:
    session = FakeSession(lambda _url, _kw: FakeResponse({}))
    source = AtsSourceConfig(type=AtsSourceType.GREENHOUSE, tenant="a/b?c")

    with pytest.raises(ATSSourceError, match="非法 ATS tenant"):
        fetch_ats_jobs(source, session=session)


def test_network_errors_are_wrapped() -> None:
    def fail(_url: str, _kwargs: object):
        raise requests.ConnectionError("连接失败")

    session = FakeSession(fail)
    source = AtsSourceConfig(type=AtsSourceType.LEVER, tenant="acme")

    with pytest.raises(ATSSourceError, match="接口请求失败"):
        fetch_ats_jobs(source, session=session)


def test_ats_jobs_to_postings_maps_fields() -> None:
    company = CompanyConfig(name="甲公司", url="https://example.com/")
    jobs = [
        ATSJob(
            source_id="1",
            title="后端开发",
            description="完整 JD 正文。",
            location="福州",
            apply_url="https://example.com/apply",
            job_url="https://example.com/job/1",
            published_at="2026-08-01T00:00:00+00:00",
            recruitment_type="Full-time",
        ),
        ATSJob(source_id="2", title="无描述岗位", description=""),
    ]

    postings = ats_jobs_to_postings(jobs, company)

    assert postings[0].company == "甲公司"
    assert postings[0].apply_url == "https://example.com/apply"
    assert postings[0].source_url == "https://example.com/job/1"
    assert postings[0].jd_complete is True
    assert postings[1].jd_complete is False
    assert postings[1].jd_incomplete_reason == "ATS 接口未返回完整 JD"


def test_source_config_validation() -> None:
    with pytest.raises(ValueError, match="tenant"):
        AtsSourceConfig(type=AtsSourceType.GREENHOUSE)
    with pytest.raises(ValueError, match="json_url"):
        AtsSourceConfig(type=AtsSourceType.JSON_FEED)
    assert AtsSourceConfig(type=AtsSourceType.ASHBY, tenant="acme").tenant == "acme"
