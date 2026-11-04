# 16 參謀長服務 `chief serve`（本機 HTTP JSON）

> 狀態：🟡 程式完成（2026-11-04，9 個測試全過，M0 測試 179 → 188），審查中。M2 第一張；ADR-0015（D23、D25）。

**重用**：M0 全部——`gateway`（make_gateway、FakeGateway）、`validator`、`prompts`、`meter`（UsageMeter、Ledger、PriceTable）、`override`（OverrideLog、judge_outcome）、`report`／`badges`／`discussion`／`doctrine`／`evals`、`harness`。自製：`chief/bridge.py`（`ChiefSession`：把 `play.py` 的每回合流程與戰後流程拆成不靠終端機的方法）、`chief/serve.py`（標準庫 `ThreadingHTTPServer`，不加依賴）、`chief serve` 子命令。

## 做什麼（老闆視角）
M0 那個會下令、會檢討、會學準則的參謀長，變成一個在本機背景跑的小服務。Godot 每 20 秒把戰情板送過去，拿回命令；玩家推翻、戰後討論、採納準則都走同一個服務。用假供應商就能在沙盒整套測，真模型只在老闆本機。

## Blocked by
—（M1 完成）

## 驗收清單
- [x] `ChiefSession(cfg, board)`（board, provider, model, harness/doctrine, lang, budget, effort, out_dir)`：建閘道、讀準則與參謀長包（evals 目錄）、開局引用句；每場一個 `battles/<id>-<時間>/`
- [x] `tick(board, t)`：壓縮快照 → 閘道 → 驗證器（V1～V6）→ 回 {assessment, orders(放行), rejected, usage, cost_usd, latency_s, error, outcomes}；計費進 usage.jsonl 與帳本；llm_log.jsonl 留底；預算 80%／100%（暫停後回空命令並附訊息）；收到的板存成 `t<n−1>.json`（戰例庫與回放用）
- [x] `override(unit_id, player_order, board?, ai_order?)`：寫 overrides.jsonl（snapshot_ref、strength_at、目標分區當時擁有者）；下一個 tick 以 §9 判後果並回傳
- [x] `end(board, result)`：戰報卡（三幕、徽章、提示）、摘要；`aar_line()`；`discuss(text|index)` 最多三回合、每回合三個快速回覆；`propose()` → diff；`adopt()`（套用、上限、回歸退步自動回滾、戰例進戰例庫、aar.json）；`undo()`；`skip()`（只出卡、aar.json 記 skipped）
- [x] `status()`：供應商、模型、本場費用、今天／本月、預算狀態、tick 數、推翻數；`settings(...)`：重建閘道、改語言／預算／effort
- [x] HTTP：`/health`、`/session/start`、`/tick`、`/override`、`/battle/end`、`/aar/line`、`/aar/discuss`、`/aar/propose`、`/aar/adopt`、`/aar/undo`、`/aar/skip`、`/status`、`/settings`、`/shutdown`；錯誤回 4xx／5xx 與 {"error": 人話}；單一執行緒鎖（請求序列化）；`--idle-exit` 秒數內沒請求自動退出
- [x] `chief serve --host --port --provider --model --harness --lang --budget --effort --idle-exit`；啟動印一行「參謀長服務 http://127.0.0.1:<port>（provider/model）」
- [x] 測試：`tests/test_service.py`（9 個） 用 fake 供應商與 Godot 樣板板走完 start → tick ×2（含推翻與後果）→ end → line → discuss → propose → adopt → undo；HTTP 往返（執行緒內起服務）；壞請求 400；預算暫停；settings 切換

## 30 秒驗收腳本
```bash
uv run chief serve --provider fake --port 8765 &
curl -s -X POST localhost:8765/session/start -d @samples/godot_board_sample.json | head -c 200
curl -s -X POST localhost:8765/tick -d '{"t": 20, "board": '"$(cat samples/godot_board_sample.json)"'}' | head -c 400
```
看到 assessment 與 orders 就是通；`uv run pytest -q tests/test_service.py` 全綠。

## 預估檔案
`chief/bridge.py`、`chief/serve.py`、`chief/cli.py`（serve）、`tests/test_service.py`、`docs/10` §16（服務合約）
