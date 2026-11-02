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
    hint: str = ""            # 施工單 09：離線的一句提示（例如整場沒拿新據點）


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


def objective_hint(start_objectives, end_objectives, winner: str, lang: str = "zh-TW") -> str:
    """離線判定：沒贏，而且整場沒拿下任何「開局不屬於我方」的目標 → 點名分數最高的那個（§11）。"""
    start_us = {o.id for o in start_objectives if o.owner == "us"}
    gained = [o for o in end_objectives if o.owner == "us" and o.id not in start_us]
    if winner == "us" or gained:
        return ""
    missed = sorted((o for o in end_objectives if o.owner != "us"), key=lambda o: (-o.value, o.id))
    if not missed:
        return ""
    top = missed[0]
    who = {"zh-TW": {"enemy": "敵方", "none": "無主"}, "zh-CN": {"enemy": "敌方", "none": "无主"}, "en": {"enemy": "enemy", "none": "unowned"}}
    texts = {
        "zh-TW": f"整場沒有奪取任何新據點：{top.id}（{top.value} 分，{top.sector}）一直是{who['zh-TW'].get(top.owner, top.owner)}。據點分定勝負，下次集中三個排以上攻它。",
        "zh-CN": f"整场没有夺取任何新据点：{top.id}（{top.value} 分，{top.sector}）一直是{who['zh-CN'].get(top.owner, top.owner)}。据点分定胜负，下次集中三个排以上攻它。",
        "en": f"No new objective was taken all battle: {top.id} ({top.value} pts, {top.sector}) stayed {who['en'].get(top.owner, top.owner)}. Points decide the battle; next time concentrate three or more platoons on it.",
    }
    return texts.get(lang, texts["zh-TW"])


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
    if card.hint:
        parts.append(Text(f"提示：{card.hint}", style="yellow"))
    if card.chief_line:
        parts.append(Text(f"參謀長：「{card.chief_line}」", style="cyan"))
    from rich.markup import escape
    return Panel(Group(*parts), title=escape(f"戰報卡 — {card.battle_id}（{card.provider}/{card.model}）"), border_style="green")


def card_dict(card: BattleCard) -> dict:
    return {"battle_id": card.battle_id, "winner": card.winner, "score": [card.score_us, card.score_enemy], "turns": card.turns,
            "end_reason": card.end_reason, "overrides": card.overrides, "override_rate": card.override_rate, "cost_usd": card.cost_usd,
            "provider": card.provider, "model": card.model, "badges": [b.id for b in card.badges],
            "moments": [m.__dict__ for m in card.moments], "chief_line": card.chief_line, "hint": card.hint, "at": __import__("time").time()}


def card_summary_text(card: BattleCard) -> str:
    """給 LLM 看的純文字摘要（英文鍵、短）。"""
    lines = [f"result={card.winner} score={card.score_us}:{card.score_enemy} turns={card.turns} end={card.end_reason} overrides={card.overrides} rate={card.override_rate} cost=${card.cost_usd:.4f}"]
    if card.hint:
        lines.append(f"hint={card.hint}")
    for m in card.moments:
        if m.kind == "override":
            lines.append(f"moment{m.index} t{m.t} unit={m.note} chief={m.ai_text} commander={m.player_text} outcome={m.outcome}")
        else:
            lines.append(f"moment{m.index} t{m.t} turning: {m.note}")
    if card.badges:
        lines.append("badges=" + ",".join(b.id for b in card.badges))
    return "\n".join(lines)


_ABBREV = ("e.g.", "i.e.", "etc.", "vs.", "no.", "mr.", "dr.", "st.")


def first_sentences(text: str, n: int = 2) -> str:
    """只留前 n 句。中文句號／驚嘆號／問號一律算句尾；英文 .!? 只在後面接空白＋大寫或句末時算，
    小數（$0.01）與縮寫（e.g.）不算。保留句與句之間的空白。"""
    text = text.strip().replace("\n", " ")
    ends: list[int] = []
    for i, ch in enumerate(text):
        if ch in "。！？":
            ends.append(i + 1)
        elif ch in ".!?":
            nxt = text[i + 1:i + 2]
            if nxt and not nxt.isspace():
                continue                                        # 小數點、縮寫中間的點
            tail = text[:i + 1].lower()
            if ch == "." and any(tail == a or tail.endswith(" " + a) for a in _ABBREV):   # 整個詞才算縮寫（first. 不是 st.）
                continue
            rest = text[i + 1:].lstrip()
            if not rest or rest[0].isupper() or rest[0].isdigit() or ord(rest[0]) > 127:
                ends.append(i + 1)
        if len(ends) == n:
            return text[:ends[-1]].strip()
    return text


def chief_line(gateway, card: BattleCard, doctrine: str, lang: str, on_usage=None) -> str:
    from .prompts import LANG_NAME
    if not hasattr(gateway, "chat"):
        return ""
    system = ("You are the Chief of Staff. Given the battle summary and your doctrine, say ONE sentence to the Commander "
              f"about what you learned about their preferences, in {LANG_NAME.get(lang, lang)}. No JSON, no list.\n\n## Doctrine\n" + doctrine)
    resp = gateway.chat([{"role": "system", "content": system}, {"role": "user", "content": card_summary_text(card)}])
    if on_usage:
        on_usage(resp.usage, resp.latency_s)
    if resp.error or not resp.text.strip():
        return ""
    return first_sentences(resp.text, 1)
