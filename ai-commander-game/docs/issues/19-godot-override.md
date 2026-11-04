# 19 推翻與接管 UI

> 狀態：🟡 程式完成（2026-11-04；`tests/test_override.gd` 37 檢查全過，含真的啟動 chief serve 驗 /override 與 /release），審查中。ADR-0015（D29）；規則 docs/10 §9、§10 V2、§16。

**重用**：骨架 `RTSCameraRig.ground_at`／`screen_position`／`is_on_screen`（點地圖選分區、投影挑排——骨架 `RTSSelection` 的挑法，但不掛它：它的右鍵下令／框選／控制組與任務式命令衝突）；M1 `Orbat.apply_orders(issuer="player")`、`order_problem`、`controlled_by`、`children_of`；16 的 `/override` 與後果判定、新加的 `/release`。自製：`scripts/ui/override_flow.gd`（`OverrideFlow` 狀態機）、`scripts/ui/override_panel.gd`（`OverridePanel`）、`Platoon` 的環（`TorusMesh`：直轄金、選取白、兩者亮金；參謀長指揮且沒選＝隱藏）、`battle.gd` 的點選與下令流程。

## 驗收清單
- [x] 點地圖上的排（錨點投影 28 px 內最近的我方排）或側欄的排／連 → 左下面板：單位名（直轄中／參謀長指揮）、目前任務、六種任務按鈕、提示「點地圖選目標分區」（support 改成「點友軍排」）、「接管」（照目前任務直轄；沒任務＝固守所在分區）「放手」「取消」；右鍵／Esc 取消選目標、Esc 取消選取
- [x] 下令：先 `Orbat.order_problem` 擋壞命令（事件「總司令的命令被引擎退回：…」），再整棵子樹 `controlled_by=player`、`apply_orders("us", [Order(issuer="player")])`、環變金；參謀長下一拍的連令拆排時跳過直轄排（FormationAI）、客戶端也跳過直轄單位、服務端 V2 擋；「放手」整棵子樹交回 ai、環消失、事件「總司令放手 X，交回參謀長」
- [x] 每次下令 → POST `/override {unit_id, player_order, board, t}`（ai_order 由服務沿上級鏈找）→ 回 `counted`：算 → `overrides_this_battle += 1`、事件「推翻已記錄（第 n 次，推翻率 r）」；已直轄再改令 → 事件「已直轄單位改令，不算推翻」；放手 → POST `/release {unit_ids}`，之後再接管又算；後果 👍／👎／➖ 由 17 的 /tick outcomes 進事件流（≥20 秒後）
- [x] 推翻率（服務回的 `override_rate`，§9 定義）顯示在側欄參謀長區
- [x] 無頭測試 `tests/test_override.gd`（37 檢查）：狀態機 8 項；面板文字／按鈕狀態／訊號；Battle 接管（環、事件、壞目標退回、連含子排、放手、接管照目前任務、側欄點樹）；真的啟動 chief serve：第 1 拍令 → 改令算一次（ai_order＝seize C3、推翻率 1/3、板上 overrides_this_battle）→ 再改不算 → /release 後再接管算第 2 次 → 側欄顯示 2/3 → 第 2 拍連令不碰直轄排

## 30 秒驗收腳本
```powershell
cd godot; & "C:\dev\godot\Godot_v4.7.2-stable_win64_console.exe" --headless --path . -s tests/test_override.gd; echo $LASTEXITCODE
```
`checks: 37 (expected 37), failures: 0`。然後 F5 → 點 A3 排（或側欄的 A3）→ 面板按「固守」→ 點地圖 B1 → 環變金、側欄事件流「總司令接管 A3 步兵排，改為 固守 B1」與「推翻已記錄（第 1 次…）」→ 20 秒後的拍出現「推翻後果 … → 👍」。

## 來自施工單 16 二審的待辦 → 已做
- 新端點 `POST /release {unit_ids}`：立刻從直轄清單拿掉並記「已明確放手」，同一拍內再接管算新的一次（§16 已改；m0 `test_release_makes_next_takeover_count`）。

## 施工備註
- 不掛骨架的 `RTSSelection`：它的右鍵＝移動／攻擊、框選、控制組是即時戰略的操作模型，和「任務式命令＋點地圖選分區」衝突；只借它的投影挑排想法。
- 面板沒有「確認」鍵：點完目標立刻下令（少一步）；誤點可再下一道或放手。
