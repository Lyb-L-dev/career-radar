"""HTML 清洗与招聘链接启发式识别测试。"""

from pathlib import Path

from career_radar.discovery import heuristic_follow_links, parse_html
from career_radar.url_utils import canonicalize_crawl_url, normalize_request_url


def test_parse_html_extracts_and_scores_links() -> None:
    fixture = Path(__file__).parent / "fixtures/career_page.html"
    document = parse_html(fixture.read_text(encoding="utf-8"), "https://example.com/")

    urls = {link.url for link in document.links}
    assert "https://example.com/jobs/1001" in urls
    assert "不应进入正文" not in document.text
    assert any(link.career_score > 0 for link in document.links if link.url.endswith("/campus"))

    follow = heuristic_follow_links(document, "job_list", 20)
    assert "https://example.com/jobs/1001" in follow
    assert "https://example.com/jobs/1002" in follow


def test_job_detail_does_not_blindly_follow_apply_links() -> None:
    document = parse_html(
        '<a href="/jobs/next">相关职位</a><a href="/apply">立即申请</a>',
        "https://example.com/jobs/1",
    )
    assert heuristic_follow_links(document, "job_detail", 20) == []


def test_news_and_tag_pages_are_not_followed() -> None:
    document = parse_html(
        """
        <a href="/jobs/1001">查看职位</a>
        <a href="/tags/recruitment">招聘新闻标签</a>
        <a href="/news/campus-award">校园招聘获奖新闻</a>
        """,
        "https://example.com/careers",
    )

    follow = heuristic_follow_links(document, "job_list", 20)

    assert "https://example.com/jobs/1001" in follow
    assert all("/tags/" not in url and "/news/" not in url for url in follow)


def test_official_recruitment_notice_inside_news_section_is_followed() -> None:
    """国企把正式招聘公告放在新闻栏目时，仅凭路径不能误杀。"""

    document = parse_html(
        """
        <a href="/news/2026-hiring">福州某市属国企2026年公开招聘公告</a>
        <a href="/news/campus-award">校园招聘获奖新闻</a>
        """,
        "https://example.gov.cn/recruitment",
    )

    follow = heuristic_follow_links(document, "job_list", 20)

    assert "https://example.gov.cn/news/2026-hiring" in follow
    assert "https://example.gov.cn/news/campus-award" not in follow


def test_crawl_url_collapses_blank_and_filter_query_variants() -> None:
    first = canonicalize_crawl_url(
        "https://example.com/alljobs?id=&jobType=1&campus=1&utm_source=test"
    )
    second = canonicalize_crawl_url("https://example.com/alljobs?jobType=9&id=")
    detail = canonicalize_crawl_url(
        "https://example.com/job?id=1001&jobType=campus"
    )

    assert first == "https://example.com/alljobs"
    assert second == first
    assert "id=1001" in detail


def test_crawl_url_keeps_required_non_filter_entry_parameter() -> None:
    url = canonicalize_crawl_url(
        "https://job.chinatelecom.com.cn/wt/TELE/web/index?brandCode=1&jobType=campus"
    )

    assert url.endswith("?brandCode=1")


def test_request_url_preserves_server_directory_trailing_slash() -> None:
    assert normalize_request_url("https://example.gov.cn/notice/") == (
        "https://example.gov.cn/notice/"
    )


def test_mixed_page_does_not_expand_broad_career_only_navigation() -> None:
    document = parse_html(
        """
        <a href="/intern-life">实习生活与员工故事</a>
        <a href="/jobs/1001">招聘岗位：后端开发</a>
        """,
        "https://example.com/careers",
    )

    follow = heuristic_follow_links(document, "mixed", 20)

    assert "https://example.com/jobs/1001" in follow
    assert "https://example.com/intern-life" not in follow


def test_image_only_year_zp_archive_is_treated_as_job_detail() -> None:
    document = parse_html(
        '<a href="/archives/2026zp"><img src="poster.png" alt=""></a>',
        "https://example.com/",
    )

    follow = heuristic_follow_links(document, "mixed", 20)

    assert follow == ["https://example.com/archives/2026zp"]
