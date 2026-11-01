"""戰報卡（施工單 06）：一張卡、三幕。程式從推翻紀錄與事件流產生，不呼叫 LLM；只有「參謀長一句話」用 LLM。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .badges import Badge
from .board import Event
from .override import OverrideRecord
from .render import TASK_ZH

CIRCLED = "①②③④⑤"
TURNING_KINDS = ("seized", "routed", "destroyed")


@dataclass
class Moment:
    index: int
    t: int
    kind: str                 # override / turning
    ai_text: str
    player_text: str
    outcome: str              # 👍 👎 ➖ 或空
    note: str = ""


@dataclass
class BattleCard:
    battle_id: str
    winner: str
    score_us: int
    score_enemy: int
    turns: int
    end_reason: str
    overrides: int
    override_rate: str
    cost_usd: float
    provider: str
    model: str
    badges: list[Badge] = field(default_factory=list)
    moments: list[Moment] = field(default_factory=list)
    chief_line: str = ""


def _order_text(o: dict | None) -> str:
    if not o:
        return "（無）"
    task = o.get("task") or o.get("type", "")
    return f"{TASK_ZH.get(task, task)} {o.get('target', '')}"


def pick_moments(records: list[OverrideRecord], events: list[Event], n: int = 3) -> list[Moment]:
    """優先挑推翻點（真實分歧），不足再補轉折點（據點易手、潰散、殲滅）。"""
    out: list[Moment] = []
    for r in records[:n]:
        out.append(Moment(index=len(out) + 1, t=r.turn, kind="override", ai_text=_order_text(r.ai_order),
                          player_text=_order_text(r.player_order), outcome=r.outcome or "未判定",
                          note=f"{r.unit_id}"))
    if len(out) < n:
        for e in events:
            if e.kind in TURNING_KINDS and len(out) < n:
                out.append(Moment(index=len(out) + 1, t=e.t, kind="turning", ai_text="—", player_text="—",
                                  outcome="", note=e.text))
    return out


def build_card_from(result, battle, records: list[OverrideRecord], badges: list[Badge], gateway) -> BattleCard:
    b = result.battle
    return BattleCard(battle_id=b.battle_id, winner=b.winner, score_us=b.score_us, score_enemy=b.score_enemy, turns=b.turns_played,
                      end_reason=b.end_reason, overrides=len(records), override_rate=result.override_rate if result.chief_orders_total else f"{len(records)}/0",
                      cost_usd=result.meter.cost_usd, provider=gateway.provider, model=gateway.model, badges=badges,
                      moments=pick_moments(records, battle.board.events))


def render_card(card: BattleCard) -> Panel:
    w = {"us": "勝", "enemy": "敗", "draw": "平"}[card.winner]
    stars = {"us": "★★★", "draw": "★★☆", "enemy": "★☆☆"}[card.winner]
    head = Text(f"{w} {stars}   {card.turns} 回合   推翻 {card.overrides} 次（{card.override_rate}）   花費 ${card.cost_usd:.4f}   據點 {card.score_us}:{card.score_enemy}", style="bold")
    badge_line = Text("🎖️ " + "、".join(f"{b.name}（{b.why}）" for b in card.badges) if card.badges else "（本場沒有徽章）", style="yellow" if card.badges else "dim")
    t = Table(box=box.SIMPLE, title="關鍵三幕")
    t.add_column("幕"); t.add_column("時間"); t.add_column("參謀長"); t.add_column("你"); t.add_column("結果")
    for m in card.moments:
        if m.kind == "override":
            t.add_row(CIRCLED[m.index - 1], f"t{m.t}", Text(f"{m.note}：{m.ai_text}"), Text(m.player_text), Text(m.outcome))
        else:
            t.add_row(CIRCLED[m.index - 1], f"t{m.t}", Text(m.note), Text("—"), Text("轉折"))
    if not card.moments:
        t.add_row("—", "—", Text("這場沒有推翻，也沒有據點易手或潰散", style="dim"), "", "")
    parts = [head, badge_line, t]
    if card.chief_line:
        parts.append(Text(f"參謀長：「{card.chief_line}」", style="cyan"))
    return Panel(Group(*parts), title=f"戰報卡 — {card.battle_id}（{card.provider}/{card.model}）", border_style="green")


def card_summary_text(card: BattleCard) -> str:
    """給 LLM 看的純文字摘要（英文鍵、短）。"""
    lines = [f"result={card.winner} score={card.score_us}:{card.score_enemy} turns={card.turns} end={card.end_reason} overrides={card.overrides} rate={card.override_rate} cost=${card.cost_usd:.4f}"]
    for m in card.moments:
        if m.kind == "override":
            lines.append(f"moment{m.index} t{m.t} unit={m.note} chief={m.ai_text} commander={m.player_text} outcome={m.outcome}")
        else:
            lines.append(f"moment{m.index} t{m.t} turning: {m.note}")
    if card.badges:
        lines.append("badges=" + ",".join(b.id for b in card.badges))
    return "\n".join(lines)


def first_sentences(text: str, n: int = 2) -> str:
    """只留前 n 句（中英文句號、驚嘆號、問號）。"""
    text = text.strip().replace("\n", " ")
    parts = re.split(r"(?<=[。！？.!?])\s*", text)
    parts = [p for p in parts if p]
    return "".join(parts[:n]) if len(parts) > n else text


def chief_line(gateway, card: BattleCard, doctrine: str, lang: str) -> str:
    from .prompts import LANG_NAME
    if not hasattr(gateway, "chat"):
        return ""
    system = ("You are the Chief of Staff. Given the battle summary and your doctrine, say ONE sentence to the Commander "
              f"about what you learned about their preferences, in {LANG_NAME.get(lang, lang)}. No JSON, no list.\n\n## Doctrine\n" + doctrine)
    resp = gateway.chat([{"role": "system", "content": system}, {"role": "user", "content": card_summary_text(card)}])
    if resp.error or not resp.text.strip():
        return ""
    return first_sentences(resp.text, 1)
