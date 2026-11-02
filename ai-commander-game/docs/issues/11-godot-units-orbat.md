# 11 方塊人、班／排／連編制樹、編制 AI 執行六種任務

> 狀態：🟡 程式完成（2026-11-02，沙盒無頭測試 34 項全過），審查中；老闆本機 F5 待驗。Blocked by 10（已驗收）。ADR-0014。

**重用**：`RTSNavGrid`（格狀 A*，從掩體碰撞烘焙）、`RTSKit.formation`／`assign_slots`（班內站位）；任務邏輯移植 `m0/chief/formation_ai.py`（§3）。自製：`Soldier`（膠囊體＋方塊頭）、`Squad`（三人一組）、`Platoon`／`Company` 節點與戰力聚合、`FormationAI`。

## 驗收清單
- [x] 讀部署好的 Board JSON（`m0/samples/board_deployed_balanced.json`，由 `chief deploy --template balanced --out` 產生）生成部隊樹：排＝三班＝九個方塊人，同分區的排排成方陣（間距 7 m）；身體色依陣營、頭色依兵種（戰車畫成方塊車）；敵方讀 `enemy_script_v1.json` 的 units
- [x] 速度依 `rules.unit.speed`：中心到中心 20 m 走 30 秒（偵察排 15 秒）；機動力 0.5 → 60 秒一格（M0「偶數回合才動」的連續版）；戰車不進森林、河川有本方工兵才過（目標進不去就原地）；分區歸屬看實際位置（跨格線就算進格）；到達有敵軍的分區停 30 秒再走（M0「進敵格就停」）
- [x] 六種任務（seize／hold／flank／withdraw／support／reserve）行為同 §3（`FormationAI` 逐函式移植 `formation_ai.py`，BFS 鄰格順序上左右下）；到達分區中心＝任務目標時 idle；潰散單位退往沒有敵軍的本方分區且退路不穿敵格（§2 v1.1）
- [x] 戰力聚合：排＝存活人數比例（四捨五入 0.01）；連＝子排平均、分區＝最強存活子排（同強取 id 序）；狀態推導同 §8b
- [x] 無頭測試 `tests/test_orbat.gd` 34 項：8 排 72 人／6 排 54 人；A1 seize C3 第一步 C2、約 65 秒到中心待命；偵察 45 秒走 3 格；進敵格停一回合；雨天戰車與雪天步兵減半；森林／河川／工兵；連令拆排、排令優先、直轄不碰、玩家連令可拆、flank 拆法、四種壞命令人話退回；support 相鄰即停與同距 id 序；殺 4 人 0.56、連平均；潰散往 D4 退第一步 D3 並停在 D4

## 30 秒驗收腳本
F5 → 看到藍方 8 排（72 個方塊人）在 B2／A2／B1／A1 排好、紅方 6 排在 C3／C4／D4／E4／E5；按**空白鍵**下「A 連 奪取 C3」→ 八個排走向 C3（HUD 的 t 在跳）。無頭：`tests/test_orbat.gd` 最後一行 `checks: 34 (expected 34), failures: 0`。
