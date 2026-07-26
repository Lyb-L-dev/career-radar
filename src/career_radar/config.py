"""读取 YAML、加载 ``.env`` 并把相对路径解析成绝对路径。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values, load_dotenv
from pydantic import ValidationError

from .models import Settings


class ConfigError(ValueError):
    """配置文件不可读、环境变量缺失或字段校验失败。"""


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_LLM_KEY_NAMES = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


_API_KEY_PLACEHOLDER_PATTERN = re.compile(
    r"^(?:sk(?:-ant)?-)?your-(?:deepseek-|openai-|anthropic-)?api-key$",
    re.IGNORECASE,
)


def is_api_key_placeholder(value: str | None) -> bool:
    """识别安装模板或系统环境中遗留的空 API Key。"""

    normalized = str(value or "").strip()
    return not normalized or bool(_API_KEY_PLACEHOLDER_PATTERN.fullmatch(normalized))


def _load_project_environment(env_path: Path) -> None:
    """加载项目 .env，并用其中真值修复父进程遗留的模板 Key。

    正常的系统环境变量仍然优先；只有当前值为空或明显是 ``your-...-api-key``
    模板时，才采用项目 .env 的有效值。Windows 后台进程经常继承用户级模板变量，
    若一律 ``override=False``，Web 服务会看见模板而命令行却能读到真实 Key。
    """

    load_dotenv(env_path, override=False)
    if not env_path.is_file():
        return
    file_values = dotenv_values(env_path)
    for name in _LLM_KEY_NAMES:
        file_value = file_values.get(name)
        if (
            is_api_key_placeholder(os.getenv(name))
            and not is_api_key_placeholder(file_value)
        ):
            os.environ[name] = str(file_value).strip()


def _expand_environment(value: Any) -> Any:
    """递归展开 ``${NAME}``，并对缺失变量给出明确错误。

    不使用 ``os.path.expandvars`` 是因为后者会悄悄保留缺失占位符，
    定时任务跑到半夜才因认证失败会很难排查。
    """

    if isinstance(value, dict):
        return {key: _expand_environment(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_environment(item) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in os.environ:
            raise ConfigError(f"配置引用了未设置的环境变量：{name}")
        return os.environ[name]

    return _ENV_PATTERN.sub(replace, value)


def _resolve_paths(settings: Settings, config_dir: Path) -> Settings:
    """让定时任务无论从哪个工作目录启动，都使用同一批数据文件。"""

    for field_name in ("database_path", "company_catalog_path", "output_dir", "log_dir"):
        path = getattr(settings.app, field_name)
        if not path.is_absolute():
            setattr(settings.app, field_name, (config_dir / path).resolve())
    for field_name in ("profile_path", "output_dir", "resume_template_path"):
        path = getattr(settings.application, field_name)
        if not path.is_absolute():
            setattr(settings.application, field_name, (config_dir / path).resolve())
    return settings


def load_settings(config_path: str | Path) -> Settings:
    """加载并严格校验配置；未知字段会被拒绝以捕获拼写错误。"""

    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise ConfigError(f"找不到配置文件：{path}")

    # 优先加载配置同目录下的 .env；有效的系统变量仍然拥有最高优先级。
    _load_project_environment(path.parent / ".env")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"读取 YAML 失败：{exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("配置文件顶层必须是 YAML 对象")

    try:
        settings = Settings.model_validate(_expand_environment(raw))
    except ValidationError as exc:
        raise ConfigError(f"配置校验失败：\n{exc}") from exc
    return _resolve_paths(settings, path.parent)
