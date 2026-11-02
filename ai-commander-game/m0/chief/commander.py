"""模擬總司令（施工單 07b）：用固定「風格規則」代替真人下推翻決定，讓五場驗收可以全自動跑。

目的：量「參謀長有沒有學到這個風格」——如果迴圈成立，風格固定的模擬總司令推翻次數應該逐場下降。
規則檔範例：samples/commander_steady.json。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from .board import Board, BoardError, TaskType
from .render import TASK_ZH
from .sim import Order

TASK_INDEX = {t: i + 1 for i, t in enumerate(["seize", "hold", "flank", "withdraw", "support", "reserve"])}


class StyleRule(BaseModel):
    """條件全部成立就推翻成 then。條件省略＝不限制。"""
    if_task: TaskType | None = None
    if_task_not: TaskType | None = None
    if_unit_type: str | None = None
    if_target_in: list[str] | None = None
    if_turn_lte: int | None = None
    if_turn_gte: int | None = None
    then_task: TaskType
    then_target: str
    reason: str = ""

    def matches(self, board: Board, t: int, order: Order) -> bool:
        try:
            u = board.unit(order.unit_id)
        except KeyError:
            return False
        if self.if_task and order.task != self.if_task:
            return False
        if self.if_task_not and order.task == self.if_task_not:
            return False
        if self.if_unit_type and u.type != self.if_unit_type:
            return False
        if self.if_target_in and order.target not in self.if_target_in:
            return False
        if self.if_turn_lte is not None and t > self.if_turn_lte:
            return False
        if self.if_turn_gte is not None and t < self.if_turn_gte:
            return False
        return True


class CommanderStyle(BaseModel):
    name: str = "sim"
    description: str = ""
    rules: list[StyleRule] = Field(default_factory=list)
    max_overrides_per_turn: int = Field(2, ge=0, le=5)
    discuss: bool = True
    adopt: bool = True


@dataclass
class SimCommander:
    style: CommanderStyle
    log: list[dict] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: str | Path) -> "SimCommander":
        p = Path(path)
        if not p.exists():
            raise BoardError(f"找不到模擬總司令風格檔：{p}")
        try:
            return cls(CommanderStyle.model_validate(json.loads(p.read_text(encoding="utf-8-sig"))))
        except (json.JSONDecodeError, ValidationError) as err:
            raise BoardError(f"風格檔 {p} 格式有問題：{str(err)[:200]}") from None

    def turn_inputs(self, board: Board, t: int, accepted: list[Order]) -> list[str]:
        """把本回合要做的推翻翻成互動介面的按鍵序列（編號 → 任務 → 目標），最後 Enter 執行。"""
        keys: list[str] = []
        done = 0
        for i, o in enumerate(accepted, 1):
            if done >= self.style.max_overrides_per_turn:
                break
            for rule in self.style.rules:
                if rule.matches(board, t, o) and not (o.task == rule.then_task and o.target == rule.then_target):
                    keys += [str(i), str(TASK_INDEX[rule.then_task]), rule.then_target]
                    self.log.append({"t": t, "unit": o.unit_id, "from": f"{o.task} {o.target}", "to": f"{rule.then_task} {rule.then_target}", "why": rule.reason})
                    done += 1
                    break
        keys.append("")
        return keys

    def aar_inputs(self) -> list[str]:
        if not self.style.adopt:
            return ["s"]
        if self.style.discuss:
            return ["", "1", "", ""]      # 討論一回合（快速回覆 1）→ 結束討論 → 採納
        return ["a", ""]


def make_input_fn(commander: SimCommander, state: dict):
    """給 run_play 的 input_fn：依目前階段吐出模擬總司令的按鍵。state 由 run_play 每回合更新。"""
    queue: list[str] = []

    def _input(prompt: str = "") -> str:
        nonlocal queue
        if prompt.startswith("總司令（") and state.get("fresh"):
            queue = commander.turn_inputs(state["board"], state["t"], state["accepted"])
            state["fresh"] = False
        elif prompt.startswith("戰後（"):
            queue = commander.aar_inputs()
        if queue:
            return queue.pop(0)
        return ""
    return _input
