# 13 戰情板寫入：每 100 ms 原子寫 `user://board.json`（Board v0.2）

> 狀態：⬜。Blocked by 11。ADR-0014（D18）。

**重用**：Board v0.2 合約（`docs/09`）、M0 的 `chief show`／`replay`／戰報卡讀同一份。自製：`BoardWriter`（組 JSON、原子寫入 tmp→rename、事件流、視距迷霧、歸屬判定）。

## 驗收清單
- [ ] 每 100 ms 寫一次（可調），`time_unit: second`，`t` 為遊戲秒；欄位齊全：map／orbat（含 cost）／enemy_known（視距）／objectives／events／fog／era／weather／time_of_day
- [ ] 原子寫入（先寫 `.tmp` 再 rename），Python 端讀取不會讀到半截
- [ ] 分區歸屬與爭奪（§6）、事件 kind 與 M0 一致（order／seized／routed／destroyed／contact／weather／info）
- [ ] Python 合約測試：`m0/tests/test_godot_board.py` 用 M0 的 `load_board` 讀 Godot 寫出的檔（沙盒用無頭跑 10 秒後產生）；`chief show <檔>` 可渲染
- [ ] 壓縮快照 `compact()` 在 Python 端 < 2K token

## 30 秒驗收腳本
F5 跑 10 秒 → `uv run chief show %APPDATA%\Godot\app_userdata\ai-commander-game\board.json` 印出 M0 戰情板畫面，t 在跳。
