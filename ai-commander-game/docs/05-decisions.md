# 05 待決策清單（建議答案制）

> 文件狀態：❓ 等老闆拍板（2026-11-01）｜對應心智圖節點：`6. 風險與待決策`
> 規則：**事實我自己查，決策老闆定**。每題附建議答案與一句理由。
> 老闆可以整批回「**全照建議**」，或只回要改的題號。拍板後我會寫 ADR 到 `docs/adr/`，並更新心智圖狀態。

| # | 決策 | 選項 | 建議答案 | 一句理由 |
|---|---|---|---|---|
| D1 | 遊戲引擎 | Godot 4 ／ Unity ／ 純網頁 Three.js | **Godot 4** | 免費 MIT、低硬體需求路線相符、GDScript 像 Python 好學 |
| D2 | 第一步做什麼 | 先做畫面 ／ 先做文字版沙盤 | **先文字版沙盤（M0）** | 專案最大不確定性是「它會不會變得像我」，兩週就能驗證，不用先花 6 週做畫面 |
| D3 | 參謀長模型 | Haiku 5.5 ／ Sonnet 5.5 ／ Opus 5.5 | **節拍 Haiku 5.5，AAR Sonnet 5.5** | 一場約 US$0.1；AAR 需要判斷力才升級。之後可用 Advisor 模式再省 |
| D4 | 金鑰方式 | 玩家 BYOK ／ 自建代理伺服器 | **MVP 走 BYOK** | 零營運成本、不用做帳號系統；商業化再加代理 |
| D5 | 戰鬥類型 | 即時（RTS）／ 回合制 | **即時，但有「決策節拍」** | 保留 CoH 的即時感，又解決 LLM 延遲；M0 文字版先用回合制模擬 |
| D6 | 專案放哪 | 留在 xiaoye-legal 這個 repo 的子資料夾 ／ 開新 repo | **開新 repo（例如 `ai-commander-game`）** | 目前 repo 是「小夜」App 的法律頁面，混在一起日後難管理。這次先放子資料夾，拍板後搬家 |
| D7 | 遊戲語言 | 繁中 ／ 英文 ／ 雙語 | **介面繁中，Doctrine 雙語** | 老闆看得懂；英文 Doctrine 對模型更省 token、更穩 |

## 不是決策、是事實（已自查，不問老闆）

- wshobson agents 與 deer-flow 在雲端環境不可用 → 已降級為內部角色演繹 + WebSearch（來源見 `01-feasibility.md`）
- Claude 現行價格與 API 行為 → 依 claude-api skill 2026-10 快取表，寫在 `03-architecture.md`
- 本 repo 現況：只有 README、privacy/terms/delete-account 三個 HTML，無程式碼、無 CI

## 拍板紀錄

（尚無。老闆回覆後由 Claude 填入：日期、題號、決定、ADR 連結）
