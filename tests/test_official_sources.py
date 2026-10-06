"""First-party structured source extraction without paid model calls."""

import json
from pathlib import Path

from career_radar.crawler import FetchedPage
from career_radar.models import AppConfig, CompanyConfig, CrawlerConfig, LLMConfig, Settings
from career_radar.official_sources import extract_official_jobs
from career_radar.pipeline import CompanyMonitor
from career_radar.storage import JobStorage

MEITU_JOB_ID = "5f0cb9cf-c9ed-4673-986d-75ad9f9e20e6"


def _next_f_script(value: str) -> str:
    return "<script>self.__next_f.push(" + json.dumps([1, value], ensure_ascii=False) + ")</script>"


MEITU_LIST_HTML = (
    "<html><body><main>校园招聘岗位</main>"
    + _next_f_script(
        'a:["$","main",null,{"initJobList":[{"jobId":"'
        + MEITU_JOB_ID
        + '","title":"AI 应用开发实习生","modeName":"校园招聘"}]}]'
    )
    + "</body></html>"
)
MEITU_DETAIL_HTML = (
    "<html><body><div class='content_section__KPieN'>"
    "<div class='content_sectionTitle__P8Ymo'>职位描述</div>"
    "<p>【岗位职责】负责 AI 应用开发、接口联调、Agent 工作流实现，并参与上线和问题排查。</p>"
    "<p>【任职要求】面向应届生，熟悉 Python，具有真实项目经验，能说明自己的实现与结果。</p>"
    "</div>"
    + _next_f_script(
        'a:["$","main",null,{"jobData":{"jobInfo":{"jobId":"'
        + MEITU_JOB_ID
        + '","title":"AI 应用开发实习生","modeName":"校园招聘",'
        '"locations":"福建厦门市","publishedAt":"2026-09-20"}}}]'
    )
    + "</body></html>"
)


EMQ_HTML = """
<html><body><div class="all-jobs">
  <div class="job-box">
    <a href="/zh/job?id=40">Cloud 技术支持工程师</a>
    <p class="job-contents">经验要求：在校/应届 / 本科及以上 / IT技术支持 / 全职
    职位描述：负责客户快速接入 EMQX Cloud，排查运行中的问题，指导部署并解决客户反馈，
    与研发团队协作定位缺陷，记录案例，编写技术文档，完成服务交付。</p>
  </div>
  <div class="job-box">
    <a href="/zh/job?id=75">KA 销售</a>
    <p class="job-contents">职位描述：联系客户。</p>
  </div>
</div></body></html>
"""


def test_emq_official_extractor_keeps_job_identity_and_incomplete_state() -> None:
    extracted = extract_official_jobs(
        "https://careers.emqx.com/zh/alljobs", EMQ_HTML, "EMQ 映云科技"
    )

    assert extracted is not None
    assert extracted.list_complete is True
    assert len(extracted.jobs) == 2
    first, second = extracted.jobs
    assert first.title == "Cloud 技术支持工程师"
    assert first.source_url == "https://careers.emqx.com/zh/job?id=40"
    assert "本科及以上" in first.description
    assert first.jd_complete is True
    assert first.profile_fit_level.value == "unknown"
    assert second.jd_complete is False
    assert second.jd_incomplete_reason


def test_emq_extractor_ignores_untrusted_job_link() -> None:
    html = EMQ_HTML.replace("/zh/job?id=40", "https://other.example/job?id=40")
    extracted = extract_official_jobs(
        "https://careers.emqx.com/zh/alljobs", html, "EMQ 映云科技"
    )

    assert extracted is not None
    assert [job.title for job in extracted.jobs] == ["KA 销售"]


def test_emq_complete_card_accepts_different_section_headings() -> None:
    html = EMQ_HTML.replace(
        "职位描述：联系客户。",
        "工作内容：负责企业客户需求沟通、产品演示与合同跟进；"
        "任职条件：能解释产品使用方式、反馈实施问题，并与技术团队协作完成交付，"
        "持续记录客户反馈与项目进度。"
        "每周整理客户问题、复现步骤与解决方案，为下一轮产品改进提供可验证的材料。",
    )
    result = extract_official_jobs(
        "https://careers.emqx.com/zh/alljobs", html, "EMQ 映云科技"
    )

    assert result is not None
    assert result.jobs[1].title == "KA 销售"
    assert result.jobs[1].jd_complete is True


def test_official_extractor_does_not_claim_other_websites() -> None:
    assert extract_official_jobs("https://example.com/jobs", EMQ_HTML, "示例") is None


def test_meitu_list_yields_real_detail_links_without_llm() -> None:
    result = extract_official_jobs(
        "https://hr.meitu.com/?page=1&recruitmentType=campus",
        MEITU_LIST_HTML,
        "美图公司",
    )

    assert result is not None
    assert result.jobs == []
    assert result.list_complete is True
    assert result.follow_urls == [f"https://hr.meitu.com/jobCampus/{MEITU_JOB_ID}"]


def test_meitu_detail_keeps_full_jd_and_official_identity() -> None:
    result = extract_official_jobs(
        f"https://hr.meitu.com/jobCampus/{MEITU_JOB_ID}",
        MEITU_DETAIL_HTML,
        "美图公司",
    )

    assert result is not None
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "AI 应用开发实习生"
    assert "岗位职责" in job.description and "任职要求" in job.description
    assert job.jd_complete is True
    assert job.source_url.endswith(MEITU_JOB_ID)
    assert job.published_at == "2026-09-20"


def test_meitu_complete_detail_does_not_require_chinese_section_words() -> None:
    english_description = (
        "Build student design communities, organize campus workshops, and collect product "
        "feedback from peers. Coordinate events with the product team, document outcomes, "
        "and share examples of successful outreach across the semester."
    )
    html = MEITU_DETAIL_HTML.replace(
        "【岗位职责】负责 AI 应用开发、接口联调、Agent 工作流实现，并参与上线和问题排查。",
        english_description,
    ).replace(
        "【任职要求】面向应届生，熟悉 Python，具有真实项目经验，能说明自己的实现与结果。",
        "",
    )

    result = extract_official_jobs(
        f"https://hr.meitu.com/jobCampus/{MEITU_JOB_ID}", html, "美图公司"
    )

    assert result is not None
    assert result.jobs[0].jd_complete is True


def test_emq_monitor_extracts_jobs_without_llm(tmp_path: Path) -> None:
    company = CompanyConfig(
        name="EMQ 映云科技",
        url="https://careers.emqx.com/zh/alljobs",
        max_pages=2,
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

    class Fetcher:
        def fetch(self, url: str) -> FetchedPage:
            return FetchedPage(url, url, EMQ_HTML, False, 200)

    class Analyzer:
        def analyze_page(self, *_args, **_kwargs):
            raise AssertionError("EMQ 结构化页面不需要付费模型")

    events = []
    result = CompanyMonitor(settings, Fetcher(), Analyzer()).crawl(
        company, lambda _name, event: events.append(event)
    )

    assert result.errors == []
    assert result.pages_visited == 1
    assert len(result.jobs) == 2
    assert events[-1]["llmExtracted"] is False


def test_meitu_monitor_follows_script_discovered_detail_without_llm(tmp_path: Path) -> None:
    company = CompanyConfig(
        name="美图公司",
        url="https://hr.meitu.com/?page=1&recruitmentType=campus",
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

    class Fetcher:
        def fetch(self, url: str) -> FetchedPage:
            html = MEITU_DETAIL_HTML if MEITU_JOB_ID in url else MEITU_LIST_HTML
            return FetchedPage(url, url, html, False, 200)

    class Analyzer:
        def analyze_page(self, *_args, **_kwargs):
            raise AssertionError("美图结构化页面不需要付费模型")

    result = CompanyMonitor(settings, Fetcher(), Analyzer()).crawl(company)  # type: ignore[arg-type]

    assert result.errors == []
    assert result.pages_visited == 2
    assert [job.title for job in result.jobs] == ["AI 应用开发实习生"]


def test_cached_meitu_list_still_follows_detail_links(tmp_path: Path) -> None:
    company = CompanyConfig(
        name="美图公司",
        url="https://hr.meitu.com/?page=1&recruitmentType=campus",
        max_pages=3,
    )
    settings = Settings(
        app=AppConfig(database_path=tmp_path / "jobs.db"),
        crawler=CrawlerConfig(
            render_mode="auto",
            request_delay_min_seconds=0,
            request_delay_max_seconds=0,
            user_agent="Mozilla/5.0 Career Radar test",
        ),
        llm=LLMConfig(provider="openai", model="test"),
        companies=[company],
    )
    storage = JobStorage(settings.app.database_path)
    storage.initialize()
    calls: list[str] = []

    class Fetcher:
        def fetch(self, url: str, _headers=None) -> FetchedPage:
            calls.append(url)
            html = MEITU_DETAIL_HTML if MEITU_JOB_ID in url else MEITU_LIST_HTML
            return FetchedPage(url, url, html, False, 200)

    class Analyzer:
        def analyze_page(self, *_args, **_kwargs):
            raise AssertionError("缓存和直接提取均不应调用 LLM")

    monitor = CompanyMonitor(settings, Fetcher(), Analyzer(), storage)  # type: ignore[arg-type]
    first = monitor.crawl(company)
    second = monitor.crawl(company)

    assert first.errors == second.errors == []
    assert first.pages_visited == second.pages_visited == 2
    assert len(second.jobs) == 1
    assert calls.count(f"https://hr.meitu.com/jobCampus/{MEITU_JOB_ID}") == 2
