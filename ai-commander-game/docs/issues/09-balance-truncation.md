# 09 平衡與截斷：難度分級、潰散撤出、參謀長看得到分數、回覆截斷重試

> 狀態：🟡 程式完成（2026-11-02，測試 157 → 171），審查中；30 秒驗收腳本的 Haiku 那一條待老闆本機跑。
> 來源：M0 真機驗收發現 5（五場全敗 3:8）與 1（Haiku 回覆被 max_tokens=2048 截斷），老闆 2026-11-02 指示「先修平衡與截斷問題，開新施工單」。

**重用**：現有引擎、提示模板、戰報卡、Anthropic adapter；只加規則與資料，不加新套件。

## 做什麼（老闆視角）
五場驗收裡 Haiku 從頭到尾守著 3 分的高地，看著敵方拿 8 分。原因有三：敵方劇本只有一種難度而且偏硬；潰散的守軍留在城裡當肉盾、援軍一到永遠「爭奪中」，城鎮根本打不下來；參謀長看不到「現在幾比幾、還剩幾回合」。這張單把這三件事修掉，再把回覆被截斷的回合從「無命令」改成「要求精簡再試一次」。

## Blocked by
08。

## 驗收清單
- [x] **潰散撤出**（§2 v1.1）：潰散單位往最近的「沒有敵軍的本方分區」退 1 格；本方分區全有敵軍才原地不動。守軍潰散後分區易手（測試：潰散敵軍從爭奪中的 C3 退到 D3，C3 變我方並寫 `seized`）
- [x] **難度三級**：`samples/enemy_v1_easy.json`（4 個排、無戰車迫砲、不推 B2）、`enemy_script_v1.json`＝normal、`enemy_v1_hard.json`（兩個戰車、第 1 回合就壓 C2、第 3 回合攻 B2）；`chief sim/play --difficulty easy|normal|hard`（沒給 `--enemy` 時生效）
- [x] **平衡定義可測**（§14）：用一份合理的集中攻擊劇本 `samples/orders_v1_assault.json`（三個步兵排＋反戰車攻 C3、迫砲在 B3 間接射擊、機槍與工兵守 B2），均衡範本、無隨機：easy 我方勝 8:3、normal 我方勝 8:3、hard 敵方勝 3:8（測試鎖住這三個結果）
- [x] **參謀長看得到分數**：每回合 user 訊息加「Score now: us X : enemy Y. Objectives not ours: … Turns left including this one: N.」，落後時加「不奪取至少一個據點就輸」；系統提示加「據點分定勝負、攻城要集中三個排＋迫砲、不要分散 support」
- [x] **截斷重試**：Anthropic `max_tokens` 2048 → 4096；`stop_reason=max_tokens` 時把精簡要求併進同一則 user 訊息再試一次，兩次都計費（attempts=2）；仍截斷才「本回合無新命令」。系統提示改評估 ≤ 120 字、reason ≤ 60 字可空、整則 < 600 字（LiteLLM 路徑由 instructor 的驗證重試涵蓋，不另改）
- [x] **戰報卡提示**（§11）：沒贏且整場沒拿下任何開局不屬於我方的目標 → 卡上一行「整場沒有奪取任何新據點：O2（5 分，C3）一直是敵方…」，寫進 `aar.json` 與給參謀長的摘要；討論第 1 回合第一個快速回覆變成「為什麼整場沒去拿新據點？」
- [ ] 真機：`chief play --provider anthropic --model claude-haiku-5-5 --auto --template balanced --difficulty normal --skip-aar` 一場，看評估變短、有去攻 C3（老闆本機）

## 30 秒驗收腳本
```bash
uv run chief sim --orders samples/orders_v1_assault.json --template balanced --difficulty easy --quiet     # 我方勝 8:3
uv run chief sim --orders samples/orders_v1_assault.json --template balanced --difficulty normal --quiet   # 我方勝 8:3
uv run chief sim --orders samples/orders_v1_assault.json --template balanced --difficulty hard --quiet     # 敵方勝 3:8
uv run chief play --provider anthropic --model claude-haiku-5-5 --auto --template balanced --difficulty normal --skip-aar
```
最後一條看三件事：每回合評估一句話、事件流有「參謀長令 … 奪取 C3」、戰後據點分不再是 3:8。

## 不做（留下一張）
對齊判定放寬（support 同格算對齊）、獨立 `evals run` 的基準戰例集註記（真機驗收發現 2、3）；K 值等資料表數字不動。

## 預估檔案
`chief/sim.py`（潰散撤出）、`chief/gateway/anthropic_adapter.py`、`chief/prompts.py`、`chief/prompts/chief_system.md`（＋harness 副本）、`chief/cli.py`（--difficulty）、`chief/report.py`、`chief/play.py`、`chief/discussion.py`、`samples/orders_v1_assault.json`、`samples/enemy_v1_easy.json`、`samples/enemy_v1_hard.json`、`tests/test_balance.py`、`docs/10` §2／§11／§14
