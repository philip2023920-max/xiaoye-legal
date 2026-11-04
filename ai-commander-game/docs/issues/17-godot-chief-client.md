# 17 Godot 節拍與參謀長客戶端

> 狀態：🟡 程式完成（2026-11-04；`tests/test_chief_client.gd` 32 檢查全過，沙盒真的啟動 `uv run chief serve --provider fake` 打完 300 秒：21 拍、12 條參謀長令；其他 6 支 Godot 測試不受影響），審查中。ADR-0015（D23、D24、D28）。

**重用**：Godot `HTTPRequest`、`OS.create_process`；M1 的 `Orbat.apply_orders`／事件流；16 的服務。自製：`scripts/chief/chief_client.gd`（啟動服務、健康檢查、請求佇列、逾時）、`scripts/chief/tick_scheduler.gd`（20 秒＋事件、最短間隔 8 秒）。

## 驗收清單
- [x] 遊戲啟動時執行 `uv run --directory <m0> chief serve --port <自動找空埠> --token <亂數>`（`ChiefClient.launch`；`--directory` 讓服務的工作目錄是 m0，讀得到 `.env` 與 `harness/`），10 秒內 `/health` 通才算上線；失敗（找不到 uv、服務一啟動就結束、10 秒不通）→ HUD「參謀長服務沒起來：原因 → 離線模式」＋事件流一條；離線時 M1 的劇本／空白鍵照常；關窗與 R 重開先 `/shutdown`（服務會補寫戰例）、2 秒內沒退就 kill；節點被拆也 kill（不留孤兒）
- [x] 開局 POST `/session/start`（board、lang）→ 開局引用句顯示在 HUD 第二行（空引用句顯示「參謀長就位（供應商／模型）」）並寫進事件流
- [x] 節拍（`TickScheduler`）：t=0 立即一次，之後每 20 秒（從上次送出算）；接觸／易手／潰散／殲滅事件觸發但與上次至少隔 8 秒；同時只一個在飛，在飛期間到期的不丟、回覆到了就補送最新的板；思考中 HUD 顯示「參謀長思考中 n 秒」；回覆套用 `Orbat.apply_orders("us", …, issuer="ai")`，直轄排／連跳過（服務端 V2 也擋）；退回清單由服務自己帶到下一拍的 feedback（引擎退回的另記 info 事件，板上的事件會被參謀長看到）；60 秒無回覆（HTTPRequest 逾時）記 info 事件「參謀長無回應（逾時沒有回覆）」
- [x] 遊戲不暫停；命令套用時事件流有「參謀長令 …」（Orbat 原有）＋每拍一條「參謀長回覆：n 條命令、m 條退回（延遲 n 秒）」；研判寫到 HUD 第二行；預算提醒進事件流；/tick 的 outcomes（推翻後果）寫進事件流
- [x] 跨程序無頭整合測試 `tests/test_chief_client.gd`（32 檢查）：排程器純邏輯 8 項；沒有服務 → 離線與人話；真的啟動 `chief serve --provider fake`（579 ms 上線）打完 300 秒（每步推進導演、在飛就等回覆）：21 拍（15 規律＋6 事件）、12 條「參謀長令」、每拍一條回覆事件、費用 0、`/battle/end` 戰報卡勝負一致、`/status` 拍數一致、服務端 `t0.json`／`aar.json`／`llm_log` 每拍一行、最終板 `t21.json`；`stop()` 後程序結束；找不到 uv → 離線模式；`chief=off`

## 30 秒驗收腳本
```powershell
cd godot; & "C:\dev\godot\Godot_v4.7.2-stable_win64_console.exe" --headless --path . -s tests/test_chief_client.gd; echo $LASTEXITCODE
```
`checks: 32 (expected 32), failures: 0`、exit 0 就是通（需要 uv 在 PATH）。然後 F5（預設 `chief_provider=fake`，不花錢）→ 左上角第二行「參謀長就位（fake／fake/none）」→ 第 0 秒 HUD 出現「參謀長：（示範）先搶城鎮…」、排自己動起來；真模型：專案設定 → 執行 → 主要執行引數填 `-- chief=anthropic`（本機 `.env` 有金鑰）→ 第二行變成 Haiku 的研判。

## 施工備註
- `OS.create_process` 沒有工作目錄參數 → 用 `uv run --directory <m0>`；空埠用 `TCPServer.listen(0)` 找；token 由 Godot 產生傳給服務（命令列），不用讀子程序 stdout。
- 測試驅動時每步 `director.tick` → `chief_update()`，請求在飛就 `await replied` 再等 `scheduler.in_flight` 歸零（`replied` 是 `call_deferred` 發的，讓 `_chief_tick` 先 `mark_done`）；真遊戲不等。
- 設定頁（21）之前，供應商／模型用場景匯出變數或命令列 `-- chief=… chief_model=…`。
