"""官网站点地图只能引导发现同域招聘页面，不直接制造岗位事实。"""

from pathlib import Path

import pytest

from career_radar.crawler import CrawlError, FetchedPage
from career_radar.models import (
    AppConfig,
    CompanyConfig,
    CrawlerConfig,
    JobPosting,
    LLMConfig,
    MonitorMode,
    PageAnalysis,
    Settings,
)
from career_radar.pipeline import CompanyMonitor
from career_radar.sitemap_discovery import discover_recruitment_urls, parse_sitemap_xml


def test_namespaced_sitemap_accepts_only_direct_same_host_locations() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://jobs.example.com/campus/2026</loc></url>
      <url><loc>https://jobs.example.com/news/招聘公告</loc></url>
      <url><loc>https://other.example.com/campus/2026</loc></url>
      <url><loc>http://127.0.0.1/private</loc></url>
      <url><other><loc>https://jobs.example.com/campus/spoof</loc></other></url>
    </urlset>"""

    links = parse_sitemap_xml(xml, "jobs.example.com")

    assert links.pages == (
        "https://jobs.example.com/campus/2026",
        "https://jobs.example.com/news/招聘公告",
    )
    assert links.sitemaps == ()


@pytest.mark.parametrize(
    "content",
    [
        "<html><a href='https://jobs.example.com/campus'>job</a></html>",
        "<urlset><url><loc>broken",
        "<!DOCTYPE urlset [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><urlset><url><loc>&xxe;</loc></url></urlset>",
    ],
)
def test_malformed_or_non_sitemap_data_cannot_yield_urls(content: str) -> None:
    with pytest.raises(ValueError):
        parse_sitemap_xml(content, "jobs.example.com")


def test_nested_sitemap_prioritizes_recruitment_and_obeys_budgets() -> None:
    start = "https://jobs.example.com/"
    index = """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://jobs.example.com/product.xml</loc></sitemap>
      <sitemap><loc>https://jobs.example.com/careers.xml</loc></sitemap>
    </sitemapindex>"""
    jobs = """<urlset><url><loc>https://jobs.example.com/campus/2026</loc></url>
      <url><loc>https://jobs.example.com/about</loc></url>
      <url><loc>https://other.example.com/recruit</loc></url></urlset>"""
    calls: list[str] = []

    class Fetcher:
        def fetch_sitemap(self, url: str) -> FetchedPage:
            calls.append(url)
            if url.endswith("product.xml"):
                raise CrawlError("不应优先抓取产品地图")
            return FetchedPage(url, url, jobs if url.endswith("careers.xml") else index, False, 200)

    found = discover_recruitment_urls(start, Fetcher())

    assert found == ["https://jobs.example.com/campus/2026"]
    assert calls[:2] == ["https://jobs.example.com/sitemap.xml", "https://jobs.example.com/careers.xml"]


def test_monitor_reaches_notice_hidden_from_homepage_via_sitemap(tmp_path: Path) -> None:
    company = CompanyConfig(
        name="测试企业",
        url="https://jobs.example.com/",
        monitor_mode=MonitorMode.NOTICES,
        max_pages=3,
    )
    settings = Settings(
        app=AppConfig(database_path=tmp_path / "jobs.db"),
        crawler=CrawlerConfig(
            render_mode="never",
            request_delay_min_seconds=0,
            request_delay_max_seconds=0,
            user_agent="Mozilla/5.0 Career Radar test",
        ),
        llm=LLMConfig(provider="openai", model="test"),
        companies=[company],
    )
    notice_url = "https://jobs.example.com/news/recruit-2026"
    pages: list[str] = []

    class Fetcher:
        def fetch_sitemap(self, url: str) -> FetchedPage:
            sitemap = f"<urlset><url><loc>{notice_url}</loc></url><url><loc>https://jobs.example.com/product</loc></url></urlset>"
            return FetchedPage(url, url, sitemap, False, 200)

        def fetch(self, url: str) -> FetchedPage:
            pages.append(url)
            return FetchedPage(url, url, "<main>2026 年校园招聘公告</main>" if url == notice_url else "<main>官网首页</main>", False, 200)

    class Analyzer:
        def analyze_page(self, _company: str, url: str, *_args: object, **_kwargs: object) -> PageAnalysis:
            if url != notice_url:
                return PageAnalysis(page_type="no_jobs", contains_recruitment_info=False)
            return PageAnalysis(
                page_type="job_detail",
                contains_recruitment_info=True,
                jobs=[JobPosting(record_type="notice", company="测试企业", title="2026 年校园招聘公告", description="面向应届生公开招聘", source_url=url)],
            )

    result = CompanyMonitor(settings, Fetcher(), Analyzer()).crawl(company)  # type: ignore[arg-type]

    assert pages == [company.url, notice_url]
    assert result.errors == []
    assert [job.title for job in result.jobs] == ["2026 年校园招聘公告"]
