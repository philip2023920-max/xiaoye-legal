# 02 模擬會戰可跑（無 LLM）

**重用**：Rich 面板（01）。自製：回合制戰鬥解算與編制 AI（M0 專用，簡化規則；查過沒有現成的 Python 連級會戰模擬器可直接用）。

## 做什麼（老闆視角）
一場連對連的會戰，10 回合，不用任何 AI 模型：敵方走固定劇本，我方照預先寫好的命令清單行動。每回合編制 AI 把「連 A 佔領 B2」這種任務式命令拆成排的動作，解算戰損、據點易手、潰散，寫進戰情板，終端機逐回合顯示。跑完印勝負與摘要。

## Blocked by
01。

## 驗收清單
- [x] `uv run chief sim --orders samples/orders_scripted.json` 跑完 10 回合，每回合印沙盤與事件，最後印勝負、雙方剩餘戰力、據點
- [x] 六種任務（seize／hold／flank／withdraw／support／reserve）都有編制 AI 行為，且對一組固定輸入產生固定輸出（同 seed 同結果）
- [x] 戰損公式：手算一個例子寫在 `docs/10-sim-rules.md`，測試用那個手算值
- [x] 一方總戰力 < 30% 提前結束，事件流有「潰散」紀錄
- [x] 每回合戰情板寫入 `battles/<id>/t<N>.json`（戰例庫用）

## 30 秒驗收腳本
`uv run chief sim --orders samples/orders_scripted.json --seed 7` → 看到 10 回合跑完、最後一行「結果：我方勝／敗，據點 2/3」之類。

## 預估檔案
`chief/sim.py`、`chief/formation_ai.py`、`samples/orders_scripted.json`、`tests/test_sim.py`、`docs/10-sim-rules.md`
