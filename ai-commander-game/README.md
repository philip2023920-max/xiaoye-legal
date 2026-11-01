# AI 參謀長 RTS（專案代號 CHIEF）

> AI 參謀長全盤指揮，玩家是總司令，隨時可推翻；每次推翻都在訓練它。畫面走 TABS 風格的簡化低多邊形，重點在「推翻 → 成長」迴圈與可打包對決的參謀長生態。
> 目前階段：**Stage 1 需求釐清**。第一輪已拍板 D2～D7，第二輪待拍板 D1、D8～D10（`docs/05-decisions.md`）。

## 心智圖就是施工藍圖

| 東西 | 在哪 | 誰改 |
|---|---|---|
| **互動心智圖（真相來源）** | https://claude.ai/artifact/YRdMT6jZYGpmQfKvc7feib | 老闆直接改；Claude 施工後回寫 |
| `MINDMAP.md` | 本資料夾 | 鏡像，git 追蹤用；也可手改，衝突時以 Artifact 為準 |
| `mindmap.html` | 本資料夾 | 由腳本產生的靜態圖（markmap），不要手改 |
| `tools/mindmap.json` | 本資料夾 | Artifact 資料庫文件的本機副本（`mindmap/main`） |

```
Artifact 資料庫 mindmap/main ◀──ArtifactData get/set──▶ tools/mindmap.json
                                                            │
                                   sync_mindmap.py --import-json / --export-json
                                                            │
                                                       MINDMAP.md ──▶ mindmap.html
```

### 老闆怎麼改

1. 打開互動心智圖。點狀態符號循環切換（⬜🟡✅❌❓）；點文字直接改；點「⋯」加子節點、寫備註、搬動、刪除。
2. 想叫 Claude 做某件事：把節點改成 🟡，或在備註寫清楚。整體指示寫在右側「給 Claude 的指示」。
3. 改完告訴 Claude：「照心智圖做」。

### Claude 怎麼做（每次更動的固定流程）

1. `ArtifactData get mindmap/main` → 存成 `tools/mindmap.json`
2. `python tools/sync_mindmap.py --import-json tools/mindmap.json` → 重建 `MINDMAP.md` 與 `mindmap.html`，並印出老闆留的指示
3. 只做 🟡 的事與老闆備註；⬜ 不碰、❌ 不做、❓ 先問（附建議答案）
4. 做完把節點改 ✅、必要時更新 `docs/*.md`；在節點下加 💬 備註回報
5. `python tools/sync_mindmap.py --export-json tools/mindmap.json` → `ArtifactData set mindmap/main`（帶 `if_version`）回寫
6. `CHANGELOG.md` 加一條；commit、push
7. 階段切換（Stage 1→2→3→4）必須老闆明說，Claude 不自己往下跳

### 狀態符號

| 符號 | 意思 |
|---|---|
| ⬜ | 未開始 |
| 🟡 | 老闆要 Claude 這次做 |
| ✅ | 完成 |
| ❌ | 作廢／本版不做 |
| ❓ | 等老闆決策 |

## 檔案地圖

| 檔案 | 用途 |
|---|---|
| `mindmap-editor.html` | 互動心智圖頁面原始碼（發佈成 Artifact） |
| `MINDMAP.md` / `mindmap.html` / `tools/mindmap.json` | 見上表 |
| `tools/sync_mindmap.py` | 同步腳本（只用 Python 標準庫） |
| `docs/01-feasibility.md` | 可行性分析與來源 |
| `docs/02-prd.md` | 一頁式 PRD v0.2、本版不做、商業評分 |
| `docs/03-architecture.md` | 架構 v0.2：指揮鏈、規模階梯、AI 戰情板、命令合約、LLM 閘道、參謀長包 |
| `docs/04-roadmap.md` | 里程碑 M0～M4 與任務 |
| `docs/05-decisions.md` | 拍板紀錄與待決策（建議答案制） |
| `docs/06-engine-comparison.md` | 引擎五選項比較（D1 用） |
| `docs/adr/` | 決策備忘卡 ADR-0002～0007 |
| `CHANGELOG.md` | 每次同步紀錄 |

## 注意

- 本資料夾暫放在 `xiaoye-legal` repo 內（該 repo 原本是「小夜」App 的法律頁面）。D6 已拍板開新 repo，搬家時心智圖裡的 `docs/...` 路徑不變。
- `mindmap.html` 用的 markmap 版號 `0.18.12`（2026-11-01 npm 最新）；雲端沙盒連不到 CDN，渲染是用本機套件驗證的。
