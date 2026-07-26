"""申请材料专用 DeepSeek 结构化调用网关。"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from ..llm import (
    FatalLLMError,
    LLMError,
    RetryableLLMError,
    _extract_json_object,
    _request_error,
    _require_api_key,
)
from ..models import LLMConfig

LOGGER = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class ApplicationLLMGateway(Protocol):
    """工作流只依赖此窄接口，测试时不需要访问真实 API。"""

    def generate(self, response_model: type[T], system_prompt: str, user_prompt: str) -> T:
        """返回经过 Pydantic 严格校验的结构化对象。"""


class DeepSeekApplicationGateway:
    """通过 OpenAI 兼容接口调用 DeepSeek JSON Object 模式。"""

    DEFAULT_BASE_URL = "https://api.deepseek.com"

    def __init__(
        self,
        config: LLMConfig,
        *,
        client: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if config.provider != "deepseek":
            raise ValueError("申请材料第二阶段目前只支持 DeepSeek provider")
        if client is None:
            api_key = _require_api_key("DEEPSEEK_API_KEY", "DeepSeek")
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise FatalLLMError("DeepSeek 适配依赖 openai SDK，请执行 pip install -e .") from exc
            client = OpenAI(
                api_key=api_key,
                base_url=config.base_url or self.DEFAULT_BASE_URL,
                timeout=config.request_timeout_seconds,
                max_retries=0,
            )
        self.client = client
        self.config = config
        self.sleeper = sleeper

    def _generate_once(
        self,
        response_model: type[T],
        system_prompt: str,
        user_prompt: str,
    ) -> T:
        schema = json.dumps(response_model.model_json_schema(), ensure_ascii=False)
        full_prompt = (
            f"{user_prompt}\n\n"
            "只输出一个 JSON 对象，不要输出 Markdown、解释或代码围栏。\n"
            f"JSON 必须严格符合以下 Schema：\n{schema}"
        )
        request: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": self.config.max_output_tokens,
        }
        if self.config.disable_thinking:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            completion = self.client.chat.completions.create(**request)
        except Exception as exc:
            raise _request_error("DeepSeek 申请工作流", exc) from exc
        content = completion.choices[0].message.content or ""
        if not content.strip():
            raise RetryableLLMError("DeepSeek 申请工作流返回空内容")
        try:
            payload = _extract_json_object(content, "DeepSeek 申请工作流")
            return response_model.model_validate(payload)
        except LLMError:
            raise
        except ValidationError as exc:
            raise RetryableLLMError(f"DeepSeek 结构化结果校验失败：{exc}") from exc

    def generate(self, response_model: type[T], system_prompt: str, user_prompt: str) -> T:
        last_error: RetryableLLMError | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                return self._generate_once(response_model, system_prompt, user_prompt)
            except FatalLLMError:
                raise
            except RetryableLLMError as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    delay = min(2 ** (attempt - 1), 20)
                    LOGGER.warning(
                        "DeepSeek 申请工作流瞬时错误，%s 秒后重试（%s/%s）：%s",
                        delay,
                        attempt,
                        self.config.max_retries,
                        exc,
                    )
                    self.sleeper(delay)
            except Exception as exc:
                raise FatalLLMError(
                    f"申请 LLM 网关返回未分类异常：{type(exc).__name__}: {exc}"
                ) from exc
        raise RetryableLLMError(
            f"DeepSeek 申请工作流连续失败 {self.config.max_retries} 次：{last_error}"
        )
