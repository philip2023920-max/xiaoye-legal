# 14 一場 5 分鐘會戰：劇本、難度、天氣、結束與結果畫面

> 狀態：🟡 程式完成（2026-11-02，沙盒煙霧測試 14 項全過，三難度結果與 M0 §14 同趨勢），審查中；老闆本機 F5 待驗。Blocked by 12、13（已驗收）。ADR-0014。

**重用**：`samples/enemy_v1_*.json`（回合→秒 ×30）、`orders_v1_assault.json` 當我方劇本、`docs/10` §14 的平衡表當期望。自製：`Director`（開局、劇本排程、天氣變化、結束判定 §7、結果畫面）、`--fixed-fps` 煙霧測試。

## 驗收清單
- [x] 開局讀部署好的板（`board_deployed_balanced.json`；GDScript 部署留 M2）；我方劇本（可選）與敵方劇本第 n 回合的命令在第 30(n−1) 秒下達（`Director`）
- [x] 結束：300 秒到、或一方戰力 < 初始 30%（每秒判定）；結果畫面：勝負、據點分、剩餘戰力、用時（M0 BattleResult 同欄位）；`result.json` 與快照同資料夾；R 重開
- [x] 難度三級：場景屬性 `difficulty` 或命令列 `-- difficulty=hard`（Godot 編輯器：專案設定 → 執行 → 主要執行引數填 `-- difficulty=hard`）；HUD 顯示難度與剩餘秒數
- [x] 無頭煙霧測試 `tests/smoke_battle.gd`（直接推進，不需 --fixed-fps）：攻擊劇本對 easy 勝 8:3、normal 勝 8:3、hard 敗 3:8，剩餘戰力 7.02:1.79／6.70:4.34／6.16:4.98（M0：7.02:1.73／6.64:4.15／6.07:4.71）；天氣在 60／150／210 秒切換；快照 11 份；結果畫面
- [x] 整場快照每 30 秒一份（`user://battles/<id>-<難度>/t<n>.json`，t0 開局）；M0 的 `chief replay` 支援秒制（第 n 回合＝第 30(n−1)～30n−1 秒）；`m0/samples/godot_battle_sample/` 已提交並有 Python 測試

## 30 秒驗收腳本
F5 → 按空白鍵攻城（或在專案設定的主要執行引數填 `-- friendly=m0://samples/orders_v1_assault.json` 讓劇本自動打）→ 5 分鐘後結果畫面；然後 `cd C:\dev\xiaoye-legal\ai-commander-game\m0; uv run chief replay $env:APPDATA\Godot\app_userdata\ai-commander-game\battles\hill-town-start-normal` 看十回合回放。無頭：`godot --headless --path . -s tests/smoke_battle.gd` → `checks: 14 (expected 14), failures: 0`（約 1 分鐘）。
