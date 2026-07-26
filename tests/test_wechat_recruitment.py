"""微信公众号招聘的身份边界、OpenCLI 适配和本地导入测试。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from career_radar.models import WechatRecruitmentConfig
from career_radar.storage import JobStorage
from career_radar.web_repository import WebRepository
from career_radar.wechat_recruitment import (
    WechatOpenCLIConnector,
    WechatRecruitmentManager,
    classify_wechat_article,
)


def _account(
    *,
    verification_status: str = "verified",
    scope: str = "company",
) -> dict[str, Any]:
    return {
        "account_id": "wechat-account-1",
        "candidate_id": "candidate-1",
        "account_name": "示例科技招聘",
        "account_identifier": "example_jobs",
        "biz_id": "MzExample",
        "scope": scope,
        "parent_company": "示例集团" if scope == "group" else None,
        "attribution_keywords": ["示例数据科技"],
        "verification_status": verification_status,
        "enabled": True,
        "created_at": "2026-07-26T08:00:00+08:00",
        "updated_at": "2026-07-26T08:00:00+08:00",
    }


def _article(
    *,
    account_name: str = "示例科技招聘",
    content: str = "现面向 2026 届毕业生招聘数据开发岗，报名方式见正文。",
) -> dict[str, Any]:
    return {
        "title": "2026 届校园招聘正式启动",
        "url": "https://mp.weixin.qq.com/s?__biz=MzExample&mid=1",
        "summary": "校园招聘",
        "content": content,
        "publishedAt": "2026-07-26",
        "accountName": account_name,
        "accountIdentifier": "example_jobs",
        "bizId": "MzExample",
    }


def test_classification_requires_verified_account_and_group_attribution() -> None:
    official, _reason, matched = classify_wechat_article(
        _article(),
        [_account()],
    )
    pending, _reason, pending_match = classify_wechat_article(
        _article(),
        [_account(verification_status="pending")],
    )
    group_lead, _reason, group_match = classify_wechat_article(
        _article(content="示例集团招聘数据开发岗，报名方式见正文。"),
        [_account(scope="group")],
    )
    group_official, _reason, _matched = classify_wechat_article(
        _article(content="示例数据科技招聘数据开发岗，报名方式见正文。"),
        [_account(scope="group")],
    )

    assert official == "official_recruitment"
    assert matched is not None
    assert pending == "third_party_lead"
    assert pending_match is not None
    assert group_lead == "third_party_lead"
    assert group_match is not None
    assert group_official == "official_recruitment"


def test_result_notice_without_open_opportunity_is_not_imported() -> None:
    classification, _reason, matched = classify_wechat_article(
        _article(content="2026 届校园招聘拟录用人员名单公示。"),
        [_account()],
    )

    assert classification == "non_recruitment"
    assert matched is None


def test_connector_filters_non_wechat_urls_and_reads_markdown(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def runner(arguments: list[str], _timeout: int) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        if "search" in arguments:
            stdout = json.dumps(
                [
                    {
                        "title": "公开招聘",
                        "url": "https://mp.weixin.qq.com/s?__biz=MzExample&mid=1",
                        "summary": "招聘数据开发岗",
                        "account_name": "示例科技招聘",
                    },
                    {
                        "title": "不安全结果",
                        "url": "https://evil.example/wechat",
                    },
                ],
                ensure_ascii=False,
            )
        else:
            output = Path(arguments[arguments.index("--output") + 1])
            markdown = output / "article.md"
            markdown.write_text(
                "# 2026 届校园招聘\n\n公众号：示例科技招聘\n\n"
                "微信号：example_jobs\n\n发布时间：2026-07-26\n\n"
                "现招聘数据开发岗，报名方式见正文。",
                encoding="utf-8",
            )
            stdout = json.dumps(
                {
                    "saved": str(markdown),
                    "title": "2026 届校园招聘",
                    "account_name": "示例科技招聘",
                    "account_id": "example_jobs",
                },
                ensure_ascii=False,
            )
        return subprocess.CompletedProcess(arguments, 0, stdout, "")

    connector = WechatOpenCLIConnector(
        WechatRecruitmentConfig(opencli_command=sys.executable),
        runner=runner,
    )
    results = connector.search("示例科技招聘 校招")
    article = connector.read_article(results[0])

    assert len(results) == 1
    assert results[0]["url"].startswith("https://mp.weixin.qq.com/")
    assert article["accountName"] == "示例科技招聘"
    assert article["accountIdentifier"] == "example_jobs"
    assert article["bizId"] == "MzExample"
    assert "招聘数据开发岗" in article["content"]
    assert all("--site-session" in call for call in calls)
    assert all("ephemeral" in call for call in calls)
    assert not tmp_path.joinpath("article.md").exists()


def test_connector_health_does_not_expose_local_error_paths() -> None:
    private_path = str(Path.home() / "private" / "opencli.log")

    def runner(arguments: list[str], _timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            arguments,
            1,
            "",
            f"failed while reading {private_path}",
        )

    connector = WechatOpenCLIConnector(
        WechatRecruitmentConfig(opencli_command=sys.executable),
        runner=runner,
    )
    health = connector.health()

    assert health["available"] is False
    assert str(Path.home()) not in health["message"]
    assert private_path not in health["message"]


def _config() -> str:
    return """
app:
  timezone: Asia/Shanghai
  database_path: data/test.db
  output_dir: output
  log_dir: logs
crawler:
  render_mode: never
  request_delay_min_seconds: 0
  request_delay_max_seconds: 0
  user_agent: Mozilla/5.0 Career Radar WeChat test
llm:
  provider: deepseek
  model: test-model
wechat_recruitment:
  enabled: true
  opencli_command: opencli
  search_terms: [招聘]
  max_articles_per_scan: 10
smtp:
  enabled: false
companies:
  - name: 示例数据科技
    url: https://example.com/
"""


class _FakeConnector:
    def __init__(self, _config: WechatRecruitmentConfig) -> None:
        pass

    def health(self) -> dict[str, Any]:
        return {"enabled": True, "available": True, "message": "测试可用"}

    def search(self, _query: str) -> list[dict[str, Any]]:
        return [
            {
                "title": "示例数据科技 2026 届校园招聘",
                "url": "https://mp.weixin.qq.com/s?__biz=MzExample&mid=1",
                "summary": "招聘数据开发岗",
                "accountName": "示例科技招聘",
                "accountIdentifier": "example_jobs",
            },
            {
                "title": "招聘转载",
                "url": "https://mp.weixin.qq.com/s?__biz=Other&mid=2",
                "summary": "第三方转载",
                "accountName": "求职资讯",
            },
        ]

    def read_article(self, result: dict[str, Any]) -> dict[str, Any]:
        if "__biz=Other" in result["url"]:
            return {
                **result,
                "content": "第三方转载：示例数据科技招聘开发岗，报名方式见正文。",
                "publishedAt": "2026-07-26",
                "bizId": "Other",
            }
        return {
            **result,
            "content": "示例数据科技面向 2026 届招聘数据开发岗，报名方式见正文。",
            "publishedAt": "2026-07-26",
            "bizId": "MzExample",
        }


def test_manager_imports_only_verified_official_article(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_config(), encoding="utf-8")
    repository = WebRepository(config_path)
    repository.initialize()
    repository.save_wechat_account(_account())
    manager = WechatRecruitmentManager(
        repository,
        connector_factory=_FakeConnector,
    )

    started = manager.start(
        candidate_id="candidate-1",
        company_name="示例数据科技",
    )
    assert manager._active is not None
    manager._active.result(timeout=5)

    scan = repository.get_wechat_scan(started["id"])
    articles = repository.list_wechat_articles("candidate-1")
    sources = repository.list_candidate_sources("candidate-1")
    jobs = JobStorage(repository.settings.app.database_path).load_all_jobs()

    assert scan is not None
    assert scan["status"] == "completed"
    assert scan["stats"]["official"] == 1
    assert scan["stats"]["leads"] == 1
    assert {item["classification"] for item in articles} == {
        "official_recruitment",
        "third_party_lead",
    }
    assert {item["source_kind"] for item in sources} == {
        "official_account",
        "third_party_lead",
    }
    assert len(jobs) == 1
    assert jobs[0].record_type == "notice"
    assert jobs[0].company == "示例数据科技"
    assert "DeepSeek" in (jobs[0].match_reason or "")


def test_manager_recovers_unfinished_scan_after_restart(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_config(), encoding="utf-8")
    repository = WebRepository(config_path)
    repository.initialize()
    repository.save_wechat_scan(
        {
            "id": "wechat-scan-stale",
            "candidateId": "candidate-1",
            "companyName": "示例数据科技",
            "status": "running",
            "startedAt": "2026-07-26T08:00:00+08:00",
            "updatedAt": "2026-07-26T08:00:00+08:00",
            "finishedAt": None,
            "accounts": [],
            "queries": [],
            "articles": [],
            "stats": {
                "searched": 0,
                "read": 0,
                "official": 0,
                "leads": 0,
                "ignored": 0,
                "imported": 0,
                "new": 0,
                "updated": 0,
                "unchanged": 0,
            },
            "errors": [],
        }
    )

    WechatRecruitmentManager(repository, connector_factory=_FakeConnector)
    recovered = repository.get_wechat_scan("wechat-scan-stale")

    assert recovered is not None
    assert recovered["status"] == "interrupted"
    assert recovered["finishedAt"]
    assert "服务重启" in recovered["errors"][0]


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_manager_refuses_to_import_unverified_accounts(
    tmp_path: Path,
    status: str,
) -> None:
    config_path = tmp_path / f"{status}.yaml"
    config_path.write_text(_config(), encoding="utf-8")
    repository = WebRepository(config_path)
    repository.initialize()
    repository.save_wechat_account(_account(verification_status=status))
    manager = WechatRecruitmentManager(
        repository,
        connector_factory=_FakeConnector,
    )

    started = manager.start(
        candidate_id="candidate-1",
        company_name="示例数据科技",
    )
    assert manager._active is not None
    manager._active.result(timeout=5)

    scan = repository.get_wechat_scan(started["id"])
    jobs = JobStorage(repository.settings.app.database_path).load_all_jobs()

    assert scan is not None
    assert scan["stats"]["official"] == 0
    assert jobs == []
