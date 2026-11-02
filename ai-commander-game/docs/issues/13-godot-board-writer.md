# 13 戰情板寫入：每 100 ms 原子寫 `user://board.json`（Board v0.2）

> 狀態：🟡 程式完成（2026-11-02，沙盒無頭測試 22 項＋Python 合約測試 3 項全過），審查中；老闆本機 F5 待驗。Blocked by 11（已驗收）。ADR-0014（D18）。

**重用**：Board v0.2 合約（`docs/09`）、M0 的 `chief show`／`replay`／戰報卡讀同一份。自製：`BoardWriter`（組 JSON、原子寫入 tmp→rename、事件流、視距迷霧、歸屬判定）。

## 驗收清單
- [x] 每 100 ms 寫一次（`Battle.WRITE_INTERVAL`），`time_unit: second`，`t` 為遊戲秒，階段 ≤90 early／≤210 mid／late；欄位齊全：map／orbat（連在前、排帶 parent 與 cost，戰情板順序）／enemy_known（視距，可信度 0.9，看到殲滅就移除）／objectives／events／fog／era／weather／time_of_day／overrides_this_battle
- [x] 原子寫入（先寫 `.tmp` 再 rename；Windows 不能改名蓋過既有檔時先刪再改名）
- [x] 分區歸屬與爭奪（§6，每秒判定，據點 owner 跟著分區，地圖與旗改色）、事件結構化 {t, kind, text, unit, sector} 且 kind 與 M0 一致（order／seized／routed／destroyed／contact／weather／info）
- [x] Python 合約測試 `m0/tests/test_godot_board.py`：永遠驗已提交的 `samples/godot_board_sample.json`（`godot/tools/dump_board.gd` 跑 120 秒產生，含命令、易手、接觸、交戰）；設 `GODOT_BIN` 時現場跑引擎再驗；`chief show` 可渲染
- [x] 壓縮快照 `compact()` 在 Python 端 < 2K token（測試）

## 30 秒驗收腳本
F5 跑 10 秒 → 另開 PowerShell：`cd C:\dev\xiaoye-legal\ai-commander-game\m0; uv run chief show $env:APPDATA\Godot\app_userdata\ai-commander-game\board.json` 印出 M0 戰情板畫面，t 在跳；按空白鍵後再看，事件流有「我方取得 C2」「在 C3 發現敵…」。
