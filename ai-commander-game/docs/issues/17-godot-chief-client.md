# 17 Godot 節拍與參謀長客戶端

> 狀態：⬜。Blocked by 16。ADR-0015（D23、D24、D28）。

**重用**：Godot `HTTPRequest`、`OS.create_process`；M1 的 `Orbat.apply_orders`／事件流；16 的服務。自製：`scripts/chief/chief_client.gd`（啟動服務、健康檢查、請求佇列、逾時）、`scripts/chief/tick_scheduler.gd`（20 秒＋事件、最短間隔 8 秒）。

## 驗收清單
- [ ] 遊戲啟動時從 `godot/` 執行 `uv run chief serve --port <自動找空埠>`（工作目錄 `../m0`），10 秒內 `/health` 通才算上線；失敗 → HUD「參謀長服務沒起來」＋離線模式（M1 的劇本／空白鍵）；遊戲結束時 `/shutdown` 並 kill 子程序
- [ ] 開局 POST `/session/start`（board、設定）→ 開局引用句顯示在 HUD
- [ ] 節拍：t=0 立即一次，之後每 20 秒；接觸／易手／潰散／殲滅事件觸發但與上次至少隔 8 秒；思考中 HUD 顯示「參謀長思考中 n 秒」；回覆套用 `Orbat.apply_orders("us", …, issuer="ai")`（跳過直轄排）；退回清單當下一次的 feedback；60 秒無回覆記 info 事件
- [ ] 遊戲不暫停；命令套用時事件流記「參謀長令 …（延遲 n 秒）」
- [ ] 跨程序無頭整合測試 `tests/test_chief_client.gd`：啟動 `chief serve --provider fake`，打完 5 分鐘（`run_to_end` 配合等待回覆），至少 10 次 tick、事件流有參謀長命令、費用為 0；服務關掉時的失敗路徑

## 30 秒驗收腳本
F5（本機 `.env` 有金鑰、設定頁選 Anthropic Haiku）→ 左上角出現「參謀長：上次您採納了…」→ 20 秒內事件流出現「參謀長令 …」，排自己動起來。
