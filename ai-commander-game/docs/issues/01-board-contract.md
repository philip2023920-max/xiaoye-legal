# 01 戰情板合約＋靜態渲染

**重用**：pydantic 2（schema）、Rich 14（Textual 相依，終端機面板）。自製：schema 本身與分區地圖字元渲染（沒有現成的）。

## 做什麼（老闆視角）
給遊戲一份「參謀長的沙盤」正式格式：分區地圖、部隊樹（班排連旅軍團）、事件流、目標、迷霧、規模欄位、玩家直轄標記。附一份範例戰局檔，執行一個指令就能在終端機看到沙盤長什麼樣。這是所有層共用的合約，以後引擎往裡寫、LLM 從裡讀、戰報卡回放它。

## Blocked by
無。

## 驗收清單
- [ ] `uv run chief show samples/board_t0.json` 顯示：分區地圖（5×5 格，據點與擁有者）、部隊樹（可見 echelon、戰力、狀態、任務、controlled_by）、最近事件、目標
- [ ] 範例檔含會戰規模（連級，含敵我各 1 個連、3 個排）
- [ ] `board.compact()` 輸出給 LLM 的壓縮版 JSON，範例檔壓縮後 < 2,000 token（用 anthropic SDK `count_tokens` 或字元÷4 估算，報告註明用哪種）
- [ ] 不合法的戰局檔（排的 parent 指到不存在的連）載入時報人話錯誤
- [ ] 文件 `docs/09-board-schema.md`：每個欄位一句話說明，附範例

## 30 秒驗收腳本
打開 PowerShell → `cd C:\dev\xiaoye-legal\ai-commander-game\m0` → `git pull` → `uv run chief show samples/board_t0.json` → 應看到地圖、部隊樹、事件三個面板。

## 預估檔案
`chief/board.py`、`chief/render.py`、`chief/cli.py`、`samples/board_t0.json`、`tests/test_board.py`、`docs/09-board-schema.md`
