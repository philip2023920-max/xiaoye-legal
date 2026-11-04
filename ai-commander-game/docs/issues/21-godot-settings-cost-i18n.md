# 21 設定頁、費用 HUD、三語字串表

> 狀態：🟡 程式完成（2026-11-04；`tests/test_settings.gd` 33 檢查全過，含真的啟動 chief serve 驗 /settings 與預算暫停），審查中。ADR-0015（D25、D27）；規則 docs/10 §16（/settings、/health keys）。

**重用**：16 的 `/status`、`/settings`、`/health`（新增 `keys` 布林）；M0 的價格表與帳本；18 的 `UiText`／`i18n/ui.csv`。自製：`scripts/ui/game_settings.gd`（`GameSettings`：正規化、存讀 `user://settings.json`、轉 `/settings` body 與啟動引數、金鑰狀態文字）、`scripts/ui/settings_page.gd`（`SettingsPage`）、`scripts/ui/cost_hud.gd`（`CostHud`）、`battle.gd` 的 `apply_settings`／`rebuild_ui`／`poll_status`／三語 HUD。

## 驗收清單
- [x] 設定頁（Esc 開關；選目標中 Esc 先取消選目標）：供應商六選一、模型、戰後檢討供應商／模型、語言、預算（-1＝不設）、思考深度、參謀長包；金鑰狀態只顯示「已設定／未設定（在 m0/.env）」（服務 `/health` 的 `keys` 布林，絕不回值；fake 不需要、ollama 看 OLLAMA_HOST、openrouter 未檢查）；「儲存並套用」→ 正規化、存 `user://settings.json`、服務在線就 POST `/settings`（下一拍生效；事件「設定已套用／沒套用：原因」）；F5 時設定檔覆寫場景預設、命令列再覆寫
- [x] 費用 HUD（HUD 第三行）：本場／今天／本月（每拍更新本場；每 30 秒 GET `/status` 更新今天／本月）；預算 80% 黃「預算已用 80%」、100% 或服務說暫停 → 紅「已達預算，參謀長暫停」；本地模型（fake／ollama）另顯示最近一拍 token 與秒數
- [x] `i18n/ui.csv`：UI 字串三語（HUD 狀態行、參謀長行、費用、設定頁、事件文字共 155 鍵；板上的戰鬥事件文字留中文，與 M0 一致）；語言切換即時套用（側欄、面板、戰後畫面、設定頁整組重建並把目前狀態畫回去；HUD 文字重算）；參謀長語言隨 `/settings` 同步送服務
- [x] 無頭測試 `tests/test_settings.gd`（33 檢查）：正規化／存讀／壞檔／body／啟動引數／金鑰狀態；費用狀態與文字與顏色；設定頁填入讀回與訊號；掃描 scripts/ 用到的每個 UI_ 鍵都在 CSV、三語齊、% 佔位數一致；Battle：Esc 開關、儲存 en → 整個 UI 變英文、切回；真的啟動 chief serve → `/health keys` → 儲存預算 0 → `/settings` → 第 1 拍達預算 → HUD 紅「參謀長暫停」→ `/status` 今天／本月

## 30 秒驗收腳本
```powershell
cd godot; & "C:\dev\godot\Godot_v4.7.2-stable_win64_console.exe" --headless --path . -s tests/test_settings.gd; echo $LASTEXITCODE
```
`checks: 33 (expected 33), failures: 0`。然後 F5 → Esc → 語言改 en →「儲存並套用」→ 整個 UI 變英文 → 再 Esc 改預算 0.01 → 儲存 → 下一拍 HUD 第三行變紅「Budget reached: chief paused」。供應商改 anthropic（`m0/.env` 有金鑰、設定頁顯示「金鑰：已設定」）→ 儲存 → 下一拍起真的用 Haiku。

## 施工備註
- 設定頁與其他 UI 在 `_init` 用 `tr()` 翻好字串，Godot 不會在換語言時自動重翻 → 用重建整組 UI 的方式即時套用（狀態都在 Battle 身上，重建只是重畫）。
- 預設 `uv run chief serve` 由設定的供應商啟動；設定頁改供應商在這場就透過 `/settings` 換閘道（服務端重建閘道，失敗保留原設定並回人話）。
- 留 M3：金鑰加密儲存（PRD F5）、邊緣捲動開關進設定頁（`edge_scroll_setting` 已留）。
