"""指令驗證器：參謀長的命令進遊戲前最後一道門。規則 V1～V6 見 docs/10-sim-rules.md §10。"""
from __future__ import annotations

from .board import Board
from .orders import MAX_ORDERS_PER_TURN, Rejection
from .sim import Order


def validate_orders(board: Board, orders: list[Order]) -> tuple[list[Order], list[Rejection]]:
    """回傳（放行的命令, 退回的命令）。順序保留；同一單位第二條起退回。"""
    by_id = {u.id: u for u in board.orbat}
    sectors = board.map.sectors
    accepted: list[Order] = []
    rejected: list[Rejection] = []
    seen: set[str] = set()

    for i, o in enumerate(orders):
        if i >= MAX_ORDERS_PER_TURN:
            rejected.append(Rejection(order=o, rule="V5", reason=f"本回合命令超過 {MAX_ORDERS_PER_TURN} 條"))
            continue
        u = by_id.get(o.unit_id)
        if u is None or u.state == "destroyed":
            rejected.append(Rejection(order=o, rule="V1", reason=f"單位 {o.unit_id} 不存在或已殲滅"))
            continue
        if u.controlled_by == "player":
            rejected.append(Rejection(order=o, rule="V2", reason=f"單位 {o.unit_id} 由總司令直轄，參謀長不得下令"))
            continue
        if o.task == "support":
            buddy = by_id.get(o.target)
            if buddy is None or buddy.state == "destroyed" or o.target == o.unit_id:
                rejected.append(Rejection(order=o, rule="V3", reason=f"任務 support 的目標 {o.target} 不合法（必須是存活的其他友軍單位）"))
                continue
        elif o.target not in sectors:
            rejected.append(Rejection(order=o, rule="V3", reason=f"任務 {o.task} 的目標 {o.target} 不合法（必須是分區 id）"))
            continue
        if o.unit_id in seen:
            rejected.append(Rejection(order=o, rule="V4", reason=f"單位 {o.unit_id} 本回合已有命令"))
            continue
        if u.state == "routed" and o.task != "withdraw":
            rejected.append(Rejection(order=o, rule="V6", reason=f"單位 {o.unit_id} 潰散中，只能撤退"))
            continue
        seen.add(o.unit_id)
        accepted.append(o)
    return accepted, rejected
