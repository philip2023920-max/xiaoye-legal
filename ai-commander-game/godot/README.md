# M1 Godot 戰鬥沙盤（ADR-0014）

Godot **4.7.2 標準版**、Compatibility 渲染器、Jolt 物理。骨架 `addons/rts_kit` 來自 godot-rts-kit（MIT，不改）。

## 怎麼開
1. Godot 專案管理員 → 匯入 → 選這個資料夾的 `project.godot`。
2. F5 跑 `scenes/Battle.tscn`：看到 M0 的 5×5 地圖變 3D（讀的是隔壁 `m0/samples/board_start.json`，所以 repo 結構要保持 `godot/` 與 `m0/` 並列）。
3. WASD 或滑鼠到邊緣平移、滾輪縮放；HUD 顯示時間、雙方戰力、滑鼠下的分區；**空白鍵**＝偵錯命令「A 連 奪取 C3」。

## 怎麼測（無頭，不需要顯示卡）
```bash
godot --headless --path . --import
godot --headless --path . -s tests/run_tests.gd      # 施工單 10：地圖與攝影機
godot --headless --path . -s tests/test_orbat.gd     # 施工單 11：部隊與編制 AI
godot --headless --path . -s tests/test_combat.gd    # 施工單 12：戰鬥解算（手算例）
godot --headless --path . -s tests/test_board_writer.gd   # 施工單 13：戰情板寫入
godot --headless --path . -s tools/dump_board.gd -- out=/tmp/board.json seconds=120   # 跑 120 秒把戰情板寫出來
```
Windows 要用 zip 裡的 **console 版**（GUI 版不會把輸出接到 PowerShell）：
```powershell
& "C:\dev\godot\Godot_v4.7.2-stable_win64_console.exe" --headless --path . --import
& "C:\dev\godot\Godot_v4.7.2-stable_win64_console.exe" --headless --path . -s tests/run_tests.gd; echo $LASTEXITCODE
```
最後一行 `failures: 0`、exit code 0 就是過（2＝逾時，表示有執行期錯誤，往上看 SCRIPT ERROR）。

## 資料夾
- `addons/rts_kit/` 骨架（攝影機、框選、迷霧、小地圖、格狀尋路）
- `scripts/core/` 讀戰情板與規則表（`m0://` 代表隔壁 m0 資料夾；規則表直接讀 `m0/rules/<era>.json`）
- `scripts/world/` 分區地圖與格子邏輯（BFS 鄰格順序上左右下）
- `scripts/units/` 方塊人、排（三班九人）、編制 AI（六種任務）、部隊樹與移動推進（`Orbat.advance`）
- `scripts/combat/` 每秒戰鬥解算（30 秒回合快照，查 m0 規則表）
- `scripts/core/board_writer.gd` 歸屬、視距敵情、Board v0.2 JSON、原子寫入 `user://board.json`（M0 的 `chief show` 直接讀）
- `scripts/battle/` 場景組裝；導演 `director.gd` 在施工單 14
- `tests/` 無頭測試；`tools/` 產生場景等小工具
