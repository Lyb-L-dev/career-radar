"""配置读取测试：重点覆盖相对路径、环境变量和交叉字段校验。"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from career_radar.config import ConfigError, is_api_key_placeholder, load_settings
from career_radar.config_editor import mutate_config_blocks


def _yaml(delay_min: int = 0, delay_max: int = 0) -> str:
    """生成尽可能小但合法的配置，降低测试与示例配置的耦合。"""

    return f"""
app:
  database_path: data/test.db
  output_dir: output
  log_dir: logs
crawler:
  render_mode: never
  request_delay_min_seconds: {delay_min}
  request_delay_max_seconds: {delay_max}
  user_agent: Mozilla/5.0 test browser agent
llm:
  provider: openai
  model: test-model
smtp:
  enabled: false
companies:
  - name: 测试公司
    url: https://example.com/
"""


def test_load_settings_resolves_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_yaml(), encoding="utf-8")

    settings = load_settings(config_path)

    assert settings.app.database_path == (tmp_path / "data/test.db").resolve()
    assert settings.application.profile_path == (
        tmp_path / "private/application_profile.yaml"
    ).resolve()
    assert settings.application.output_dir == (
        tmp_path / "private/application_outputs"
    ).resolve()
    assert settings.companies[0].name == "测试公司"
    assert settings.candidate.graduation_year == 2026
    assert "普通本科" in settings.candidate.education_level


def test_company_classification_and_notice_mode_are_loaded(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        _yaml().replace(
            "    url: https://example.com/",
            """    url: https://example.com/
    company_type: local_soe
    industry_category: gaming
    province: 福建
    city: 厦门
    priority: high
    monitor_mode: notices
    government_honors:
      - 政府公示示例""",
        ),
        encoding="utf-8",
    )

    company = load_settings(config_path).companies[0]

    assert company.company_type.value == "local_soe"
    assert company.industry_category.value == "gaming"
    assert company.monitor_mode.value == "notices"
    assert company.province == "福建"


def test_group_recruitment_requires_parent_and_attribution_keywords(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    invalid = _yaml().replace(
        "    url: https://example.com/",
        """    url: https://group.example.com/jobs
    recruitment_channel: group_recruitment""",
    )
    config_path.write_text(invalid, encoding="utf-8")

    with pytest.raises(ConfigError, match="parent_company"):
        load_settings(config_path)

    config_path.write_text(
        invalid.replace(
            "    recruitment_channel: group_recruitment",
            """    recruitment_channel: group_recruitment
    parent_company: 示例集团
    attribution_keywords: [测试公司, 测试品牌]""",
        ),
        encoding="utf-8",
    )
    company = load_settings(config_path).companies[0]

    assert company.parent_company == "示例集团"
    assert company.attribution_keywords == ["测试公司", "测试品牌"]


def test_invalid_delay_range_is_reported(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_yaml(10, 5), encoding="utf-8")

    with pytest.raises(ConfigError, match="request_delay_min_seconds"):
        load_settings(config_path)


def test_wechat_recruitment_defaults_and_search_term_cleanup(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        _yaml()
        + """
wechat_recruitment:
  enabled: true
  opencli_command: opencli
  search_terms: [招聘, " 校招 ", 招聘]
""",
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.wechat_recruitment.search_terms == ["招聘", "校招"]
    assert settings.wechat_recruitment.results_per_query == 10
    assert settings.wechat_recruitment.max_articles_per_scan == 20


def test_missing_environment_placeholder_is_reported(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_yaml() + "\nunknown: ${CAREER_RADAR_TEST_MISSING}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="CAREER_RADAR_TEST_MISSING"):
        load_settings(config_path)


def test_project_env_replaces_inherited_template_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_yaml(), encoding="utf-8")
    (tmp_path / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-project-real-value\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "your-deepseek-api-key")

    load_settings(config_path)

    assert os.environ["DEEPSEEK_API_KEY"] == "sk-project-real-value"


def test_real_key_like_values_are_not_rejected_by_suffix_heuristics() -> None:
    assert is_api_key_placeholder("sk-your-deepseek-api-key") is True
    assert is_api_key_placeholder("your-deepseek-api-key") is True
    assert is_api_key_placeholder("sk-real-customer-api-key") is False
    assert is_api_key_placeholder("sk-your-team-issued-value") is False


def test_invalid_timezone_is_reported(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        _yaml().replace("app:\n", "app:\n  timezone: Mars/Olympus_Mons\n"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="无效时区"):
        load_settings(config_path)


def test_config_mutations_serialize_the_entire_read_modify_write_cycle(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        _yaml()
        + """
  - name: 并发删除甲
    url: https://a.example.com/
  - name: 并发删除乙
    url: https://b.example.com/
""",
        encoding="utf-8",
    )
    ready = threading.Barrier(3)

    def remove_company(name: str) -> None:
        ready.wait()

        def mutation(raw: dict[str, object]) -> tuple[dict[str, object], None]:
            companies = list(raw["companies"])  # type: ignore[arg-type]
            # 放大旧实现“两个请求都基于相同快照写回”的竞态窗口。
            time.sleep(0.02)
            remaining = [company for company in companies if company["name"] != name]
            return {"companies": remaining}, None

        mutate_config_blocks(config_path, mutation)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(remove_company, "并发删除甲"),
            executor.submit(remove_company, "并发删除乙"),
        ]
        ready.wait()
        for future in futures:
            future.result()

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert [company["name"] for company in raw["companies"]] == ["测试公司"]
