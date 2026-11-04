# AI 參謀長 RTS（專案代號 CHIEF）

> AI 參謀長全盤指揮，玩家是總司令，隨時可推翻；每次推翻都在訓練它。畫面走 TABS 風格的簡化低多邊形，重點在「推翻 → 成長」迴圈與可打包對決的參謀長生態。
> 目前階段：**Stage 2 架構設計＋環境建置**（`docs/08-stage2-architecture.md`）。選型完成、護欄已裝，等老闆說「開始」走環境建置精靈。

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
| `docs/07-reuse-catalog.md` | 可重用素材與模板目錄（ADR-0011 重用優先） |
| `docs/08-stage2-architecture.md` | Stage 2：選型比價、流程圖、環境建置精靈、金鑰表、故障排除 |
| `docs/issues/` | M0 施工單（曳光彈切片，附驗收清單與 30 秒驗收腳本） |
| `m0/` | M0 Python 環境骨架（pyproject、uv.lock、.env.example、金鑰捕捉腳本、doctor 體檢） |
| `THIRD_PARTY.md` | 進專案的第三方元件與授權 |
| `docs/adr/` | 決策備忘卡 ADR-0001～0013 |
| `CHANGELOG.md` | 每次同步紀錄 |

## M0 指令速查

| 指令 | 用途 |
|---|---|
| `uv run chief show samples/board_t0.json` | 看戰情板（`--compact` 看給 LLM 的壓縮版） |
| `uv run chief sim --orders samples/orders_scripted.json --seed 7` | 無 LLM 的劇本會戰 |
| `uv run chief deploy` / `--template armor` / `--units infantry,infantry,tank` / `--suggest --provider ollama` | 部署階段：看範本與點數、自選配比、請參謀長挑範本（`--out x.json` 存板）（08） |
| `--template balanced --enemy samples/enemy_script_v1.json --weather rain --time night` | sim／play 共用：開局部署、v1 敵方劇本（含戰車迫砲、天氣中途變化）、覆寫天氣時段（08） |
| `--difficulty easy / normal / hard` | 敵方劇本難度（09）；`uv run chief sim --orders samples/orders_v1_assault.json --template balanced --difficulty normal` 是平衡基準局（我方勝 8:3） |
| `uv run chief play --provider ollama --model qwen2.5:3b --auto` | 參謀長自動指揮（`--provider anthropic --model claude-haiku-5-5` 換 Claude） |
| `uv run chief play --provider ollama --model qwen2.5:3b` | 互動：Enter 採納、數字改令、+ 接管、- 放手、q 結束；戰後戰報卡 → 討論 → 採納準則 |
| `--budget 0.5` `--effort low` `--aar-provider anthropic --aar-model claude-sonnet-5-5` `--skip-aar` | 預算、Anthropic 思考深度、戰後檢討模型、跳過戰後 |
| `uv run chief doctrine show` / `undo` | 看準則／還原上一版 |
| `uv run chief harness list` / `export default` / `import --file x.zip` | 參謀長包 |
| `uv run chief evals run --provider ollama` | 戰例庫回歸（`--doctrine samples/bad_doctrine.md` 試壞準則） |
| `uv run chief stats` / `chief acceptance --battles 5` | 推翻率曲線／M0 五場驗收（真人） |
| `uv run chief replay battles/<場資料夾>` | 回放一場：每回合評估、命令、關鍵事件（`--all` 含敵情與退回）（09） |
| `uv run chief serve --provider fake --port 8765` | 本機參謀長服務（HTTP JSON，Godot 用；合約見 docs/10 §16）（16） |
| `uv run chief play --provider anthropic --commander samples/commander_steady.json --quiet` | 模擬總司令全自動打一場（五場驗收不用真人） |
| `HANDOFF.md` | 給下一個 session 的交接檔 |

## Effort 慣例（老闆 2026-11-01 問，Claude 建議）

- 預設 **High**。日常同步、文件、精靈步驟都用它。
- 寫難改的合約（戰情板格式、閘道介面、驗證器、成長迴圈）與疑難 bug → **Extra**。
- 授權審核、商業化前安全檢查 → **Max**。
- Ultracode 先關；M1 進 Godot 多檔並行時再評估。
- 需要切換時，Claude 在該輪開頭用「⚙️ 建議切換 effort」提示。

## 注意

- 本資料夾暫放在 `xiaoye-legal` repo 內（該 repo 原本是「小夜」App 的法律頁面）。D6 已拍板開新 repo，搬家時心智圖裡的 `docs/...` 路徑不變。
- `mindmap.html` 用的 markmap 版號 `0.18.12`（2026-11-01 npm 最新）；雲端沙盒連不到 CDN，渲染是用本機套件驗證的。
