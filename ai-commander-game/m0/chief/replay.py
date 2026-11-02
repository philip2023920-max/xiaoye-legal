"""回放一場戰鬥（施工單 09）：從快照 t*.json 與 llm_log.jsonl 整理成每回合幾行的文字。不呼叫 LLM。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .board import BoardError, load_board

KEY_KINDS = ("order", "seized", "routed", "destroyed", "weather", "override")
WX = {"clear": "晴", "rain": "雨", "snow": "雪", "fog": "霧"}
TOD = {"day": "日", "night": "夜"}


def _assessments(d: Path) -> dict[int, str]:
    """llm_log.jsonl 每回合的評估（raw 只留 500 字，所以用正則抓 assessment 就好）。"""
    out: dict[int, str] = {}
    p = d / "llm_log.jsonl"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        raw = row.get("raw") or ""
        m = re.search(r'"assessment"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
        text = m.group(1) if m else (row.get("error") or "")
        out[int(row.get("t", 0))] = text.replace("\\n", " ")[:90]
    return out


def replay_lines(battle_dir: str | Path, show_all: bool = False) -> list[str]:
    d = Path(battle_dir)
    snaps = sorted(d.glob("t*.json"), key=lambda p: int(p.stem[1:]))
    if not snaps:
        raise BoardError(f"{d} 裡沒有快照 t*.json")
    last = load_board(snaps[-1])
    boards = {int(p.stem[1:]): load_board(p) for p in snaps}
    assess = _assessments(d)
    kinds = KEY_KINDS + (("contact", "info") if show_all else ())
    seconds = last.time_unit == "second"            # M1（Godot）快照：t 是秒、每 30 秒一份 t<n>.json
    turns = max(boards) if seconds else last.t
    unit_note = "（每回合 30 秒）" if seconds else ""
    lines = [f"{last.battle_id}｜世代 {last.era}｜共 {turns} 回合{unit_note}｜據點 我 {sum(o.value for o in last.objectives if o.owner == 'us')} : 敵 {sum(o.value for o in last.objectives if o.owner == 'enemy')}"]

    def turn_of(e) -> int:
        return min(turns, e.t // 30 + 1) if seconds else e.t   # 秒 → 回合：第 n 回合＝第 30(n−1)～30n−1 秒；結束那秒併入最後一回合
    for t in range(1, turns + 1):
        b = boards.get(t, last)
        evs = [e for e in last.events if turn_of(e) == t and e.kind in kinds]
        orders = [e.text.replace("參謀長令 ", "") for e in evs if e.kind == "order"]
        others = [f"[{e.kind}] {e.text}" for e in evs if e.kind != "order"]
        strength_us = round(sum(u.strength for u in b.orbat if u.echelon == "platoon" and u.state != "destroyed"), 2)
        head = f"t{t:<2} {WX.get(b.weather, b.weather)}/{TOD.get(b.time_of_day, b.time_of_day)} 我方戰力 {strength_us}"
        if t in assess:
            head += f"｜評估：{assess[t]}"
        lines.append(head)
        lines.append("    令：" + ("；".join(orders) if orders else "（無）"))
        if others:
            lines.append("    事件：" + "；".join(others))
    return lines
