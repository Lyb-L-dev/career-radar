"""配置读取测试：重点覆盖相对路径、环境变量和交叉字段校验。"""

from pathlib import Path

import pytest

from career_radar.config import ConfigError, load_settings


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


def test_invalid_delay_range_is_reported(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_yaml(10, 5), encoding="utf-8")

    with pytest.raises(ConfigError, match="request_delay_min_seconds"):
        load_settings(config_path)


def test_missing_environment_placeholder_is_reported(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_yaml() + "\nunknown: ${CAREER_RADAR_TEST_MISSING}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="CAREER_RADAR_TEST_MISSING"):
        load_settings(config_path)


def test_invalid_timezone_is_reported(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        _yaml().replace("app:\n", "app:\n  timezone: Mars/Olympus_Mons\n"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="无效时区"):
        load_settings(config_path)
