#!/usr/bin/env python3
"""心智圖同步工具（只用 Python 標準庫）。

三種用法（在 ai-commander-game 資料夾內執行）：

  python tools/sync_mindmap.py
      MINDMAP.md → mindmap.html，並檢查圖中引用的檔案是否存在。

  python tools/sync_mindmap.py --export-json tools/mindmap.json
      MINDMAP.md → JSON（給互動心智圖 Artifact 的資料庫用）。若舊 JSON 存在，
      會盡量沿用節點 id，讓 Artifact 的折疊狀態不跳掉。

  python tools/sync_mindmap.py --import-json tools/mindmap.json
      JSON（從 Artifact 資料庫讀回）→ MINDMAP.md，再產生 mindmap.html。

真相來源：老闆在 Artifact 改過 → 以 Artifact 為準（先 --import-json）。
MINDMAP.md 是鏡像，方便 git 追蹤與離線閱讀。
"""
from __future__ import annotations

import json
import re
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "MINDMAP.md"
OUT = ROOT / "mindmap.html"

STATUS_EMOJI = {"todo": "⬜", "doing": "🟡", "done": "✅", "dropped": "❌", "decide": "❓"}
EMOJI_STATUS = {v: k for k, v in STATUS_EMOJI.items()}
NOTE_MARK = "💬"
LINK_MARK = "→"

FRONTMATTER = """---
title: AI 參謀長 RTS 心智圖
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 2
  maxWidth: 360
---
"""

# 版號 0.18.12 為 2026-11-01 從 npm registry 查到的最新版。
AUTOLOADER = "https://cdn.jsdelivr.net/npm/markmap-autoloader@0.18.12"

TEMPLATE = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --bg: #faf6f0; --fg: #2b2b2b; --bar: #ffffffcc; --accent: #b5542e; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #1b1b1f; --fg: #e8e6e3; --bar: #26262bcc; --accent: #e0885c; }}
  }}
  html, body {{ margin: 0; height: 100%; background: var(--bg); color: var(--fg);
    font-family: -apple-system, "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", sans-serif; }}
  .bar {{ position: fixed; top: 0; left: 0; right: 0; z-index: 10; padding: 8px 16px;
    background: var(--bar); backdrop-filter: blur(6px); font-size: 13px; display: flex; gap: 16px; flex-wrap: wrap; align-items: center; }}
  .bar b {{ color: var(--accent); }}
  .markmap {{ position: absolute; top: 40px; left: 0; right: 0; bottom: 0; }}
  .markmap > svg {{ width: 100%; height: 100%; }}
  .markmap a {{ color: var(--accent); }}
</style>
<script>
  window.markmap = {{ autoLoader: {{ manual: false }} }};
</script>
<script src="{autoloader}"></script>
</head>
<body>
<div class="bar">
  <b>{title}</b>
  <span>來源：MINDMAP.md（改完跑 <code>python tools/sync_mindmap.py</code>）</span>
  <span>{summary}</span>
</div>
<div class="markmap">
<script type="text/template">
{markdown}
</script>
</div>
</body>
</html>
"""


# ---------- Markdown → 樹 ----------

def split_status(text: str) -> tuple[str, str]:
    """狀態符號只認「行尾」那一個（連結已先拿掉）；行中出現的符號視為內容。"""
    t = text.strip()
    for emoji, name in EMOJI_STATUS.items():
        if t.endswith(emoji):
            return t[: -len(emoji)].strip(), name
    return t, ""


def split_link(text: str) -> tuple[str, str]:
    m = re.search(r"\s*" + LINK_MARK + r"\s*(\S+)\s*$", text)
    if m:
        return text[: m.start()].strip(), m.group(1)
    return text.strip(), ""


def parse_markdown(md: str) -> dict:
    body = md
    if body.startswith("---"):
        parts = body.split("---", 2)
        body = parts[2] if len(parts) == 3 else body
    title = "心智圖"
    nodes: list[dict] = []
    stack: list[tuple[int, dict]] = []  # (level, node)
    for raw in body.splitlines():
        if not raw.strip():
            continue
        if raw.startswith("# "):
            title = raw[2:].strip()
            continue
        if raw.startswith("## "):
            node = make_node(raw[3:])
            nodes.append(node)
            stack = [(-1, node)]
            continue
        m = re.match(r"^(\s*)-\s+(.*)$", raw)
        if not m or not stack:
            continue
        level = len(m.group(1)) // 2
        text = m.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else None
        if parent is None:
            continue
        if text.startswith(NOTE_MARK):
            note = text[len(NOTE_MARK):].strip()
            parent["note"] = (parent["note"] + "\n" + note).strip() if parent["note"] else note
            continue
        node = make_node(text)
        parent["children"].append(node)
        stack.append((level, node))
    return {"title": title, "nodes": nodes}


def make_node(text: str) -> dict:
    text, link = split_link(text)
    text, status = split_status(text)
    return {"id": "", "text": text, "status": status, "link": link, "note": "", "children": []}


# ---------- 樹 → Markdown ----------

def node_line(n: dict) -> str:
    s = n["text"].strip()
    if n.get("status"):
        s += " " + STATUS_EMOJI.get(n["status"], "")
    if n.get("link"):
        s += f" {LINK_MARK} {n['link']}"
    return s


def render_markdown(tree: dict) -> str:
    out = [FRONTMATTER, f"# {tree['title']}", ""]
    for top in tree["nodes"]:
        out.append(f"## {node_line(top)}")
        if top.get("note"):
            for ln in top["note"].splitlines():
                out.append(f"- {NOTE_MARK} {ln}")
        for child in top.get("children", []):
            render_child(child, 0, out)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_child(n: dict, level: int, out: list[str]) -> None:
    pad = "  " * level
    out.append(f"{pad}- {node_line(n)}")
    if n.get("note"):
        for ln in n["note"].splitlines():
            out.append(f"{pad}  - {NOTE_MARK} {ln}")
    for c in n.get("children", []):
        render_child(c, level + 1, out)


# ---------- id 沿用 ----------

def assign_ids(tree: dict, previous: dict | None) -> None:
    prev_map: dict[str, str] = {}
    if previous:
        def walk(nodes: list[dict], path: str) -> None:
            for n in nodes:
                key = path + "/" + n.get("text", "")
                if n.get("id"):
                    prev_map[key] = n["id"]
                walk(n.get("children", []), key)
        walk(previous.get("nodes", []), "")

    def assign(nodes: list[dict], path: str) -> None:
        for n in nodes:
            key = path + "/" + n["text"]
            if not n.get("id"):
                n["id"] = prev_map.get(key) or "n_" + uuid.uuid4().hex[:8]
            assign(n.get("children", []), key)
    assign(tree["nodes"], "")


# ---------- HTML ----------

def build_html(md: str) -> int:
    m = re.search(r"^title:\s*(.+)$", md, re.M)
    title = m.group(1).strip() if m else "心智圖"
    refs = set(re.findall(r"(?:docs/[\w\-./]+|README\.md|CHANGELOG\.md|tools/[\w\-./]+)", md))
    refs = {r for r in refs if "..." not in r}
    missing = sorted(r for r in refs if not (ROOT / r.split("#")[0]).exists())
    body = md.split("\n## 1.", 1)[-1]
    counts = Counter(s for s in STATUS_EMOJI.values() for _ in range(body.count(s)))
    summary = "　".join(f"{s} {counts.get(s, 0)}" for s in STATUS_EMOJI.values())
    safe_md = md.replace("</", "<\\/")
    OUT.write_text(TEMPLATE.format(title=title, autoloader=AUTOLOADER, summary=summary, markdown=safe_md), encoding="utf-8")
    print(f"已產生 {OUT.relative_to(ROOT)}")
    print(f"狀態統計：{summary}")
    if missing:
        print("⚠️ 心智圖引用但不存在的檔案：")
        for r in missing:
            print(f"  - {r}")
        return 2
    print("引用檔案檢查：全部存在 ✅")
    return 0


# ---------- 主程式 ----------

def main(argv: list[str]) -> int:
    if not SRC.exists():
        print(f"找不到 {SRC}", file=sys.stderr)
        return 1

    if len(argv) >= 2 and argv[0] == "--export-json":
        target = ROOT / argv[1]
        tree = parse_markdown(SRC.read_text(encoding="utf-8"))
        previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
        assign_ids(tree, previous)
        tree["version"] = (previous or {}).get("version", 0) + 1
        tree["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tree["updatedBy"] = "claude"
        tree["instructions"] = (previous or {}).get("instructions", "")
        target.write_text(json.dumps(tree, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已匯出 {target.relative_to(ROOT)}（version {tree['version']}，{count_nodes(tree['nodes'])} 個節點）")
        return 0

    if len(argv) >= 2 and argv[0] == "--import-json":
        target = ROOT / argv[1]
        tree = json.loads(target.read_text(encoding="utf-8"))
        SRC.write_text(render_markdown(tree), encoding="utf-8")
        print(f"已從 {target.relative_to(ROOT)} 重建 MINDMAP.md（updatedBy={tree.get('updatedBy')}，updatedAt={tree.get('updatedAt')}）")
        if tree.get("instructions"):
            print("📝 老闆在 Artifact 留的指示：")
            print("   " + tree["instructions"].replace("\n", "\n   "))
        return build_html(SRC.read_text(encoding="utf-8"))

    return build_html(SRC.read_text(encoding="utf-8"))


def count_nodes(nodes: list[dict]) -> int:
    return sum(1 + count_nodes(n.get("children", [])) for n in nodes)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
