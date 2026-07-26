"""为 Web 管理端提供保守的 YAML 局部更新。

配置文件包含大量中文说明，直接 ``yaml.safe_dump`` 整个对象会丢失全部注释。
这里仅替换明确提交的顶层区块，并在原子覆盖前使用现有 Pydantic 模型完整校验。
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import yaml

from .config import ConfigError, load_settings

_WRITE_LOCK = threading.Lock()
_TOP_LEVEL_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:")
_MutationResult = TypeVar("_MutationResult")


def load_raw_config(config_path: str | Path) -> dict[str, Any]:
    """读取未做路径解析的 YAML 字典，便于保留相对路径和用户书写方式。"""

    path = Path(config_path).expanduser().resolve()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"读取 YAML 失败：{exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("配置文件顶层必须是 YAML 对象")
    return raw


def _load_raw_text(text: str) -> dict[str, Any]:
    """解析已经在写锁内读取的 YAML 文本。"""

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"读取 YAML 失败：{exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("配置文件顶层必须是 YAML 对象")
    return raw


def _replace_block(text: str, key: str, value: Any) -> str:
    """替换单个顶层 YAML 区块；找不到时追加到文件末尾。"""

    lines = text.splitlines(keepends=True)
    start: int | None = None
    end = len(lines)
    for index, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}\s*:", line):
            start = index
            break
    if start is not None:
        for index in range(start + 1, len(lines)):
            if _TOP_LEVEL_KEY.match(lines[index]):
                end = index
                break

    rendered = yaml.safe_dump(
        {key: value},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    if not rendered.endswith("\n"):
        rendered += "\n"

    if start is None:
        separator = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return f"{text}{separator}{rendered}"
    return "".join(lines[:start]) + rendered + "".join(lines[end:])


def _write_config_blocks(path: Path, text: str, updates: dict[str, Any]) -> None:
    """在调用方持有写锁时校验并原子写回指定顶层区块。"""

    for key, value in updates.items():
        text = _replace_block(text, key, value)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            prefix=".career-radar-config-",
            suffix=".yaml",
            dir=path.parent,
            delete=False,
        ) as handle:
            handle.write(text)
            temp_path = Path(handle.name)

        # 使用与正式启动完全相同的加载路径，避免 Web 表单写出 CLI 无法读取的配置。
        load_settings(temp_path)
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def mutate_config_blocks(
    config_path: str | Path,
    mutator: Callable[[dict[str, Any]], tuple[dict[str, Any], _MutationResult]],
) -> _MutationResult:
    """在同一写锁内完成读取、业务变更、校验与原子替换。

    适用于企业列表等读改写操作，避免并发请求基于旧快照覆盖已经完成的修改。
    当前锁保护单个 Python 进程；若未来启用多个 API worker，需升级为跨进程文件锁。
    """

    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise ConfigError(f"找不到配置文件：{path}")

    with _WRITE_LOCK:
        text = path.read_text(encoding="utf-8")
        raw = _load_raw_text(text)
        updates, result = mutator(raw)
        if updates:
            _write_config_blocks(path, text, updates)
        return result


def update_config_blocks(config_path: str | Path, updates: dict[str, Any]) -> None:
    """校验后原子写回指定区块，并保留一个最近版本的 ``.bak`` 备份。"""

    if not updates:
        return

    mutate_config_blocks(config_path, lambda _raw: (updates, None))
