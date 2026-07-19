"""企业候选库的数据完整性与个人画像初筛测试。"""

from pathlib import Path

from career_radar.company_catalog import catalog_response, load_company_catalog
from career_radar.models import CandidateProfile


def test_generated_official_catalog_contains_at_least_one_thousand_unique_companies() -> None:
    path = Path(__file__).parents[1] / "data" / "company_candidates.json"
    catalog = load_company_catalog(path)
    items = catalog["items"]

    assert catalog["total"] == 1188
    assert catalog["total"] >= 1000
    assert sum(source["count"] for source in catalog["sources"]) == catalog["total"]
    assert len({item["id"] for item in items}) == len(items)
    assert len({item["name"] for item in items}) == len(items)
    assert all(item["evidenceUrl"].startswith("https://www.miit.gov.cn/") for item in items)
    assert sum(item["province"] == "福建" for item in items) > 0


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
    assert response["stats"]["total"] == 1188
    assert all(item["province"] == "福建" for item in response["items"])
    assert all(item["techSignals"] for item in response["items"])
    assert all(item["decision"] == "pending" and not item["monitored"] for item in response["items"])
