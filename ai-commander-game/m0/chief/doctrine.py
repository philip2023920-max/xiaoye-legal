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
        """下一場開局引用最近一次採納（不花 token）；只回摘要句，不含日期戳。"""
        _, _, last, _ = split_sections(self.load())
        if not last:
            return ""
        body = last.lstrip("-• ").strip()
        return re.sub(r"^\d{4}-\d{2}-\d{2}:\s*", "", body)


SECTION_KEYWORDS = {"profile": ("profile", "commander"), "tactic": ("verified", "tactic"), "rejected": ("rejected", "do not"), "hypothesis": ("hypothes", "to test")}
PLACEHOLDER = re.compile(r"^-?\s*\(?none( yet)?\)?\.?$", re.I)
MIN_REMOVE_NEEDLE = 8


def _section_key(heading: str) -> str | None:
    h = heading.strip().lstrip("#").strip().lower()
    if h.startswith(LAST_ADOPTED.lstrip("# ").lower()):
        return "__last__"
    for k, words in SECTION_KEYWORDS.items():
        if any(w in h for w in words):
            return k
    return None


def split_sections(text: str) -> tuple[str, dict[str, list[str]], str, list[str]]:
    """回傳（標題行, {section_key: lines}, last_adopted 行, 其他段落原文）。手改檔的未知標題整段保留在 notes。"""
    text = text.lstrip("\ufeff")
    title = ""
    buckets: dict[str, list[str]] = {k: [] for k in SECTIONS}
    last = ""
    notes: list[str] = []
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("# ") and not title:
            title = line.strip()
            continue
        if line.startswith("## "):
            current = _section_key(line)
            if current is None:
                current = "__notes__"
                notes.append(line.strip())
            continue
        if not line.strip():
            continue
        if current == "__last__":
            last = line.strip().lstrip("-• ").strip()
            last = "- " + last if last else ""
        elif current == "__notes__":
            notes.append(line.strip())
        elif current:
            if not PLACEHOLDER.match(line.strip()):
                buckets[current].append(line.strip())
        else:
            notes.append(line.strip())   # 標題前的段落也保留
    return title or "# Doctrine", buckets, last, notes


def _render(title: str, buckets: dict[str, list[str]], last: str, notes: list[str] | None = None) -> str:
    out = [title, ""]
    for k, h in SECTIONS.items():
        out.append(h)
        out.extend(buckets[k] or ["- (none yet)"])
        out.append("")
    if notes:
        if not notes[0].startswith("## "):
            out.append("## Notes")
        out.extend(notes)
        out.append("")
    if last:
        out.append(LAST_ADOPTED)
        out.append(last)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def apply_diff(text: str, diff: DoctrineDiff, stamp: str | None = None) -> tuple[str, dict]:
    """套用 diff。刪除：每個 needle 最多刪 1 行，先找整行相同、再找 ≥8 字的子字串（防止短字串誤殺）。
    上限：超過 2,000 字先淘汰最舊的假設 → 戰術 → 被否決 → 畫像（剛新增的不淘汰），仍超過就硬截。"""
    title, buckets, _, notes = split_sections(text)
    removed = 0
    ignored: list[str] = []
    for needle in diff.remove[:3]:
        n = needle.strip().lstrip("-• ").strip()
        if not n:
            continue
        hit = None
        for k in buckets:
            for l in buckets[k]:
                if l.lstrip("-• ").strip().lower() == n.lower():
                    hit = (k, l)
                    break
            if hit:
                break
        if hit is None and len(n) >= MIN_REMOVE_NEEDLE:
            for k in buckets:
                for l in buckets[k]:
                    if n.lower() in l.lower():
                        hit = (k, l)
                        break
                if hit:
                    break
        if hit is None:
            ignored.append(n)
            continue
        buckets[hit[0]].remove(hit[1])
        removed += 1
    added = 0
    new_lines: set[str] = set()
    for line in diff.add[:3]:
        entry = "- " + line.text
        if entry not in buckets[line.section]:
            buckets[line.section].append(entry)
            new_lines.add(entry)
            added += 1
    stamp = stamp or time.strftime("%Y-%m-%d")
    last = f"- {stamp}: {diff.summary}" if diff.summary else f"- {stamp}: +{added} -{removed}"
    trimmed = 0
    rendered = _render(title, buckets, last, notes)
    while len(rendered) > DOCTRINE_MAX_CHARS:
        victim = None
        for k in ("hypothesis", "tactic", "rejected", "profile"):
            old = [l for l in buckets[k] if l not in new_lines]
            if old:
                victim = (k, old[0])
                break
        if victim is None:
            if notes:
                notes.pop()
                trimmed += 1
                rendered = _render(title, buckets, last, notes)
                continue
            rendered = rendered[:DOCTRINE_MAX_CHARS].rstrip() + "\n"   # 最後手段
            break
        buckets[victim[0]].remove(victim[1])
        trimmed += 1
        rendered = _render(title, buckets, last, notes)
    return rendered, {"added": added, "removed": removed, "trimmed": trimmed, "chars": len(rendered), "ignored_removes": ignored}


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


def save_aar(path: str | Path, card_summary: str, transcript: list[dict], diff: DoctrineDiff | None, adopted: bool, report: dict | None,
             card: dict | None = None, duration_s: float | None = None, skipped: bool | None = None) -> None:
    """aar.json：卡、討論、diff、是否採納、流程時長與是否跳過（PRD F14 的 < 2 分鐘、跳過率指標用）。"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"card": card or {}, "card_summary": card_summary, "transcript": transcript,
                                      "diff": diff.model_dump() if diff else None, "adopted": adopted, "report": report,
                                      "duration_s": duration_s, "skipped": skipped},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
