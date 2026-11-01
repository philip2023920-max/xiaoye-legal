"""參謀長的輸出合約（LLM → 遊戲）。原則「寬進嚴出」：先把小模型常見的小毛病正規化
（圍欄、同義詞、大小寫、太長），再交給嚴格的驗證器（V1～V6）與引擎。schema 是合約，提示是期待。"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .sim import Order

MAX_ORDERS_PER_TURN = 5
ASSESSMENT_MAX = 200
REASON_MAX = 120

TASK_SYNONYMS = {
    "attack": "seize", "assault": "seize", "capture": "seize", "take": "seize", "advance": "seize", "occupy": "seize", "secure": "seize",
    "defend": "hold", "defense": "hold", "defence": "hold", "stay": "hold", "guard": "hold", "keep": "hold",
    "retreat": "withdraw", "fallback": "withdraw", "fall_back": "withdraw", "pull_back": "withdraw", "regroup": "withdraw", "withdrawal": "withdraw",
    "assist": "support", "cover": "support", "help": "support", "reinforce": "support", "escort": "support",
    "wait": "reserve", "standby": "reserve", "stand_by": "reserve", "rest": "reserve", "idle": "reserve",
    "encircle": "flank", "outflank": "flank", "envelop": "flank", "flanking": "flank",
}
SECTOR_RE = re.compile(r"^[A-Za-z]\d{1,2}$")


class ChiefOrder(BaseModel):
    """一條命令（寬鬆版）。to_order() 轉成引擎用的嚴格 Order。"""
    unit_id: str
    task: Literal["seize", "hold", "flank", "withdraw", "support", "reserve"]
    target: str
    reason: str = ""

    @field_validator("unit_id", "target", mode="before")
    @classmethod
    def _clean_id(cls, v):
        s = str(v or "").strip().strip("\"'`")
        return s.upper() if SECTOR_RE.match(s) else s

    @field_validator("task", mode="before")
    @classmethod
    def _normalize_task(cls, v):
        s = str(v or "").strip().lower().replace(" ", "_").replace("-", "_")
        return TASK_SYNONYMS.get(s, s)

    @field_validator("reason", mode="before")
    @classmethod
    def _trim_reason(cls, v):
        return str(v)[:REASON_MAX] if v else ""

    def to_order(self) -> Order:
        return Order(unit_id=self.unit_id, task=self.task, target=self.target, reason=self.reason)


class ChiefOrders(BaseModel):
    """每個決策節拍參謀長回傳的東西：一句評估＋命令清單（超過 5 條由驗證器 V5 退回）。"""
    assessment: str = Field(default="", description="One-sentence situation assessment for the Commander")
    orders: list[ChiefOrder] = Field(default_factory=list)

    @field_validator("assessment", mode="before")
    @classmethod
    def _trim_assessment(cls, v):
        return str(v)[:ASSESSMENT_MAX] if v else ""

    @field_validator("orders", mode="before")
    @classmethod
    def _none_is_empty(cls, v):
        return [] if v is None else v

    def sim_orders(self) -> list[Order]:
        return [o.to_order() for o in self.orders]


RuleCode = Literal["V1", "V2", "V3", "V4", "V5", "V6", "V7"]


class Rejection(BaseModel):
    """被驗證器退回的命令與原因（規則表：docs/10-sim-rules.md §10）。"""
    order: Order
    rule: RuleCode
    reason: str

    def line(self) -> str:
        return f"{self.rule} {self.order.unit_id} {self.order.task} {self.order.target}：{self.reason}"
