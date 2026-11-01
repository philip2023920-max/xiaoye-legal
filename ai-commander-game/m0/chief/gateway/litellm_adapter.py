"""OpenAI 相容路徑：LiteLLM（統一呼叫與 usage）＋ instructor（schema 驗證、把錯誤回饋給模型重試）。

適用 Ollama、OpenAI、DeepSeek、OpenRouter、LM Studio、vLLM…凡是 LiteLLM 認得的都行。
最低公分母策略：schema 進提示 → 回 JSON → 本地驗證 → 不合格重試最多 2 次（共 3 次）。
Ollama 另走 json_schema → json_object → 純提示 三段降級（端點不支援時自動降級）。
"""
from __future__ import annotations

import logging
import os
import time
from typing import Type

from pydantic import BaseModel

from ..board import estimate_tokens
from ..meter import Usage
from ..orders import ChiefOrders
from .base import ChatResponse, ChiefResponse, ParsedResponse

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")  # 不要每次 import 都上網抓價格表
DEFAULT_TIMEOUT_S = 120
DEFAULT_MODELS = {
    "ollama": "ollama/qwen2.5:3b",
    "openai": "openai/gpt-4o-mini",
    "deepseek": "deepseek/deepseek-chat",
    "openrouter": "openrouter/deepseek/deepseek-chat",
}
MAX_RETRIES = 2


def _usage_from(completion, messages: list[dict], text: str) -> Usage:
    u = getattr(completion, "usage", None)
    if u and getattr(u, "prompt_tokens", None) is not None:
        details = getattr(u, "prompt_tokens_details", None)
        cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
        cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0   # LiteLLM 轉 Anthropic 時會帶
        return Usage(prompt_tokens=int(u.prompt_tokens or 0), completion_tokens=int(u.completion_tokens or 0),
                     cache_read_tokens=int(cached), cache_write_tokens=int(cache_write))
    # 供應商沒回 usage：用與戰情板相同的粗估法（ASCII 4 字元＝1、非 ASCII 1 字＝1）並標記
    prompt_text = "".join(m.get("content", "") for m in messages)
    return Usage(prompt_tokens=estimate_tokens(prompt_text), completion_tokens=estimate_tokens(text), estimated=True)


def _connection_problem(err: BaseException) -> str | None:
    """instructor 會把連線錯誤包進 InstructorRetryException；往下挖 __cause__ 找真正原因。"""
    seen = 0
    cur: BaseException | None = err
    while cur is not None and seen < 6:
        name = type(cur).__name__
        text = str(cur)
        low = text.lower()
        if name in ("APIConnectionError", "ConnectionError", "ConnectError", "Timeout", "APITimeoutError", "ReadTimeout", "ConnectTimeout") \
                or "connection refused" in low or ("connection" in low and "refused" in low):
            return f"連不上模型服務：{text[:160]}"
        if name == "NotFoundError" or ("not found" in low and "model" in low):
            return f"模型不存在：{text[:160]}"
        if name == "AuthenticationError":
            return "金鑰無效或未設定"
        cur = cur.__cause__ or cur.__context__
        seen += 1
    return None


class LiteLLMGateway:
    provider: str
    model: str

    def __init__(self, provider: str = "ollama", model: str | None = None, api_base: str | None = None,
                 extra: dict | None = None, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        import instructor
        import litellm

        litellm.suppress_debug_info = True
        self.provider = provider
        self.model = model or DEFAULT_MODELS.get(provider, model or "")
        if not self.model:
            raise ValueError(f"供應商 {provider} 需要指定 --model")
        if provider == "ollama":
            api_base = api_base or os.getenv("OLLAMA_HOST", "http://localhost:11434")
            if not self.model.startswith("ollama"):
                self.model = "ollama/" + self.model
        self.api_base = api_base
        self.extra = extra or {}
        self.timeout_s = timeout_s
        logging.getLogger("instructor").setLevel(logging.CRITICAL)   # 重試時的英文錯誤不要夾在面板中間
        # MD_JSON：容忍模型把 JSON 包在 ```json 圍欄或前後加話（小模型常見）
        self._client = instructor.from_litellm(litellm.completion, mode=instructor.Mode.MD_JSON)
        self.schema_level = 2 if (provider == "ollama" and "response_format" not in self.extra) else 0  # 2=json_schema 1=json_object 0=無

    def _response_format(self, response_model: Type[BaseModel]) -> dict | None:
        if self.schema_level == 2:
            return {"type": "json_schema", "json_schema": {"name": response_model.__name__.lower(), "schema": response_model.model_json_schema()}}
        if self.schema_level == 1:
            return {"type": "json_object"}
        return None

    def parse(self, messages: list[dict], response_model: Type[BaseModel]) -> ParsedResponse:
        """通用結構化呼叫：schema 驗證 + 把錯誤回饋給模型重試（instructor）。"""
        from instructor.core.exceptions import InstructorRetryException

        kwargs = dict(model=self.model, messages=messages, response_model=response_model, max_retries=MAX_RETRIES,
                      timeout=self.timeout_s, **self.extra)
        if self.api_base:
            kwargs["api_base"] = self.api_base
        rf = self._response_format(response_model)
        if rf:
            kwargs["response_format"] = rf
        t0 = time.perf_counter()
        try:
            try:
                obj, completion = self._client.chat.completions.create_with_completion(**kwargs)
            except Exception as first:  # noqa: BLE001
                if rf and _connection_problem(first) is None and "format" in str(first).lower():
                    self.schema_level -= 1          # 端點不吃這種 response_format：降一級再試一次
                    kwargs.pop("response_format", None)
                    rf = self._response_format(response_model)
                    if rf:
                        kwargs["response_format"] = rf
                    obj, completion = self._client.chat.completions.create_with_completion(**kwargs)
                else:
                    raise
        except InstructorRetryException as err:
            problem = _connection_problem(err)
            attempts = getattr(err, "n_attempts", MAX_RETRIES + 1)
            if problem:
                return ParsedResponse(parsed=None, usage=Usage(), attempts=attempts, latency_s=time.perf_counter() - t0,
                                      error=f"呼叫 {self.model} 失敗：{problem}")
            last = getattr(err, "last_completion", None)
            text = ""
            try:
                text = last.choices[0].message.content or "" if last else ""
            except Exception:  # noqa: BLE001
                text = ""
            usage = _usage_from(last, messages, text) if last else Usage(estimated=True)
            return ParsedResponse(parsed=None, usage=usage, attempts=attempts, latency_s=time.perf_counter() - t0,
                                  error=f"模型連續 {attempts} 次沒有回傳合法的 JSON（{response_model.__name__}）", raw=text[:500])
        except Exception as err:  # noqa: BLE001 - 連線／金鑰／模型不存在等
            problem = _connection_problem(err) or f"{type(err).__name__}: {str(err)[:200]}"
            return ParsedResponse(parsed=None, usage=Usage(), latency_s=time.perf_counter() - t0, attempts=1,
                                  error=f"呼叫 {self.model} 失敗：{problem}")
        text = ""
        try:
            text = completion.choices[0].message.content or ""
        except Exception:  # noqa: BLE001
            pass
        return ParsedResponse(parsed=obj, usage=_usage_from(completion, messages, text), latency_s=time.perf_counter() - t0, raw=text[:500])

    def issue_orders(self, messages: list[dict]) -> ChiefResponse:
        r = self.parse(messages, ChiefOrders)
        error = r.error
        if error and "合法的 JSON" in error:
            error = f"模型連續 {r.attempts} 次沒有回傳合法的命令 JSON，本回合無新命令"
        return ChiefResponse(orders=r.parsed, usage=r.usage, attempts=r.attempts, latency_s=r.latency_s, error=error, raw=r.raw)

    def chat(self, messages: list[dict]) -> ChatResponse:
        """純文字回覆（討論用）。"""
        import litellm
        kwargs = dict(model=self.model, messages=messages, timeout=self.timeout_s, **self.extra)
        if self.api_base:
            kwargs["api_base"] = self.api_base
        t0 = time.perf_counter()
        try:
            completion = litellm.completion(**kwargs)
        except Exception as err:  # noqa: BLE001
            problem = _connection_problem(err) or f"{type(err).__name__}: {str(err)[:200]}"
            return ChatResponse(text="", latency_s=time.perf_counter() - t0, error=f"呼叫 {self.model} 失敗：{problem}")
        text = ""
        try:
            text = completion.choices[0].message.content or ""
        except Exception:  # noqa: BLE001
            pass
        return ChatResponse(text=text, usage=_usage_from(completion, messages, text), latency_s=time.perf_counter() - t0)
