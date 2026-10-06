"""HTML 清洗与招聘链接启发式识别测试。"""

from pathlib import Path

import pytest

from career_radar.discovery import (
    _preferred_visible_text,
    heuristic_follow_links,
    parse_html,
)
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


def test_crawl_url_preserves_recruitment_filter_query_variants() -> None:
    first = canonicalize_crawl_url(
        "https://example.com/alljobs?id=&jobType=1&campus=1&utm_source=test"
    )
    second = canonicalize_crawl_url("https://example.com/alljobs?jobType=9&id=")
    detail = canonicalize_crawl_url(
        "https://example.com/job?id=1001&jobType=campus"
    )

    assert first == "https://example.com/alljobs?campus=1&jobType=1"
    assert second == "https://example.com/alljobs?jobType=9"
    assert second != first
    assert "id=1001" in detail


def test_crawl_url_keeps_required_non_filter_entry_parameter() -> None:
    url = canonicalize_crawl_url(
        "https://job.chinatelecom.com.cn/wt/TELE/web/index?brandCode=1&jobType=campus"
    )

    assert url.endswith("?brandCode=1&jobType=campus")


def test_parse_html_keeps_spa_job_route_distinct_from_page_anchor() -> None:
    document = parse_html(
        '<a href="#/job/1001">查看职位</a><a href="#jobs">跳转岗位区域</a>',
        "https://example.com/careers",
    )

    urls = {item.url for item in document.links}
    assert "https://example.com/careers#/job/1001" in urls
    assert "https://example.com/careers" not in urls


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


def test_recruitment_category_links_are_followed_inside_join_section() -> None:
    document = parse_html(
        '<a href="/about/join/yanfa">研发类</a>'
        '<a href="/about/join/zhineng">职能类</a>'
        '<a href="/about/product">产品介绍</a>',
        "https://example.com/about/join",
    )

    follow = heuristic_follow_links(document, "career_home", 10)

    assert "https://example.com/about/join/yanfa" in follow
    assert "https://example.com/about/join/zhineng" in follow
    assert "https://example.com/about/product" not in follow


def test_job_detail_with_query_id_is_followed_from_official_job_list() -> None:
    document = parse_html(
        '<a href="/zh/job?id=40">Cloud 技术支持工程师</a>'
        '<a href="/zh/alljobs?jobType=1&id=">开发类筛选</a>',
        "https://example.com/zh/alljobs",
    )

    follow = heuristic_follow_links(document, "job_list", 10)

    assert "https://example.com/zh/job?id=40" in follow
    assert "https://example.com/zh/alljobs?jobType=1&id=" not in follow


def test_image_only_year_zp_archive_is_treated_as_job_detail() -> None:
    document = parse_html(
        '<a href="/archives/2026zp"><img src="poster.png" alt=""></a>',
        "https://example.com/",
    )

    follow = heuristic_follow_links(document, "mixed", 20)

    assert follow == ["https://example.com/archives/2026zp"]


def _raise(*_args: object) -> None:
    raise RuntimeError("extractor crashed")


def test_preferred_text_falls_back_when_extractor_unavailable() -> None:
    fallback = "正文内容" * 120
    assert _preferred_visible_text(
        "<html></html>", fallback, extractor=lambda html: None
    ) == fallback
    assert _preferred_visible_text(
        "<html></html>", fallback, extractor=_raise
    ) == fallback


def test_preferred_text_rejects_too_short_result() -> None:
    fallback = "正文内容" * 120
    assert _preferred_visible_text(
        "<html></html>", fallback, extractor=lambda html: "太短的结果"
    ) == fallback


def test_preferred_text_uses_cleaner_result_when_enough_content() -> None:
    fallback = "导航链接\n" * 60
    cleaner = "岗位职责正文" + "详细内容" * 40
    result = _preferred_visible_text(
        "<html></html>", fallback, extractor=lambda html: cleaner
    )
    assert result == cleaner


def test_parse_html_prefers_trafilatura_when_installed() -> None:
    pytest.importorskip("trafilatura")
    body = "岗位职责：负责系统设计与实现。" + "详细技术要求。" * 80
    document = parse_html(
        f"<html><head><title>招聘</title></head>"
        f"<body><nav>首页 关于我们 产品中心</nav><div class='article'>{body}</div>"
        f"<footer>备案号 ©2026</footer></body></html>",
        "https://example.com/careers",
    )
    assert "岗位职责" in document.text
    assert len(document.text) >= 100


def test_parse_html_preserves_short_recruitment_requirement_in_table() -> None:
    pytest.importorskip("trafilatura")
    paragraphs = "".join(
        f"<p>职责{i}：参与平台服务研发，负责需求分析、方案设计、开发测试与维护。</p>"
        for i in range(14)
    )
    html = (
        "<html><body><article><h1>2026 招聘公告</h1>"
        + paragraphs
        + "<table><tr><th>岗位</th><th>专业要求</th></tr>"
        + "<tr><td>数据工程师</td><td>统计学硕士</td></tr></table>"
        + "</article></body></html>"
    )

    document = parse_html(html, "https://example.com/jobs")

    assert "统计学硕士" in document.text
