"""閘道介面（合約）：messages 進、ChiefOrders＋usage 出。供應商細節全部藏在 adapter。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from ..meter import Usage
from ..orders import ChiefOrders


@dataclass
class ChiefResponse:
    orders: ChiefOrders | None
    usage: Usage = field(default_factory=Usage)
    attempts: int = 1
    latency_s: float = 0.0
    error: str | None = None   # 重試用盡或連線失敗時的人話說明
    raw: str = ""


class Gateway(Protocol):
    provider: str
    model: str

    def issue_orders(self, messages: list[dict]) -> ChiefResponse: ...


class FakeGateway:
    """測試與離線用：照順序回傳預先寫好的 ChiefOrders；用完就回空命令。"""
    provider = "fake"

    def __init__(self, scripted: list[ChiefOrders] | None = None, model: str = "fake/none",
                 usage: Usage | None = None, latency_s: float = 0.01) -> None:
        self.model = model
        self.scripted = list(scripted or [])
        self.usage = usage or Usage(prompt_tokens=100, completion_tokens=20)
        self.latency_s = latency_s
        self.calls: list[list[dict]] = []

    def issue_orders(self, messages: list[dict]) -> ChiefResponse:
        self.calls.append(messages)
        orders = self.scripted.pop(0) if self.scripted else ChiefOrders(assessment="(fake) no orders", orders=[])
        return ChiefResponse(orders=orders, usage=Usage(**self.usage.__dict__), latency_s=self.latency_s)


def make_gateway(provider: str, model: str | None = None, **kwargs) -> "Gateway":
    """依供應商名稱建立閘道。provider：ollama / openai / deepseek / openrouter / anthropic（04）/ fake。"""
    if provider == "fake":
        return FakeGateway(model=model or "fake/none")
    if provider == "anthropic":
        from .anthropic_adapter import AnthropicGateway
        return AnthropicGateway(model=model, effort=kwargs.get("effort"))
    from .litellm_adapter import LiteLLMGateway
    kwargs.pop("effort", None)
    return LiteLLMGateway(provider=provider, model=model, **kwargs)


def timed() -> float:
    return time.perf_counter()
