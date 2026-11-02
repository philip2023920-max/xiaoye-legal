"""Anthropic 原生路徑（施工單 04）：官方 SDK `messages.parse()` 結構化輸出 + prompt caching。

為什麼不走 LiteLLM：strict schema、快取、串流這些新功能官方 SDK 最快跟上（ADR-0012）。
用法：ANTHROPIC_API_KEY 放在 .env（金鑰捕捉腳本寫入），不經聊天、不進 log。
"""
from __future__ import annotations

import time
from typing import Type

from pydantic import BaseModel

from ..meter import Usage
from ..orders import ChiefOrders
from .base import ChatResponse, ChiefResponse, ParsedResponse

DEFAULT_MODEL = "claude-haiku-5-5"   # 節拍用（D3）；AAR 用 claude-sonnet-5-5
MAX_TOKENS = 4096   # 施工單 09：2048 在壞準則下 7 回合被截 3 次
BREVITY_NOTE = ("Your previous reply was cut off by the output length limit. Reply again with the same JSON schema but much shorter: "
                "assessment in one short sentence, and set every \"reason\" to \"\".")


def _add_usage(a: Usage, b: Usage) -> Usage:
    return Usage(prompt_tokens=a.prompt_tokens + b.prompt_tokens, completion_tokens=a.completion_tokens + b.completion_tokens,
                 cache_read_tokens=a.cache_read_tokens + b.cache_read_tokens, cache_write_tokens=a.cache_write_tokens + b.cache_write_tokens,
                 estimated=a.estimated or b.estimated)


def _split(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """把 OpenAI 風格 messages 拆成 Anthropic 的 system（含快取標記）與 messages。"""
    system_blocks = [{"type": "text", "text": m["content"], "cache_control": {"type": "ephemeral"}}
                     for m in messages if m["role"] == "system"]
    rest = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    return system_blocks, rest


def usage_from_anthropic(u) -> Usage:
    """Anthropic usage → 共用 Usage。cache_read 另計價（Haiku 5.5 讀快取約 0.1 倍）。"""
    return Usage(
        prompt_tokens=int(getattr(u, "input_tokens", 0) or 0),
        completion_tokens=int(getattr(u, "output_tokens", 0) or 0),
        cache_read_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(getattr(u, "cache_creation_input_tokens", 0) or 0),
    )


class AnthropicGateway:
    provider = "anthropic"

    def __init__(self, model: str | None = None, client=None, max_tokens: int = MAX_TOKENS, effort: str | None = None) -> None:
        self.model = model or DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.effort = effort   # low/medium/high：Haiku 5.5 預設 medium；下命令這種工作 low 通常夠（⚠️ 真機驗證）
        if client is None:
            import anthropic  # 延後匯入：沒有金鑰的人跑 ollama 不該被擋
            client = anthropic.Anthropic()   # 金鑰由環境變數 ANTHROPIC_API_KEY 提供
        self.client = client

    def _error(self, err: Exception) -> str:
        import anthropic
        name = type(err).__name__
        hint = {
            "AuthenticationError": "金鑰無效或未設定（檢查 .env 的 ANTHROPIC_API_KEY）",
            "PermissionDeniedError": "金鑰沒有權限或帳戶需要儲值",
            "RateLimitError": "被限流，稍後重試",
            "APIConnectionError": "連不上 Anthropic API（網路或代理）",
            "NotFoundError": f"模型 {self.model} 不存在",
            "BadRequestError": "請求格式被拒（可能是模型不支援某參數）",
        }.get(name, "")
        detail = str(err)
        if isinstance(err, anthropic.APIStatusError):
            detail = f"HTTP {err.status_code}: {detail}"
        return f"呼叫 {self.model} 失敗：{name}{'（' + hint + '）' if hint else ''}: {detail[:200]}"

    def parse(self, messages: list[dict], response_model: Type[BaseModel]) -> ParsedResponse:
        system_blocks, convo = _split(messages)
        t0 = time.perf_counter()
        try:
            kwargs = dict(model=self.model, max_tokens=self.max_tokens,
                          system=system_blocks,          # 系統提示＋準則在前並快取；每回合只換 user 訊息
                          messages=convo,
                          output_format=response_model)  # 結構化輸出：SDK 保證回來就是合法的 response_model
            if self.effort:
                kwargs["output_config"] = {"effort": self.effort}
            response = self.client.messages.parse(**kwargs)
        except Exception as err:  # noqa: BLE001 - 金鑰錯、額度不足、網路、429、5xx 都走這裡
            return ParsedResponse(parsed=None, latency_s=time.perf_counter() - t0, error=self._error(err))
        latency = time.perf_counter() - t0
        stop = getattr(response, "stop_reason", None)
        usage = usage_from_anthropic(getattr(response, "usage", None))
        if stop == "refusal":
            return ParsedResponse(parsed=None, usage=usage, latency_s=latency, error="模型因安全分類拒絕了這個請求（stop_reason=refusal）", stop_reason=stop)
        if stop == "max_tokens":
            return ParsedResponse(parsed=None, usage=usage, latency_s=latency, error=f"回覆被 max_tokens={self.max_tokens} 截斷", stop_reason=stop)
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            return ParsedResponse(parsed=None, usage=usage, latency_s=latency, error="SDK 沒有回傳可解析的結構化輸出")
        raw = ""
        try:
            raw = next(b.text for b in response.content if getattr(b, "type", "") == "text")
        except Exception:  # noqa: BLE001
            pass
        return ParsedResponse(parsed=parsed, usage=usage, latency_s=latency, raw=raw[:500], stop_reason=stop)

    def issue_orders(self, messages: list[dict]) -> ChiefResponse:
        r = self.parse(messages, ChiefOrders)
        attempts = 1
        if r.stop_reason == "max_tokens":   # 截斷：把精簡要求併進同一則 user 訊息再試一次（兩次都計費）
            retry = [dict(m) for m in messages]
            retry[-1]["content"] = retry[-1]["content"] + "\n\n" + BREVITY_NOTE
            r2 = self.parse(retry, ChiefOrders)
            r2.usage = _add_usage(r.usage, r2.usage)
            r2.latency_s += r.latency_s
            if r2.stop_reason == "max_tokens":
                r2.error += "（已要求精簡重試 1 次仍截斷）"
            r, attempts = r2, 2
        error = r.error
        if error and r.stop_reason in ("refusal", "max_tokens"):
            error += "，本回合無新命令"
        return ChiefResponse(orders=r.parsed, usage=r.usage, attempts=attempts, latency_s=r.latency_s, error=error, raw=r.raw)

    def chat(self, messages: list[dict]) -> ChatResponse:
        system_blocks, convo = _split(messages)
        t0 = time.perf_counter()
        try:
            kwargs = dict(model=self.model, max_tokens=self.max_tokens, system=system_blocks, messages=convo)
            if self.effort:
                kwargs["output_config"] = {"effort": self.effort}
            response = self.client.messages.create(**kwargs)
        except Exception as err:  # noqa: BLE001
            return ChatResponse(text="", latency_s=time.perf_counter() - t0, error=self._error(err))
        text = ""
        try:
            text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        except Exception:  # noqa: BLE001
            pass
        return ChatResponse(text=text, usage=usage_from_anthropic(getattr(response, "usage", None)), latency_s=time.perf_counter() - t0)
