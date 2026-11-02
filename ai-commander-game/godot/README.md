# M1 Godot 戰鬥沙盤（ADR-0014）

Godot **4.7.2 標準版**、Compatibility 渲染器、Jolt 物理。骨架 `addons/rts_kit` 來自 godot-rts-kit（MIT，不改）。

## 怎麼開
1. Godot 專案管理員 → 匯入 → 選這個資料夾的 `project.godot`。
2. F5 跑 `scenes/Battle.tscn`：看到 M0 的 5×5 地圖變 3D（讀的是隔壁 `m0/samples/board_start.json`，所以 repo 結構要保持 `godot/` 與 `m0/` 並列）。
3. WASD 或滑鼠到邊緣平移、滾輪縮放；HUD 顯示滑鼠下的分區。

## 怎麼測（無頭，不需要顯示卡）
```bash
godot --headless --path . --import
godot --headless --path . -s tests/run_tests.gd
```
Windows 要用 zip 裡的 **console 版**（GUI 版不會把輸出接到 PowerShell）：
```powershell
& "C:\dev\godot\Godot_v4.7.2-stable_win64_console.exe" --headless --path . --import
& "C:\dev\godot\Godot_v4.7.2-stable_win64_console.exe" --headless --path . -s tests/run_tests.gd; echo $LASTEXITCODE
```
最後一行 `failures: 0`、exit code 0 就是過（2＝逾時，表示有執行期錯誤，往上看 SCRIPT ERROR）。

## 資料夾
- `addons/rts_kit/` 骨架（攝影機、框選、迷霧、小地圖、格狀尋路）
- `scripts/core/` 讀戰情板（`m0://` 代表隔壁 m0 資料夾）；規則表 `rules.gd` 在施工單 12
- `scripts/world/` 分區地圖
- `scripts/battle/` 場景組裝；導演 `director.gd` 在施工單 14
- `tests/` 無頭測試；`tools/` 產生場景等小工具
