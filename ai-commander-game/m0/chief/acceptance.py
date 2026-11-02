"""M0 總驗收（施工單 07）：同一人連打 N 場，看推翻率曲線；另提供 stats 從既有戰鬥資料夾畫曲線。"""
from __future__ import annotations

import json
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table


def battle_stats(battles_root: str | Path = "battles") -> list[dict]:
    rows = []
    for d in sorted(Path(battles_root).glob("*/")):
        aar = d / "aar.json"
        if not aar.exists():
            continue
        try:
            card = json.loads(aar.read_text(encoding="utf-8")).get("card", {})
        except json.JSONDecodeError:
            continue
        if not card:
            continue
        rows.append({"dir": d.name, "winner": card.get("winner"), "score": card.get("score"), "turns": card.get("turns"),
                     "override_rate": card.get("override_rate"), "cost": card.get("cost_usd", 0.0), "model": card.get("model"),
                     "at": card.get("at") or aar.stat().st_mtime})
    rows.sort(key=lambda r: r["at"])
    return rows


def rate_value(rate: str | None) -> float | None:
    try:
        a, b = str(rate).split("/")
        return round(100.0 * int(a) / int(b), 1) if int(b) else None
    except (ValueError, AttributeError):
        return None


def render_curve(rows: list[dict], console: Console, title: str = "推翻率曲線") -> None:
    t = Table(box=box.SIMPLE, title=title)
    t.add_column("#"); t.add_column("戰鬥"); t.add_column("結果"); t.add_column("據點"); t.add_column("推翻率"); t.add_column("曲線"); t.add_column("費用"); t.add_column("模型")
    for i, r in enumerate(rows, 1):
        v = rate_value(r["override_rate"])
        bar = "█" * int(round((v or 0) / 5)) if v is not None else "—"
        w = {"us": "勝", "enemy": "敗", "draw": "平"}.get(r["winner"], "?")
        t.add_row(str(i), r["dir"], w, f"{r['score'][0]}:{r['score'][1]}" if r.get("score") else "—", f"{v}%" if v is not None else "—", bar, f"${r['cost']:.4f}", str(r["model"]))
    console.print(t)
    vals = [rate_value(r["override_rate"]) for r in rows]
    vals = [v for v in vals if v is not None]
    if len(vals) >= 2:
        trend = "下降 ✅" if vals[-1] < vals[0] else ("持平 ➖" if vals[-1] == vals[0] else "上升 ⚠️")
        console.print(f"首場 {vals[0]}% → 末場 {vals[-1]}%：{trend}（M0 驗收目標：下降）")
