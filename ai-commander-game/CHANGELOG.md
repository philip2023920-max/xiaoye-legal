# 變更紀錄（心智圖與文件同步日誌）

每次依心智圖施工後，在此新增一條：日期｜動了哪些節點｜改了哪些檔案。

## 2026-11-01（第八次）— 進入 Stage 3，拆施工單
- 開工前檢查：未決決策 2 個（模擬規則粒度、推翻介面）附建議答案；預估檔案 ≥ 10 → 拆 7 張曳光彈施工單 `docs/issues/01～07`
- 心智圖 M0 節點展開為 7 張施工單；回寫 Artifact 資料庫

## 2026-11-01（第七次）— 環境建置精靈完成
- 老闆決定護欄不擋 git push；Windows 環境 7 步全部完成（uv、Git clone 到 C:\dev、Ollama qwen2.5:3b、Anthropic 金鑰、捕捉腳本寫入 .env、uv sync、doctor 全部通過）
- `docs/08` 進度表更新、心智圖 Stage 2 節點改 ✅；回寫 Artifact 資料庫

## 2026-11-01（第六次）— 進入 Stage 2
- 選型比價（WebSearch 降級＋沙盒 uv 實測）：uv、Textual 8.2.8、LiteLLM 1.106.6＋instructor 1.17.0、anthropic 2.3.0 → ADR-0012；`docs/08-stage2-architecture.md`
- M0 環境骨架 `m0/`：pyproject、uv.lock、.env.example、.gitignore、金鑰捕捉腳本（sh／ps1）、`chief/doctor.py` 體檢（已煙霧測試）
- 實體護欄：`ai-commander-game/.claude/hooks/block-dangerous.js`（隨專案搬家）＋ repo 根目錄 `.claude/settings.json` 指向它；自測 7 條全部符合預期
- `THIRD_PARTY.md` 建立（M0 部分）；心智圖加 M0 技術棧與 Stage 2 進度；回寫 Artifact 資料庫

## 2026-11-01（第五次）— 老闆指示「重用優先」
- ADR-0011 重用優先；新增 `docs/07-reuse-catalog.md`（RTS 骨架、布娃娃、地形、UI、方塊人素材、milsymbol、Textual、LiteLLM、instructor、TextStarCraft II 摘要鏈），全部標 ⚠️ 待 Stage 2 驗證
- 架構文件標註重用元件；路線圖加 T0.0、T1.0 重用檢查
- 心智圖新增「8. 素材與模板庫」，文件索引改為 9；回寫 Artifact 資料庫

## 2026-11-01（第四次）— 老闆第三輪「全照建議」，D1～D10 全部定案
- D1 Godot 4 → ADR-0001；D8 規模階梯 → ADR-0008；D9 Anthropic＋Ollama → ADR-0009
- `05-decisions.md` 狀態改 ✅；`03-architecture.md`、`04-roadmap.md`、`06-engine-comparison.md`、README 標題同步
- 心智圖：D1／D8／D9 節點改 ✅，新增「待老闆下令進入 Stage 2」；回寫 Artifact 資料庫

## 2026-11-01（第三次）— 老闆第二輪：D10 拍板＋兩項新需求
- D10 否決建議：對決不設限制，寫 `docs/adr/0010-duels-unrestricted.md`
- 新需求 F13 Token 與費用計量、F14 戰報卡＋討論（遊戲化從簡）→ `02-prd.md` v0.3、`03-architecture.md` v0.3、`04-roadmap.md`（T0.9、T0.10、T2.7、T2.8）
- 心智圖：核心玩法加「戰報卡＋討論」子樹；技術架構加「Token 計量」子樹；D10 改 ✅；回寫 Artifact 資料庫

## 2026-11-01（第二次）— 老闆第一輪拍板，設計改版 v0.2
- 拍板：D2、D3、D4、D5、D6、D7 → 寫入 `docs/05-decisions.md` 拍板紀錄與 `docs/adr/0002～0007`
- 設計改版：AI 全盤操作、玩家隨時推翻；常駐 AI 戰情板；多供應商 LLM 閘道；參謀長包與對決；三語 → `02-prd.md`、`03-architecture.md`、`04-roadmap.md` 全部改到 v0.2
- 新增 `06-engine-comparison.md`（D1 用）；新增第二輪決策 D8～D10
- 心智圖改成互動 Artifact：https://claude.ai/artifact/YRdMT6jZYGpmQfKvc7feib （資料存 Artifact 資料庫 `mindmap/main`，已寫入 version 1）；`tools/sync_mindmap.py` 加 JSON 匯入／匯出，`MINDMAP.md` 為鏡像；頁面原始碼 `mindmap-editor.html`
- 心智圖節點重排：新增「3. AI 戰情板」，技術架構加閘道與參謀長包

## 2026-11-01（第一次）— 專案啟動（Stage 1）
- 建立心智圖 `MINDMAP.md` 與產生器 `tools/sync_mindmap.py`，輸出 `mindmap.html`
- 新增 `docs/01-feasibility.md`、`02-prd.md`、`03-architecture.md`、`04-roadmap.md`、`05-decisions.md`
