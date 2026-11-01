# 變更紀錄（心智圖與文件同步日誌）

每次依心智圖施工後，在此新增一條：日期｜動了哪些節點｜改了哪些檔案。

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
