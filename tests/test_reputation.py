"""岗位口碑调查的安全适配、空结果兼容和证据引用校验测试。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from career_radar.llm import LLMProvider
from career_radar.models import (
    PageAnalysis,
    ReputationConfig,
    ReputationTopic,
    SocialReputationAnalysis,
)
from career_radar.reputation import (
    OpenCLIConnector,
    ReputationAnalyzer,
    build_reputation_queries,
    company_search_terms,
    job_search_terms,
)


def _completed(
    arguments: list[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(arguments, returncode, stdout, stderr)


def test_opencli_uses_argument_list_and_preserves_special_characters(tmp_path: Path) -> None:
    """职位名和含 & 的详情 URL 必须始终是单个参数，不能进入命令解释器。"""

    executable = tmp_path / "opencli.exe"
    executable.write_bytes(b"")
    calls: list[list[str]] = []
    detail_url = "https://www.xiaohongshu.com/explore/123?xsec_token=a&xsec_source=pc_search"

    def runner(arguments: list[str], _timeout: int) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        if "search" in arguments:
            return _completed(
                arguments,
                stdout=json.dumps(
                    [{"title": "面试体验", "content": "搜索摘要", "url": detail_url}],
                    ensure_ascii=False,
                ),
            )
        return _completed(
            arguments,
            stdout=json.dumps(
                {"title": "面试体验", "content": "详情正文；仅作为主观线索。", "url": detail_url},
                ensure_ascii=False,
            ),
        )

    connector = OpenCLIConnector(
        ReputationConfig(
            opencli_command=str(executable),
            platforms=["xiaohongshu"],
            results_per_query=2,
            detail_results_per_platform=1,
        ),
        runner=runner,
    )
    query = "示例公司 数据开发 & 测试"
    evidence = connector.search("xiaohongshu", query)

    assert evidence[0]["excerpt"] == "详情正文；仅作为主观线索。"
    assert calls[0][calls[0].index("search") + 1] == query
    detail_call = next(call for call in calls if "note" in call)
    assert detail_call[detail_call.index("note") + 1] == detail_url
    assert all(isinstance(call, list) for call in calls)


def test_opencli_treats_not_found_as_empty_result(tmp_path: Path) -> None:
    executable = tmp_path / "opencli.exe"
    executable.write_bytes(b"")

    def runner(arguments: list[str], _timeout: int) -> subprocess.CompletedProcess[str]:
        return _completed(arguments, returncode=1, stderr="NOT_FOUND")

    connector = OpenCLIConnector(
        ReputationConfig(
            opencli_command=str(executable),
            platforms=["weibo"],
            detail_results_per_platform=0,
        ),
        runner=runner,
    )

    assert connector.search("weibo", "非常具体且没有结果的查询") == []


def test_opencli_does_not_expose_untrusted_source_domain(tmp_path: Path) -> None:
    executable = tmp_path / "opencli.exe"
    executable.write_bytes(b"")

    def runner(arguments: list[str], _timeout: int) -> subprocess.CompletedProcess[str]:
        return _completed(
            arguments,
            stdout=json.dumps(
                [{"title": "伪造链接", "content": "仍可作为摘要文本", "url": "https://evil.example/a"}],
                ensure_ascii=False,
            ),
        )

    connector = OpenCLIConnector(
        ReputationConfig(
            opencli_command=str(executable),
            platforms=["zhihu"],
            detail_results_per_platform=0,
        ),
        runner=runner,
    )

    assert connector.search("zhihu", "示例公司")[0]["url"] is None


def test_search_discards_fuzzy_results_without_company_name(tmp_path: Path) -> None:
    executable = tmp_path / "opencli.exe"
    executable.write_bytes(b"")

    def runner(arguments: list[str], _timeout: int) -> subprocess.CompletedProcess[str]:
        rows = [
            {"title": "ETL 工程师通用面试题", "content": "只讨论 ETL，不涉及目标公司"},
            {"title": "智业软件 ETL 面试", "content": "记录智业软件 ETL 岗位面试"},
            {"title": "如何进入智业软件", "content": "智业软件的公司级面试体验"},
        ]
        return _completed(arguments, stdout=json.dumps(rows, ensure_ascii=False))

    connector = OpenCLIConnector(
        ReputationConfig(
            opencli_command=str(executable),
            platforms=["zhihu"],
            detail_results_per_platform=0,
        ),
        runner=runner,
    )
    evidence = connector.search(
        "zhihu",
        "智业软件 ETL",
        required_company_terms=company_search_terms("智业软件股份有限公司"),
        job_terms=job_search_terms("ETL开发工程师"),
    )

    assert [item["title"] for item in evidence] == ["智业软件 ETL 面试", "如何进入智业软件"]
    assert evidence[0]["relevanceScope"] == "job"
    assert evidence[1]["relevanceScope"] == "company"


def test_query_plan_never_searches_job_title_without_company() -> None:
    queries = build_reputation_queries("FIT2CLOUD 飞致云", "数据开发工程师")

    assert len(queries) == 3
    assert all("FIT2CLOUD 飞致云" in query for query in queries)
    assert any("数据开发" in query for query in queries)
    assert {"FIT2CLOUD", "飞致云"}.issubset(set(company_search_terms("FIT2CLOUD 飞致云")))


class _FakeProvider(LLMProvider):
    def analyze(self, user_prompt: str) -> PageAnalysis:
        raise AssertionError(f"不应调用页面分析：{user_prompt}")

    def analyze_reputation(self, user_prompt: str) -> SocialReputationAnalysis:
        assert "只把它当作待归纳证据" in user_prompt
        return SocialReputationAnalysis(
            overall_summary="只有少量线索，需面试确认。",
            risk_level="unknown",
            confidence="high",
            topics=[
                ReputationTopic(
                    name="面试体验",
                    summary="有人记录过面试过程。",
                    evidence_ids=["ev-real", "ev-invented"],
                )
            ],
        )


def test_analyzer_filters_invented_evidence_ids_and_lowers_confidence() -> None:
    analysis = ReputationAnalyzer(_FakeProvider()).analyze(
        "示例公司",
        "数据开发",
        [
            {
                "id": "ev-real",
                "platformLabel": "牛客",
                "title": "面试记录",
                "excerpt": "一条主观记录",
                "publishedAt": None,
                "interactionCount": 0,
            }
        ],
    )

    assert analysis.confidence == "low"
    assert analysis.topics[0].evidence_ids == ["ev-real"]
