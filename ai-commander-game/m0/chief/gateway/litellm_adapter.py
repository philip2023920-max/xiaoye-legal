"""OpenAI 相容路徑：LiteLLM（統一呼叫與 usage）＋ instructor JSON 模式（schema 驗證、把錯誤回饋給模型重試）。

適用 Ollama、OpenAI、DeepSeek、OpenRouter、LM Studio、vLLM…凡是 LiteLLM 認得的都行。
最低公分母策略：schema 進提示 → 回 JSON → 本地驗證 → 不合格重試最多 2 次（共 3 次）。
"""
from __future__ import annotations

import os
import time

from ..meter import Usage
from ..orders import ChiefOrders
from .base import ChiefResponse

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
        cached = getattr(details, "cached_tokens", 0) or 0 if details else 0
        return Usage(prompt_tokens=int(u.prompt_tokens or 0), completion_tokens=int(u.completion_tokens or 0),
                     cache_read_tokens=int(cached))
    # 供應商沒回 usage：字元 ÷ 4 粗估並標記
    chars = sum(len(m.get("content", "")) for m in messages)
    return Usage(prompt_tokens=chars // 4, completion_tokens=len(text) // 4, estimated=True)


class LiteLLMGateway:
    provider: str
    model: str

    def __init__(self, provider: str = "ollama", model: str | None = None, api_base: str | None = None,
                 extra: dict | None = None) -> None:
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
        self._client = instructor.from_litellm(litellm.completion, mode=instructor.Mode.JSON)

    def issue_orders(self, messages: list[dict]) -> ChiefResponse:
        from instructor.core.exceptions import InstructorRetryException

        kwargs = dict(model=self.model, messages=messages, response_model=ChiefOrders, max_retries=MAX_RETRIES, **self.extra)
        if self.api_base:
            kwargs["api_base"] = self.api_base
        t0 = time.perf_counter()
        try:
            orders, completion = self._client.chat.completions.create_with_completion(**kwargs)
        except InstructorRetryException as err:
            attempts = getattr(err, "n_attempts", MAX_RETRIES + 1)
            last = getattr(err, "last_completion", None)
            text = ""
            try:
                text = last.choices[0].message.content or "" if last else ""
            except Exception:  # noqa: BLE001
                text = ""
            usage = _usage_from(last, messages, text) if last else Usage(estimated=True)
            return ChiefResponse(orders=None, usage=usage, attempts=attempts, latency_s=time.perf_counter() - t0,
                                 error=f"模型連續 {attempts} 次沒有回傳合法的命令 JSON，本回合無新命令", raw=text[:500])
        except Exception as err:  # noqa: BLE001 - 連線／金鑰／模型不存在等
            return ChiefResponse(orders=None, latency_s=time.perf_counter() - t0, attempts=1,
                                 error=f"呼叫 {self.model} 失敗：{type(err).__name__}: {str(err)[:200]}")
        text = ""
        try:
            text = completion.choices[0].message.content or ""
        except Exception:  # noqa: BLE001
            pass
        return ChiefResponse(orders=orders, usage=_usage_from(completion, messages, text),
                             latency_s=time.perf_counter() - t0, raw=text[:500])
