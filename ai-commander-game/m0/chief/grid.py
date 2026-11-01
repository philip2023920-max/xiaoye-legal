"""分區格工具：id ↔ 座標、鄰格、最短路徑下一步。規則見 docs/10-sim-rules.md §2。"""
from __future__ import annotations

from collections import deque

from .board import COL_LETTERS, MapGrid


def to_xy(sector_id: str) -> tuple[int, int]:
    """'B2' -> (1, 2)：x 是欄（A=0），y 是列（從 1 起）。"""
    return COL_LETTERS.index(sector_id[0]), int(sector_id[1:])


def to_id(x: int, y: int) -> str:
    return f"{COL_LETTERS[x]}{y}"


def neighbors(grid: MapGrid, sector_id: str) -> list[str]:
    """上下左右四鄰，固定順序（上、左、右、下）讓結果可重現。"""
    x, y = to_xy(sector_id)
    out = []
    for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < grid.cols and 1 <= ny <= grid.rows:
            out.append(to_id(nx, ny))
    return out


def distance(a: str, b: str) -> int:
    ax, ay = to_xy(a)
    bx, by = to_xy(b)
    return abs(ax - bx) + abs(ay - by)


def next_step(grid: MapGrid, start: str, goal: str, avoid: set[str] | None = None) -> str | None:
    """BFS 最短路徑的第一步；已到達或無路回 None。所有地形可通行；avoid 內的格子不當中繼（goal 除外）。"""
    if start == goal:
        return None
    avoid = avoid or set()
    prev: dict[str, str | None] = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for n in neighbors(grid, cur):
            if n not in prev and (n == goal or n not in avoid):
                prev[n] = cur
                q.append(n)
    if goal not in prev:
        return None
    node = goal
    while prev[node] != start:
        node = prev[node]  # type: ignore[assignment]
    return node
