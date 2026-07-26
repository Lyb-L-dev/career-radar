"""企业官网自动发现的第三方过滤与置信度测试。"""

from career_radar.company_website import discover_official_website


def test_exact_company_title_and_snippet_select_official_homepage() -> None:
    result = discover_official_website(
        "福建福特科光电股份有限公司",
        [
            {
                "rank": 1,
                "title": "福建福特科光电股份有限公司 - 精密光学",
                "url": "https://www.foctek.com/",
                "snippet": "福建福特科光电股份有限公司为客户提供高精度光学元件。",
            },
            {
                "rank": 2,
                "title": "企业概况 - Foctek",
                "url": "https://www.foctek.com/About/Profile.html",
                "snippet": "福建福特科光电股份有限公司成立于 2002 年。",
            },
            {
                "rank": 3,
                "title": "福建福特科光电股份有限公司 - 爱企查",
                "url": "https://aiqicha.baidu.com/company_detail/123",
                "snippet": "福建福特科光电股份有限公司工商信息。",
            },
        ],
    )

    assert result["status"] == "found"
    assert result["confidence"] == "high"
    assert result["website"] == "https://www.foctek.com/"
    assert all("baidu.com" not in item["website"] for item in result["candidates"])


def test_search_directory_and_recruitment_pages_are_never_treated_as_official() -> None:
    rows = [
        {
            "rank": 1,
            "title": "测试数据科技有限公司招聘 - BOSS直聘",
            "url": "https://www.zhipin.com/gongsi/example.html",
            "snippet": "测试数据科技有限公司招聘职位。",
        },
        {
            "rank": 2,
            "title": "测试数据科技有限公司 - 天眼查",
            "url": "https://www.tianyancha.com/company/123",
            "snippet": "测试数据科技有限公司工商信息。",
        },
    ]

    result = discover_official_website("测试数据科技有限公司", rows)

    assert result["status"] == "not_found"
    assert result["website"] is None
    assert result["candidates"] == []


def test_single_weak_result_requires_manual_confirmation() -> None:
    result = discover_official_website(
        "测试数据科技有限公司",
        [
            {
                "rank": 4,
                "title": "测试数据科技有限公司",
                "url": "https://example-company.com/about",
                "snippet": "提供数据服务。",
            }
        ],
    )

    assert result["status"] == "ambiguous"
    assert result["website"] == "https://example-company.com/"
    assert result["candidates"][0]["score"] < 85
