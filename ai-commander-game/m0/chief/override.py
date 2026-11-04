"""總司令推翻與接管（施工單 05）：推翻紀錄、後果判定（docs/10-sim-rules.md §9）、玩家命令檢查。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .board import Board
from .sim import Order

OUTCOME_GOOD, OUTCOME_BAD, OUTCOME_NEUTRAL = "👍", "👎", "➖"
TASK_CHOICES = ["seize", "hold", "flank", "withdraw", "support", "reserve"]


@dataclass
class OverrideRecord:
    turn: int
    unit_id: str
    ai_order: Optional[dict]        # 被推翻的參謀長命令（接管沒命令的單位時為 None）
    player_order: dict
    snapshot_ref: str               # 推翻當下的戰情板快照路徑（上一回合的 tN.json）
    strength_at: float
    outcome: Optional[str] = None   # 👍 / 👎 / ➖，t+1 回合結束時填
    judged_turn: Optional[int] = None
    t_at: Optional[float] = None    # 推翻當下的遊戲秒（秒制板；服務用它決定判定時點，§9）


class OverrideLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.records: list[OverrideRecord] = []

    def add(self, rec: OverrideRecord) -> None:
        self.records.append(rec)
        self._write()

    def pending(self, turn: int) -> list[OverrideRecord]:
        return [r for r in self.records if r.outcome is None and r.turn + 1 == turn]

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            for r in self.records:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    def set_outcome(self, rec: OverrideRecord, outcome: str, turn: int) -> None:
        rec.outcome, rec.judged_turn = outcome, turn
        self._write()


def target_sector(board: Board, order: dict) -> Optional[str]:
    """命令的目標分區；support 看友軍所在格。"""
    tgt = order.get("target", "")
    if tgt in board.map.sectors:
        return tgt
    try:
        return board.unit(tgt).sector
    except KeyError:
        return None


def judge_outcome(board_after: Board, rec: OverrideRecord, owner_before: Optional[str]) -> str:
    """§9：👍 戰力下降 < 0.05 且目標分區變我方或維持我方；👎 潰散／殲滅或目標分區變敵方；其他 ➖。"""
    try:
        u = board_after.unit(rec.unit_id)
    except KeyError:
        return OUTCOME_NEUTRAL
    sector = target_sector(board_after, rec.player_order)
    owner_after = board_after.map.sectors[sector].owner if sector else None
    if u.state in ("routed", "destroyed") or (owner_after == "enemy" and owner_before != "enemy"):
        return OUTCOME_BAD
    if round(rec.strength_at - u.strength, 4) < 0.05 and owner_after == "us":
        return OUTCOME_GOOD
    return OUTCOME_NEUTRAL


def subtree_ids(board: Board, unit_id: str) -> list[str]:
    """unit 本身＋所有下級 id（接管／放手連時一起處理）。"""
    out, stack = [unit_id], [unit_id]
    while stack:
        x = stack.pop()
        for u in board.orbat:
            if u.parent == x and u.id not in out:
                out.append(u.id)
                stack.append(u.id)
    return out


def player_order_problem(board: Board, order: Order) -> Optional[str]:
    """玩家命令的檢查（不套 V2，因為那是玩家自己的單位）。"""
    try:
        u = board.unit(order.unit_id)
    except KeyError:
        return f"單位 {order.unit_id} 不存在"
    if u.state == "destroyed":
        return f"單位 {order.unit_id} 已殲滅"
    if u.state == "routed" and order.task != "withdraw":
        return f"單位 {order.unit_id} 潰散中，只能撤退"
    if order.task == "support":
        try:
            b = board.unit(order.target)
        except KeyError:
            return f"support 的目標 {order.target} 必須是友軍單位 id"
        if b.state == "destroyed" or order.target == order.unit_id:
            return f"support 的目標 {order.target} 不合法"
    elif order.target not in board.map.sectors:
        return f"目標 {order.target} 不是分區 id（例如 C3）"
    return None
