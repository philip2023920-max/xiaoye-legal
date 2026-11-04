# 21 設定頁、費用 HUD、三語字串表

> 狀態：⬜。Blocked by 17。ADR-0015（D25、D27）。

**重用**：16 的 `/status`、`/settings`；M0 的價格表與帳本；Godot `TranslationServer`。自製：`scripts/ui/settings.gd`、`scripts/ui/cost_hud.gd`、`godot/i18n/ui.csv`。

## 驗收清單
- [ ] 設定頁（Esc）：供應商（anthropic／ollama／openai／deepseek／openrouter／fake）、模型、戰後檢討模型、語言、預算、思考深度；金鑰狀態只顯示「已設定／未設定（在 m0/.env）」；存 `user://settings.json`，下一 tick 生效（POST `/settings`）
- [ ] 費用 HUD：本場／今天／本月；80% 提醒黃、100% 紅且顯示「參謀長暫停」；本地模型顯示 token 與秒數
- [ ] `i18n/ui.csv`：所有 UI 字串三語；語言切換即時套用；參謀長語言同步送服務
- [ ] 無頭測試：設定存讀、字串表三欄齊全且無缺鍵

## 30 秒驗收腳本
Esc → 改成 en → 整個 UI 變英文 → 改預算 0.01 → 下一 tick 後 HUD 變紅「參謀長暫停」。
