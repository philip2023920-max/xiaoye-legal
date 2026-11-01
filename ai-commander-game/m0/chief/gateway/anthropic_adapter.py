"""Anthropic 原生路徑（施工單 04）：官方 SDK `messages.parse()` 結構化輸出 + prompt caching。

為什麼不走 LiteLLM：strict schema、快取、串流這些新功能官方 SDK 最快跟上（ADR-0012）。
用法：ANTHROPIC_API_KEY 放在 .env（金鑰捕捉腳本寫入），不經聊天、不進 log。
"""
from __future__ import annotations

import time

from ..meter import Usage
from ..orders import ChiefOrders
from .base import ChiefResponse

DEFAULT_MODEL = "claude-haiku-5-5"   # 節拍用（D3）；AAR 用 claude-sonnet-5-5
MAX_TOKENS = 2048


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

    def __init__(self, model: str | None = None, client=None, max_tokens: int = MAX_TOKENS) -> None:
        self.model = model or DEFAULT_MODEL
        self.max_tokens = max_tokens
        if client is None:
            import anthropic  # 延後匯入：沒有金鑰的人跑 ollama 不該被擋
            client = anthropic.Anthropic()   # 金鑰由環境變數 ANTHROPIC_API_KEY 提供
        self.client = client

    def issue_orders(self, messages: list[dict]) -> ChiefResponse:
        system_blocks, convo = _split(messages)
        t0 = time.perf_counter()
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_blocks,          # 系統提示＋準則在前並快取；每回合只換 user 訊息
                messages=convo,
                output_format=ChiefOrders,     # 結構化輸出：SDK 保證回來就是合法 ChiefOrders
            )
        except Exception as err:  # noqa: BLE001 - 金鑰錯、額度不足、網路、429、5xx 都走這裡
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
            return ChiefResponse(orders=None, latency_s=time.perf_counter() - t0,
                                 error=f"呼叫 {self.model} 失敗：{name}{'（' + hint + '）' if hint else ''}: {detail[:200]}")
        latency = time.perf_counter() - t0
        stop = getattr(response, "stop_reason", None)
        usage = usage_from_anthropic(getattr(response, "usage", None))
        if stop == "refusal":
            return ChiefResponse(orders=None, usage=usage, latency_s=latency,
                                 error="模型因安全分類拒絕了這個請求（stop_reason=refusal），本回合無新命令")
        if stop == "max_tokens":
            return ChiefResponse(orders=None, usage=usage, latency_s=latency,
                                 error=f"回覆被 max_tokens={self.max_tokens} 截斷，本回合無新命令")
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            return ChiefResponse(orders=None, usage=usage, latency_s=latency, error="SDK 沒有回傳可解析的結構化輸出")
        raw = ""
        try:
            raw = next(b.text for b in response.content if getattr(b, "type", "") == "text")
        except Exception:  # noqa: BLE001
            pass
        return ChiefResponse(orders=parsed, usage=usage, latency_s=latency, raw=raw[:500])
