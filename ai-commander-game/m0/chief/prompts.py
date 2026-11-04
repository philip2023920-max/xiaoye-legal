"""把戰情板與作戰準則組成給 LLM 的訊息。系統提示固定在前（快取友善），每回合只換 user 訊息。"""
from __future__ import annotations

import json
import math
from pathlib import Path

LANG_NAME = {"zh-TW": "Traditional Chinese (繁體中文)", "zh-CN": "Simplified Chinese (简体中文)", "en": "English"}
SYSTEM_TEMPLATE_PATH = Path(__file__).parent / "prompts" / "chief_system.md"
BATTLE_SECONDS = 300      # docs/10 §15：Godot 一場 300 秒（M0 10 回合 × 30 秒）
TICK_SECONDS = 20         # ADR-0015 D24：每 20 秒一拍


def load_doctrine(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        import sys
        print(f"⚠️ 找不到作戰準則 {p}，本場用空準則", file=sys.stderr)
        return "(no doctrine yet)"
    return p.read_text(encoding="utf-8-sig")


_template_override: Path | None = None


def use_template(path: str | Path | None) -> None:
    """參謀長包可帶自己的系統提示模板（harness/<name>/prompts/chief_system.md）。"""
    global _template_override
    _template_override = Path(path) if path else None


def system_prompt(doctrine: str, lang: str = "zh-TW", era: str = "ww2_1944") -> str:
    from .rules import load_rules
    src = _template_override if (_template_override and _template_override.exists()) else SYSTEM_TEMPLATE_PATH
    template = src.read_text(encoding="utf-8-sig")
    rules_text = load_rules(era).prompt_text()
    if "{rules}" not in template:
        if "## Doctrine" in template:
            template = template.replace("## Doctrine", "{rules}\n\n## Doctrine", 1)
        else:   # 舊參謀長包的模板沒有掛點：附在最後，並提醒一次
            import sys
            print(f"⚠️ 系統提示模板 {src} 沒有 {{rules}} 掛點，戰鬥模型說明附在結尾", file=sys.stderr)
            template = template.rstrip() + "\n\n{rules}\n"
    return (template.replace("{language}", LANG_NAME.get(lang, lang)).replace("{doctrine}", doctrine.strip())
            .replace("{rules}", rules_text))


def _orderable(snapshot: dict) -> list[str]:
    return [u["id"] for u in snapshot.get("friendly", []) if u.get("ctrl") != "player"]


def _sector_range(snapshot: dict) -> str:
    ids = list(snapshot.get("map", {}).get("sectors", {}).keys())
    return f"{ids[0]}..{ids[-1]}" if ids else "(none)"


def _seconds_mode(snapshot: dict) -> bool:
    return snapshot.get("unit") == "second"


def _time_left(snapshot: dict, turn: int) -> str:
    """施工單 16：Godot 的板是秒制（t 秒／300 秒，每 ~20 秒一拍），不能拿 M0 的 10 回合去算剩幾回合。"""
    from .sim import MAX_TURNS
    if _seconds_mode(snapshot):
        t = float(snapshot.get("t", 0) or 0)
        left_s = max(0.0, BATTLE_SECONDS - t)
        decisions = max(1, math.ceil(left_s / TICK_SECONDS)) if left_s > 0 else 0
        return f"Time left: about {left_s:.0f} s of {BATTLE_SECONDS} (roughly {decisions} more decisions, one every ~{TICK_SECONDS} s)."
    return f"Turns left including this one: {max(0, MAX_TURNS - turn + 1)}."


def score_line(snapshot: dict, turn: int) -> str:
    """施工單 09：把「據點分定勝負」算給參謀長看，別讓它守一個 3 分據點守到輸。"""
    objs = snapshot.get("objectives", [])
    us = sum(o.get("value", 0) for o in objs if o.get("owner") == "us")
    en = sum(o.get("value", 0) for o in objs if o.get("owner") == "enemy")
    missing = [f"{o['id']} ({o.get('value', 0)} pts at {o.get('sector')}, {'unowned' if o.get('owner', 'none') == 'none' else o.get('owner')})" for o in objs if o.get("owner") != "us"]
    line = f"Score now: us {us} : enemy {en}. Objectives not ours: {', '.join(missing) or 'none'}. {_time_left(snapshot, turn)}"
    if objs and us <= en:
        line += " You do not win on points unless you seize at least one more objective."
    return line


def user_prompt(snapshot: dict, turn: int, feedback: list[str] | None = None) -> str:
    head = f"Decision {turn} (t={float(snapshot.get('t', 0) or 0):.0f} s)" if _seconds_mode(snapshot) else f"Turn {turn}"
    parts = [f"{head}. Situation board (JSON):", json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))]
    parts.append(score_line(snapshot, turn))
    parts.append(f"Units you may order this turn: {', '.join(_orderable(snapshot)) or '(none)'}. Sector ids: {_sector_range(snapshot)}.")
    if feedback:
        parts.append("Your orders rejected last turn (do not repeat the mistake):")
        parts.extend(f"- {f}" for f in feedback)
    parts.append("Issue this turn's orders now as the JSON object described in the system prompt.")
    return "\n".join(parts)


def build_messages(doctrine: str, snapshot: dict, turn: int, lang: str = "zh-TW", feedback: list[str] | None = None) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt(doctrine, lang, snapshot.get("era", "ww2_1944"))},
        {"role": "user", "content": user_prompt(snapshot, turn, feedback)},
    ]
