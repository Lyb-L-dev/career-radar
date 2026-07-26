"""读取版本化中文 Prompt，并安全序列化不可信输入。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROMPT_VERSION = "2026-07-22.v1"
_PROMPT_DIR = Path(__file__).with_name("prompts")


def load_prompt(name: str) -> str:
    """只允许读取随包分发的固定 Prompt 名称。"""

    if not name.replace("_", "").isalnum():
        raise ValueError("无效 Prompt 名称")
    path = _PROMPT_DIR / f"{name}.md"
    if not path.is_file():
        raise ValueError(f"找不到申请 Prompt：{name}")
    return path.read_text(encoding="utf-8").strip()


def prompt_payload(**values: Any) -> str:
    """把 JD、画像、草稿等作为 JSON 数据块传入，避免字符串拼接混淆边界。"""

    return json.dumps(values, ensure_ascii=False, sort_keys=True, indent=2)
