"""把戰情板與作戰準則組成給 LLM 的訊息。系統提示固定在前（快取友善），每回合只換 user 訊息。"""
from __future__ import annotations

import json
from pathlib import Path

LANG_NAME = {"zh-TW": "Traditional Chinese (繁體中文)", "zh-CN": "Simplified Chinese (简体中文)", "en": "English"}
SYSTEM_TEMPLATE_PATH = Path(__file__).parent / "prompts" / "chief_system.md"


def load_doctrine(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        import sys
        print(f"⚠️ 找不到作戰準則 {p}，本場用空準則", file=sys.stderr)
        return "(no doctrine yet)"
    return p.read_text(encoding="utf-8-sig")


def system_prompt(doctrine: str, lang: str = "zh-TW") -> str:
    template = SYSTEM_TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.replace("{language}", LANG_NAME.get(lang, lang)).replace("{doctrine}", doctrine.strip())


def _orderable(snapshot: dict) -> list[str]:
    return [u["id"] for u in snapshot.get("friendly", []) if u.get("ctrl") != "player"]


def _sector_range(snapshot: dict) -> str:
    ids = list(snapshot.get("map", {}).get("sectors", {}).keys())
    return f"{ids[0]}..{ids[-1]}" if ids else "(none)"


def user_prompt(snapshot: dict, turn: int, feedback: list[str] | None = None) -> str:
    parts = [f"Turn {turn}. Situation board (JSON):", json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))]
    parts.append(f"Units you may order this turn: {', '.join(_orderable(snapshot)) or '(none)'}. Sector ids: {_sector_range(snapshot)}.")
    if feedback:
        parts.append("Your orders rejected last turn (do not repeat the mistake):")
        parts.extend(f"- {f}" for f in feedback)
    parts.append("Issue this turn's orders now as the JSON object described in the system prompt.")
    return "\n".join(parts)


def build_messages(doctrine: str, snapshot: dict, turn: int, lang: str = "zh-TW", feedback: list[str] | None = None) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt(doctrine, lang)},
        {"role": "user", "content": user_prompt(snapshot, turn, feedback)},
    ]
