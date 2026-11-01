#!/usr/bin/env python3
"""把 MINDMAP.md 同步成 mindmap.html，並檢查圖中引用的檔案是否存在。

用法（在 ai-commander-game 資料夾內）：
    python tools/sync_mindmap.py

只用 Python 標準庫。MINDMAP.md 是唯一真相來源；mindmap.html 由本腳本產生，不要手改。
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "MINDMAP.md"
OUT = ROOT / "mindmap.html"

STATUS = ["⬜", "🟡", "✅", "❌", "❓"]
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


def main() -> int:
    if not SRC.exists():
        print(f"找不到 {SRC}", file=sys.stderr)
        return 1
    md = SRC.read_text(encoding="utf-8")

    # 標題：取 frontmatter 的 title，否則用第一個 H1
    m = re.search(r"^title:\s*(.+)$", md, re.M)
    title = m.group(1).strip() if m else "心智圖"

    # 檢查引用的檔案是否存在（docs/...、README.md、tools/...、CHANGELOG.md）
    refs = set(re.findall(r"(?:docs/[\w\-./]+|README\.md|CHANGELOG\.md|tools/[\w\-./]+)", md))
    refs = {r for r in refs if "..." not in r}
    missing = sorted(r for r in refs if not (ROOT / r.split("#")[0]).exists())

    # 狀態統計只算「1.」以後的章節，排除「0. 這張圖怎麼用」的圖例
    body = md.split("\n## 1.", 1)[-1]
    counts = Counter(s for s in STATUS for _ in range(body.count(s)))
    summary = "　".join(f"{s} {counts.get(s, 0)}" for s in STATUS)

    # 避免 markdown 內容提早關閉 <script>
    safe_md = md.replace("</", "<\\/")
    OUT.write_text(
        TEMPLATE.format(title=title, autoloader=AUTOLOADER, summary=summary, markdown=safe_md),
        encoding="utf-8",
    )

    print(f"已產生 {OUT.relative_to(ROOT)}")
    print(f"狀態統計：{summary}")
    if missing:
        print("⚠️ 心智圖引用但不存在的檔案：")
        for r in missing:
            print(f"  - {r}")
        return 2
    print("引用檔案檢查：全部存在 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
