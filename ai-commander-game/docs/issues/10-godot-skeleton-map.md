# 10 Godot 專案骨架＋固定俯視攝影機＋5×5 分區地圖

> 狀態：🟡 程式完成（2026-11-02，沙盒無頭測試 26 項全過），審查中；老闆本機 F5 與無頭測試待驗。M1 第一張；ADR-0014。

**重用**：godot-rts-kit `addons/rts_kit`（MIT，不改）：`RTSCameraRig` 當攝影機；`RTSKit` 常數與群組契約。地圖資料直接讀 M0 的 `m0/samples/board_start.json`（Board v0.2），不另造一份地圖格式。自製：`SectorMap`（分區格、地形色、據點旗、方塊掩體、座標↔分區）、`BoardIO`、`Battle` 場景組裝、無頭測試。

## 做什麼（老闆視角）
打開 Godot 按 F5，看到 M0 那張 5×5 地圖變成 3D：平地、高地、森林、城鎮、河川各有顏色，B2／C3／D4 三個據點插旗，城鎮與森林有方塊掩體與樹。WASD 平移、滾輪縮放、固定俯視角。沙盒能用無頭模式跑這一層的測試。

## Blocked by
—（M0 完成）

## 驗收清單
- [x] `godot/project.godot`：Godot 4.7.2、Compatibility、Jolt、1280×720；`addons/rts_kit` 複製進來含 LICENSE；`.godot/` 不進 git
- [x] `BoardIO`：讀 `m0/samples/board_start.json`（開發期走 `res://../m0`，匯出時可改 `res://data`）；schema_version 不是 0.2 就報錯（人話）
- [x] `SectorMap`：分區邊長 20 m，A1 在左上角（x 向右＝欄、z 向下＝列）；`center_of("C3") == (50, 0, 50)`；`sector_at(world)` 反查，出界回空字串；地形 5 色＋擁有方色調；據點旗（含 id 與分數的 Label3D）；城鎮 6 個方塊掩體、森林 8 棵樹（StaticBody3D，碰撞層 2，給之後的尋路烘焙）；格線
- [x] `Battle.tscn`：組裝地圖、光、環境、`RTSCameraRig`（俯仰 60°、距離 70、邊界＝地圖矩形、地面碰撞層 1 的地面碰撞體）、HUD 一行文字（戰鬥 id、滑鼠下分區）
- [x] 無頭測試 `tests/run_tests.gd`：26 項檢查、`EXPECTED_CHECKS` 守門；沙盒 exit 0（老闆本機待跑）
- [x] `godot/README.md`：怎麼開、怎麼測、資料夾說明

## 30 秒驗收腳本
Godot 專案管理員匯入 `ai-commander-game/godot/project.godot` → F5 → 看到地圖與三面旗、滑鼠移到城鎮 HUD 顯示 C3。PowerShell：`C:\dev\godot\Godot_v4.7.2-stable_win64.exe --headless --path . -s tests/run_tests.gd` → 最後一行 `failures: 0`。

## 預估檔案
`godot/project.godot`、`godot/addons/rts_kit/*`、`godot/scenes/Battle.tscn`、`godot/scripts/battle/battle.gd`、`godot/scripts/core/board_io.gd`、`godot/scripts/world/sector_map.gd`、`godot/tests/run_tests.gd`、`godot/README.md`、`godot/.gitignore`
