"""參謀長的輸出合約（LLM → 遊戲）。schema 是合約，提示是期待；合約優先。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .sim import Order

MAX_ORDERS_PER_TURN = 5


class ChiefOrders(BaseModel):
    """每個決策節拍參謀長回傳的東西：一句評估＋最多 5 條任務式命令。"""
    assessment: str = Field(max_length=200, description="One-sentence situation assessment for the Commander")
    orders: list[Order] = Field(default_factory=list, max_length=MAX_ORDERS_PER_TURN)


RuleCode = Literal["V1", "V2", "V3", "V4", "V5", "V6"]


class Rejection(BaseModel):
    """被驗證器退回的命令與原因（規則表：docs/10-sim-rules.md §10）。"""
    order: Order
    rule: RuleCode
    reason: str

    def line(self) -> str:
        return f"{self.rule} {self.order.unit_id} {self.order.task} {self.order.target}：{self.reason}"
