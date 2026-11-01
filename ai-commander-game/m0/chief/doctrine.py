"""作戰準則（施工單 06）：有結構、有上限（2,000 字）、可撤銷；戰後由 AAR 模型提出 diff，玩家一鍵採納。"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DOCTRINE_MAX_CHARS = 2000
SECTIONS = {
    "profile": "## Commander profile",
    "tactic": "## Verified tactics",
    "rejected": "## Rejected practices (do not propose)",
    "hypothesis": "## Hypotheses to test",
}
LAST_ADOPTED = "## Last adopted"
Section = Literal["profile", "tactic", "rejected", "hypothesis"]


class DoctrineLine(BaseModel):
    section: Section
    text: str = Field(max_length=160)

    @field_validator("text", mode="before")
    @classmethod
    def _trim(cls, v):
        return str(v).strip().lstrip("-• ").strip()[:160]


class DoctrineDiff(BaseModel):
    """AAR 模型的輸出：最多各 3 條新增／刪除，加一句給玩家看的摘要（玩家語言）。"""
    summary: str = Field(default="", max_length=200)
    add: list[DoctrineLine] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list, description="existing doctrine lines to delete (substring match)")

    @field_validator("summary", mode="before")
    @classmethod
    def _trim_summary(cls, v):
        return str(v or "")[:200]

    @field_validator("add", "remove", mode="before")
    @classmethod
    def _cap3(cls, v):
        return (v or [])[:3]


class DoctrineStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.prev = self.path.with_suffix(".prev.md")

    def load(self) -> str:
        return self.path.read_text(encoding="utf-8-sig") if self.path.exists() else "# Doctrine v1\n" + "\n".join(f"{h}\n" for h in SECTIONS.values())

    def save(self, text: str) -> None:
        if self.path.exists():
            self.prev.write_text(self.path.read_text(encoding="utf-8-sig"), encoding="utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8")

    def undo(self) -> bool:
        if not self.prev.exists():
            return False
        self.path.write_text(self.prev.read_text(encoding="utf-8"), encoding="utf-8")
        self.prev.unlink()
        return True

    def opening_line(self) -> str:
        """下一場開局引用最近一次採納（不花 token）。"""
        text = self.load()
        m = re.search(re.escape(LAST_ADOPTED) + r"[^\n]*\n- ([^\n]+)", text)
        return m.group(1).strip() if m else ""


def _split_sections(text: str) -> tuple[str, dict[str, list[str]], str]:
    """回傳（標題行, {section_key: lines}, last_adopted 行）。未知段落併入 hypothesis 以免遺失。"""
    title = ""
    buckets: dict[str, list[str]] = {k: [] for k in SECTIONS}
    last = ""
    current = None
    for line in text.splitlines():
        if line.startswith("# ") and not title:
            title = line.strip()
            continue
        if line.startswith("## "):
            current = next((k for k, h in SECTIONS.items() if line.strip().lower().startswith(h.lower()[:12])), None)
            if line.strip().startswith(LAST_ADOPTED):
                current = "__last__"
            continue
        if not line.strip():
            continue
        if current == "__last__":
            last = line.strip()
        elif current:
            buckets[current].append(line.strip())
        else:
            buckets["hypothesis"].append(line.strip())
    return title or "# Doctrine", buckets, last


def _render(title: str, buckets: dict[str, list[str]], last: str) -> str:
    out = [title, ""]
    for k, h in SECTIONS.items():
        out.append(h)
        out.extend(buckets[k] or ["- (none yet)"])
        out.append("")
    if last:
        out.append(LAST_ADOPTED)
        out.append(last)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def apply_diff(text: str, diff: DoctrineDiff, stamp: str | None = None) -> tuple[str, dict]:
    """套用 diff；超過上限先砍假設、再砍最舊的已驗證戰術。回傳（新文字, 報告）。"""
    title, buckets, _ = _split_sections(text)
    removed = 0
    for needle in diff.remove:
        n = needle.strip().lstrip("-• ").strip()
        if not n:
            continue
        for k in buckets:
            before = len(buckets[k])
            buckets[k] = [l for l in buckets[k] if n.lower() not in l.lower()]
            removed += before - len(buckets[k])
    for k in buckets:
        buckets[k] = [l for l in buckets[k] if l != "- (none yet)"]
    added = 0
    for line in diff.add:
        entry = "- " + line.text
        if entry not in buckets[line.section]:
            buckets[line.section].append(entry)
            added += 1
    stamp = stamp or time.strftime("%Y-%m-%d")
    last = f"- {stamp}: {diff.summary}" if diff.summary else f"- {stamp}: +{added} -{removed}"
    trimmed = 0
    rendered = _render(title, buckets, last)
    while len(rendered) > DOCTRINE_MAX_CHARS:
        if buckets["hypothesis"]:
            buckets["hypothesis"].pop(0)
        elif buckets["tactic"]:
            buckets["tactic"].pop(0)
        elif buckets["rejected"]:
            buckets["rejected"].pop(0)
        else:
            break
        trimmed += 1
        rendered = _render(title, buckets, last)
    return rendered, {"added": added, "removed": removed, "trimmed": trimmed, "chars": len(rendered)}


def propose_diff(gateway, doctrine: str, card_summary: str, transcript: list[dict], lang: str):
    """請 AAR 模型提出準則 diff（結構化）。回傳 ParsedResponse（parsed 是 DoctrineDiff 或 None）。"""
    from .prompts import LANG_NAME
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in transcript) or "(no discussion)"
    system = (
        "You are the Chief of Staff's after-action reviewer. Update the doctrine so the Chief adapts to the Commander. "
        "Respond ONLY with JSON: {\"summary\": \"<one sentence for the Commander, in " + LANG_NAME.get(lang, lang) + ">\", "
        "\"add\": [{\"section\": \"profile|tactic|rejected|hypothesis\", \"text\": \"<English, <=120 chars>\"}], \"remove\": [\"<substring of an existing line>\"]}. "
        "At most 3 adds and 3 removes. Prefer learning from overrides: what the Commander changed and whether it worked. "
        "Put preferences under profile, proven tactics under tactic, things the Commander rejected under rejected, unproven ideas under hypothesis.\n\n"
        "## Current doctrine\n" + doctrine
    )
    user = "## Battle summary\n" + card_summary + "\n\n## Debrief transcript\n" + convo + "\n\nPropose the doctrine diff now."
    return gateway.parse([{"role": "system", "content": system}, {"role": "user", "content": user}], DoctrineDiff)


def save_aar(path: str | Path, card_summary: str, transcript: list[dict], diff: DoctrineDiff | None, adopted: bool, report: dict | None) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"card": card_summary, "transcript": transcript,
                                      "diff": diff.model_dump() if diff else None, "adopted": adopted, "report": report},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
