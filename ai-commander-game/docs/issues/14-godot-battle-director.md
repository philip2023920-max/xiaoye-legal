# 14 一場 5 分鐘會戰：劇本、難度、天氣、結束與結果畫面

> 狀態：🟡 程式完成並審查修正（2026-11-02；code-reviewer 軸 9 項：高 1 中 2 低 6，全部修正；煙霧測試 24 項；三難度與 M0 §14 同趨勢）；待老闆本機 F5。ADR-0014。

**重用**：`samples/enemy_v1_*.json`（回合→秒 ×30）、`orders_v1_assault.json` 當我方劇本、`docs/10` §14 的平衡表當期望。自製：`Director`（開局、劇本排程、天氣變化、結束判定 §7、結果畫面）、無頭煙霧測試（直接推進，不需 --fixed-fps）。

## 驗收清單
- [x] 開局讀部署好的板（`board_deployed_balanced.json`；GDScript 部署留 M2）；我方劇本（可選）與敵方劇本第 n 回合的命令在第 30(n−1) 秒下達（`Director`）
- [x] 結束：300 秒到、或一方戰力 < 初始 30%（每秒判定）；結果畫面：勝負、據點分、剩餘戰力、用時（M0 BattleResult 同欄位）；`result.json` 與快照同資料夾；R 重開
- [x] 難度三級：場景屬性 `difficulty` 或命令列 `-- difficulty=hard`（Godot 編輯器：專案設定 → 執行 → 主要執行引數填 `-- difficulty=hard`）；未知難度警告並當 normal（工具直接拒收）；HUD 顯示難度與剩餘秒數，結束後顯示「已結束」；結束那秒的 board.json 也寫出
- [x] 無頭煙霧測試 `tests/smoke_battle.gd` 24 項（約 30 秒）：攻擊劇本對 easy 勝 8:3、normal 勝 8:3、hard 敗 3:8，剩餘戰力 7.02:1.79／6.70:4.34／6.16:4.98（M0：7.02:1.73／6.64:4.15／6.07:4.71）；天氣在 60／150／210 秒切換；快照 11 份；結果畫面；另有導演單元檢查（戰力提早結束、壞命令 info、第 11 回合忽略、不寫檔、未知難度、舊檔清除、最後快照＝結束那秒）
- [x] 整場快照每 30 秒一份（`user://battles/<id>-<難度>/t<n>.json`，t0 開局；開局先清掉資料夾裡上一場的快照與結果；提早結束時補最後一份＝結束那秒，檔名＝turns_played）；M0 的 `chief replay` 支援秒制（第 n 回合＝第 30(n−1)～30n−1 秒）並印 result.json 的勝負；`m0/samples/godot_battle_sample/` 已提交並有 Python 測試

## 30 秒驗收腳本
F5 → 按空白鍵攻城（或在專案設定的主要執行引數填 `-- friendly=m0://samples/orders_v1_assault.json` 讓劇本自動打）→ 5 分鐘後結果畫面；然後 `cd C:\dev\xiaoye-legal\ai-commander-game\m0; uv run chief replay $env:APPDATA\Godot\app_userdata\ai-commander-game\battles\hill-town-start-normal` 看十回合回放。無頭：`godot --headless --path . -s tests/smoke_battle.gd` → `checks: 24 (expected 24), failures: 0`（約 30 秒）。

## 審查紀錄（2026-11-02，code-reviewer 軸）
三難度結果可重現（逐位元相同）、排程／結束／勝負／快照時點與 M0 一致。修正 9 項：開局清掉資料夾裡上一場的快照與結果（原本會讓 `chief replay` 拼接不同場次）、`dump_board` 不再順手寫快照；提早結束補最後一份快照（檔名＝turns_played）且 `chief replay` 印 result.json 的勝負；未知難度警告並當 normal、工具拒收；結束那秒的 board.json 也寫；`run_battle` 失敗模式（劇本載入失敗、沒結束）exit 1；工具與測試關掉命令列引數解析避免污染；煙霧測試開跑先清資料夾、補 8 項導演單元檢查；Python 回放斷言加上界；HUD 結束後顯示「已結束」；文件措辭。
