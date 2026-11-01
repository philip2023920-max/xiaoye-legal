"""編制 AI：把任務式命令變成每回合的具體動作。規則見 docs/10-sim-rules.md §3。

LLM 與玩家只下「任務」（seize/hold/flank/withdraw/support/reserve），
這裡負責「排該往哪走、連的任務怎麼拆給排」。純函式，不碰隨機數。
"""
from __future__ import annotations

from .board import MapGrid, Task, Unit
from .grid import distance, neighbors, next_step


def split_company_task(company: Unit, children: list[Unit], task: Task) -> dict[str, Task]:
    """連的任務拆給存活子排。flank：第一個排正面固守，其餘側翼。"""
    alive = [c for c in children if c.state != "destroyed"]
    out: dict[str, Task] = {}
    if task.type == "flank" and len(alive) >= 2:
        out[alive[0].id] = Task(type="hold", target=alive[0].sector)
        for c in alive[1:]:
            out[c.id] = task
        return out
    for c in alive:
        out[c.id] = task
    return out


def flank_approach_sector(grid: MapGrid, target: str, main_sector: str | None) -> str | None:
    """側翼進入點：目標的鄰格中離「我方主力所在格」最遠的那一格（同距取固定順序第一個）。"""
    cands = neighbors(grid, target)
    if not cands:
        return None
    if main_sector is None:
        return cands[0]
    return max(cands, key=lambda s: (distance(s, main_sector), -cands.index(s)))


def decide_move(
    unit: Unit,
    grid: MapGrid,
    friendly: list[Unit],
    own_sectors: list[str],
    unit_by_id: dict[str, Unit],
) -> str | None:
    """回傳這回合要移動到的分區；None 表示原地。

    friendly：同側所有單位（含自己）；own_sectors：目前我方擁有的分區；
    unit_by_id：同側單位索引，給 support 查目標單位位置用。
    """
    if unit.state == "destroyed":
        return None
    if unit.state == "routed":
        # 潰散：往最近的我方分區退一格
        targets = [s for s in own_sectors if s != unit.sector]
        if not targets:
            return None
        goal = min(targets, key=lambda s: (distance(unit.sector, s), s))
        return next_step(grid, unit.sector, goal)
    task = unit.task
    if task is None:
        return None
    t = task.type
    if t in ("seize", "hold", "withdraw", "reserve"):
        return next_step(grid, unit.sector, task.target)
    if t == "support":
        buddy = unit_by_id.get(task.target)
        if buddy is None or buddy.state == "destroyed":
            return None
        if unit.sector in neighbors(grid, buddy.sector):
            return None  # 已在友軍相鄰格，固守
        goal = min(neighbors(grid, buddy.sector), key=lambda s: (distance(unit.sector, s), s))
        return next_step(grid, unit.sector, goal)
    if t == "flank":
        if unit.sector == task.target:
            return None
        leaves = [u for u in friendly if u.state not in ("destroyed", "routed") and u.id != unit.id]
        main = max(leaves, key=lambda u: u.strength).sector if leaves else None
        approach = flank_approach_sector(grid, task.target, main)
        if approach is None:
            return next_step(grid, unit.sector, task.target)
        if unit.sector == approach:
            return task.target  # 從側翼進入目標
        return next_step(grid, unit.sector, approach)
    return None
