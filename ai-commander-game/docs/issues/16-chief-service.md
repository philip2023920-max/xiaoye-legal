# 16 參謀長服務 `chief serve`（本機 HTTP JSON）

> 狀態：🟡 程式完成（2026-11-04）；三審第一輪 18 項已全部修正（21 個測試），待重審。M2 第一張；ADR-0015（D23、D25）。

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
- [x] 測試：`tests/test_service.py`（21 個） 用 fake 供應商與 Godot 樣板板走完 start → tick ×2（含推翻與後果）→ end → line → discuss → propose → adopt → undo；HTTP 往返（執行緒內起服務）；壞請求 400／401／404／405／409；預算暫停；settings 切換；推翻命令驗證；已直轄不算；ai_order 上級鏈；判定時點（秒制 ≥20 秒／回合制下一拍）；result 先驗；換會話補寫戰例；閒置退出等處理中的請求；token

## 30 秒驗收腳本
```bash
uv run chief serve --provider fake --port 8765 &
curl -s -X POST localhost:8765/session/start -d '{"board": '"$(cat samples/godot_board_sample.json)"'}' | head -c 200
curl -s -X POST localhost:8765/tick -d '{"t": 20, "board": '"$(cat samples/godot_board_sample.json)"'}' | head -c 400
```
看到 assessment 與 orders 就是通（`/session/start` 直接 `-d @samples/godot_board_sample.json` 也收）；`uv run pytest -q tests/test_service.py` 全綠。

## 預估檔案
`chief/bridge.py`、`chief/serve.py`、`chief/cli.py`（serve）、`tests/test_service.py`、`docs/10` §16（服務合約）

## 三審第一輪（2026-11-04，code-reviewer 軸 18 項）→ 全部修正
- 高：adopt 可重入毀掉 undo／aar.json → `aar_closed`，第二次 adopt／skip／discuss／propose 回 409；壞 `player_order` 讓下一拍 KeyError → `/override` 先驗（TASK_CHOICES＋`player_order_problem`），outcomes 文字用 `.get()`。
- 中：推翻率分子違反 §9「已直轄再改令不算」→ 以上一板 `controlled_by` 與直轄清單判、回 `counted`；`ai_order` 回退鏈改同 play.py（上級連令、最近一拍、板上 task）；§9 判定時點：秒制板推翻後 ≥20 秒的第一拍才判（§9 補一條、docs/12 同步）；「Turns left」在秒制板全錯 → `Decision n (t=… s)`＋`Time left … of 300`；閒置退出競態 → `in_flight` 計數＋結束時重設計時、輪詢 `min(5, idle/2)`；settings 的 `aar_*` 獨立、anthropic 缺金鑰在建閘道就擋、測試改成真斷言；`/session/start` 白名單 9 欄位＋準則路徑限工作目錄＋`--token`／`X-Chief-Token`；驗收腳本第 1 行修正並讓裸板也收；`end()` 的 result 先用 pydantic 驗再改狀態、拍數不動。
- 低：每拍同一組鍵、戰後 tick 409、重複 end 同形狀；HTTP 邊界（Content-Length 非數字 400、chunked 411、>16 MiB 413、PUT 等 405、`POST /health` 405、GET 未知 404、斷線不噴 traceback、405 時讀掉 body）；custom 準則 `use_template(None)`；換會話／服務退出前補寫戰例；`duration_s` 從第一次互動起算；補測試；§16 與 docs/12 §2 漂移修正。
