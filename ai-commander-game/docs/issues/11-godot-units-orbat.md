# 11 方塊人、班／排／連編制樹、編制 AI 執行六種任務

> 狀態：🟡 程式完成並審查修正（2026-11-02；code-reviewer 軸 15 項：高 2 中 3 低 10，全部修正；沙盒無頭測試 50 項全過）；待老闆本機 F5。Blocked by 10（已驗收）。ADR-0014。

**重用**：`RTSNavGrid`（格狀 A*，從掩體碰撞烘焙）、`RTSKit.formation`／`assign_slots`（班內站位）；任務邏輯移植 `m0/chief/formation_ai.py`（§3）。自製：`Soldier`（膠囊體＋方塊頭）、`Squad`（三人一組）、`Platoon`／`Company` 節點與戰力聚合、`FormationAI`。

## 驗收清單
- [x] 讀部署好的 Board JSON（`m0/samples/board_deployed_balanced.json`，由 `chief deploy --template balanced --out` 產生）生成部隊樹：排＝三班＝九個方塊人，同分區的排排成方陣（間距 7 m）；身體色依陣營、頭色依兵種（戰車畫成方塊車）；敵方讀 `enemy_script_v1.json` 的 units
- [x] 速度依 `rules.unit.speed`：中心到中心 20 m 走 30 秒（偵察排 15 秒）；機動力 0.5 → 60 秒一格（M0「偶數回合才動」的連續版）；戰車不進森林、河川有本方工兵才過（目標進不去就原地）；分區歸屬看實際位置（跨格線就算進格）；到達有敵軍的分區停 30 秒再走（M0「進敵格就停」）
- [x] 六種任務（seize／hold／flank／withdraw／support／reserve）行為同 §3（`FormationAI` 逐函式移植 `formation_ai.py`，BFS 鄰格順序上左右下）；到達分區中心＝任務目標時 idle；潰散單位退往沒有敵軍的本方分區且退路不穿敵格（§2 v1.1）
- [x] 戰力聚合：排＝存活人數比例（四捨五入 0.01）；連＝子排平均、分區＝最強存活子排（同強取 id 序）；狀態推導同 §8b
- [x] 無頭測試 `tests/test_orbat.gd` 50 項：8 排 72 人／6 排 54 人；A1 seize C3 第一步 C2、約 65 秒到中心待命；偵察 45 秒走 3 格；進敵格停一回合；雨天戰車與雪天步兵減半；森林／河川／工兵；連令拆排、排令優先、直轄不碰、玩家連令可拆、flank 拆法、四種壞命令人話退回；support 相鄰即停與同距 id 序；殺 4 人 0.56、連平均；連全潰散／全殲滅狀態（不當機）；潰散往 D4 退第一步 D3 並停在 D4、潰散但本方格沒敵軍不動、潰散＋withdraw 照令、潰散偵察排 30 秒只退一格；hold／reserve／withdraw／flank 繞路與進入點；直轄排照自己任務走；同單位兩道令後者為準；側翼進入點腳下但目標是森林 → 原地

## 30 秒驗收腳本
F5 → 看到藍方 8 排（72 個方塊人）在 B2／A2／B1／A1 排好、紅方 6 排在 C3／C4／D4／E4／E5；按**空白鍵**下「A 連 奪取 C3」→ 八個排走向 C3（HUD 的 t 在跳）。無頭：`tests/test_orbat.gd` 最後一行 `checks: 50 (expected 50), failures: 0`。

## 審查紀錄（2026-11-02，code-reviewer 軸，M0／Godot 探針對照）
15 項全部修正：全殲滅的連 `aggregate` 取 `alive[0]` 當機 → 守門；flank 從進入點直接進森林 → 任何分支算出的下一格都過 `blocked_sectors`；連分區同強取序改為 id 字串序最大者（與 M0 `max` 相同，測試期望改 A1／E4）；潰散速度固定 speed 1；兩趟迴圈取代 `sort_custom`（同單位兩道令後者為準）；`Orbat.place_platoon` 同步分區與清暫停；中途分區不再閃 idle（只有到達任務目標才 idle）；九個站位取代疊在中心（開局與到站同一套）；`setup` 末尾 `recompute_strength`；葉節點兵種不合法拒建；閒置排不算 avoid、每 tick 快取 leaves／hostile／engineers、非裝甲不查 25 格；`orbat_index` 取代 id 序；手算值改用 `< 2.0` 與整秒；§15 補潰散速度、靜態歸屬、工兵時點、中途新令、吸附、站位、取序；補 16 項測試（34 → 50）。
