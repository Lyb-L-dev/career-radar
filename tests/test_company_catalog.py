"""企业候选库的数据完整性与个人画像初筛测试。"""

from pathlib import Path

from career_radar.company_catalog import catalog_response, load_company_catalog
from career_radar.models import CandidateProfile


def test_generated_official_catalog_contains_multi_source_quality_companies() -> None:
    path = Path(__file__).parents[1] / "data" / "company_candidates.json"
    catalog = load_company_catalog(path)
    items = catalog["items"]

    assert catalog["total"] == 3295
    assert catalog["total"] >= 3000
    # 同一企业可同时命中多份名单，所以来源成员数允许大于去重后的企业数。
    assert sum(source["count"] for source in catalog["sources"]) >= catalog["total"]
    assert len({item["id"] for item in items}) == len(items)
    assert len({item["name"] for item in items}) == len(items)
    assert all(item["qualityEvidenceScore"] >= 80 for item in items)
    assert all(item["scaleLevel"] != "unknown" for item in items)
    assert sum(item["province"] == "福建" for item in items) == 468
    central_enterprises = [
        item for item in items if item.get("suggestedCompanyType") == "central_soe"
    ]
    assert len(central_enterprises) == 99
    assert all(item.get("officialWebsite") for item in central_enterprises)
    assert sum(len(item["sourceKeys"]) > 1 for item in items) == 56


def test_catalog_response_prioritizes_fujian_and_never_enables_candidates() -> None:
    path = Path(__file__).parents[1] / "data" / "company_candidates.json"
    catalog = load_company_catalog(path)
    profile = CandidateProfile(
        target_roles=["数据开发", "Python 后端"],
        preferred_locations=["福州", "厦门", "上海"],
    )

    response = catalog_response(
        catalog,
        profile=profile,
        states={},
        monitored_names=set(),
        province="福建",
        tech_only=True,
        page=1,
        page_size=50,
    )

    assert response["total"] > 0
    assert response["stats"]["total"] == 3295
    assert all(item["province"] == "福建" for item in response["items"])
    assert all(item["techSignals"] for item in response["items"])
    assert all(item["decision"] == "pending" and not item["monitored"] for item in response["items"])


def test_catalog_can_filter_membership_in_merged_official_source() -> None:
    path = Path(__file__).parents[1] / "data" / "company_candidates.json"
    catalog = load_company_catalog(path)
    response = catalog_response(
        catalog,
        profile=CandidateProfile(),
        states={},
        monitored_names=set(),
        source_key="ndrc-national-enterprise-technology-centers-2023",
        page=1,
        page_size=50,
    )

    assert response["total"] == 1714
    assert all(
        "ndrc-national-enterprise-technology-centers-2023" in item["sourceKeys"]
        for item in response["items"]
    )


def test_central_enterprise_candidates_keep_official_website_and_type() -> None:
    path = Path(__file__).parents[1] / "data" / "company_candidates.json"
    response = catalog_response(
        load_company_catalog(path),
        profile=CandidateProfile(),
        states={},
        monitored_names=set(),
        source_key="sasac-central-enterprises-2026",
        page=1,
        page_size=100,
    )

    assert response["total"] == 99
    assert all(item["companyType"] == "central_soe" for item in response["items"])
    assert all(item["officialWebsite"] for item in response["items"])
