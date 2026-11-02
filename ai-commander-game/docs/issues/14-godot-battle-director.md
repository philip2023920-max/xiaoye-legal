# 14 一場 5 分鐘會戰：劇本、難度、天氣、結束與結果畫面

> 狀態：⬜。Blocked by 12、13。ADR-0014。

**重用**：`samples/enemy_v1_*.json`（回合→秒 ×30）、`orders_v1_assault.json` 當我方劇本、`docs/10` §14 的平衡表當期望。自製：`Director`（開局、劇本排程、天氣變化、結束判定 §7、結果畫面）、`--fixed-fps` 煙霧測試。

## 驗收清單
- [ ] 開局讀部署好的板（或 `--template` 等價的 GDScript 部署）；敵方劇本第 n 回合的命令在第 30(n−1) 秒下達
- [ ] 結束：300 秒到、或一方戰力 < 30%；結果畫面：勝負、據點分、剩餘戰力、用時；寫 `user://result.json`
- [ ] 難度三級可選（啟動參數或 HUD 下拉）
- [ ] 無頭煙霧測試 `tests/smoke_battle.gd --fixed-fps 60`：攻擊劇本對 easy／normal 我方勝、hard 敵方勝（與 §14 同趨勢；數值容差另記）
- [ ] 整場 board.json 快照每 30 秒留一份（`user://battles/<id>/t<n>.json`），M0 的 `chief replay` 能回放

## 30 秒驗收腳本
F5 → 5 分鐘（或按 F 加速）→ 結果畫面；`uv run chief replay %APPDATA%\Godot\app_userdata\ai-commander-game\battles\<id>`。
