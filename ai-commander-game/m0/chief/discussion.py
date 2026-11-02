"""戰後討論（施工單 06）：最多三回合，每回合給 3 個快速回覆，也可打字；參謀長回覆限兩句。"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .prompts import LANG_NAME
from .report import BattleCard, card_summary_text, first_sentences

MAX_ROUNDS = 3


def quick_replies(card: BattleCard, lang: str, rnd: int = 1) -> list[str]:
    """每回合不同：第 1 回合問原因，第 2 回合談下次，第 3 回合定規則。"""
    overrides = [m for m in card.moments if m.kind == "override"]
    first = overrides[0] if overrides else None
    tag = f"第{'①②③'[first.index - 1]}幕" if first else "這場"
    sets = {
        "zh-TW": [[f"為什麼{tag}你那樣做？", "你覺得這場輸贏的關鍵在哪？", "我的推翻有哪一次是錯的？"],
                  ["下次這種情況先問我再動", "下次遇到同樣敵情你會怎麼做？", "哪個單位你覺得我用錯了？"],
                  ["把這個做法寫進準則", "我錯了，照你的做法就好", "這場先不改準則"]],
        "zh-CN": [[f"为什么{tag}你那样做？", "你觉得这场输赢的关键在哪？", "我的推翻有哪一次是错的？"],
                  ["下次这种情况先问我再动", "下次遇到同样敌情你会怎么做？", "哪个单位你觉得我用错了？"],
                  ["把这个做法写进准则", "我错了，照你的做法就好", "这场先不改准则"]],
        "en": [[f"Why did you act that way in {('moment ' + str(first.index)) if first else 'this battle'}?", "What decided this battle?", "Which of my overrides was wrong?"],
               ["Next time, ask me before moving in that situation", "What would you do against the same enemy next time?", "Which unit did I misuse?"],
               ["Write this into the doctrine", "I was wrong, your way was fine", "Leave the doctrine alone this time"]],
    }
    return sets.get(lang, sets["zh-TW"])[min(rnd, 3) - 1]


def run_discussion(gateway, card: BattleCard, doctrine: str, lang: str, console: Console, input_fn=input,
                   max_rounds: int = MAX_ROUNDS, on_usage=None) -> list[dict]:
    """回傳對話紀錄 [{role, content}]。輸入空白提前結束；EOF／Ctrl+C 視同結束。"""
    system = ("You are the Chief of Staff debriefing with the Commander after a battle. Answer in at most TWO sentences, "
              f"in {LANG_NAME.get(lang, lang)}, concrete and without flattery. Battle summary:\n" + card_summary_text(card)
              + "\n\n## Your doctrine\n" + doctrine)
    history: list[dict] = []
    rnd = 1
    while rnd <= max_rounds:
        options = quick_replies(card, lang, rnd)
        console.print(Panel(Text("\n".join(f"{i+1}. {q}" for i, q in enumerate(options)) + "\n（輸入數字、或直接打字；Enter 結束討論）"),
                            title=f"討論 第 {rnd}/{max_rounds} 回合", border_style="cyan"))
        try:
            raw = (input_fn("你> ") or "").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw:
            break
        if raw.isdecimal() and not (1 <= int(raw) <= len(options)):
            console.print(Text(f"請輸入 1～{len(options)}，或直接打字", style="red"))
            continue                                             # 不算一回合
        text = options[int(raw) - 1] if raw.isdecimal() else raw
        history.append({"role": "user", "content": text})
        resp = gateway.chat([{"role": "system", "content": system}] + history)
        if on_usage:
            on_usage(resp.usage, resp.latency_s)
        rnd += 1
        reply = first_sentences(resp.text, 2) if not resp.error else f"（參謀長無回應：{resp.error}）"
        history.append({"role": "assistant", "content": reply})
        console.print(Text(f"參謀長：{reply}", style="cyan"))
    return history
