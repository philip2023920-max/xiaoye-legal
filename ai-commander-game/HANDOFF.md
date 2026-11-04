# 交接檔（給下一個 Claude session 或本機 Claude Code）

> 更新：2026-11-02（08 完成後）。本專案的工作規則在 `README.md`，心智圖是真相來源（Artifact 資料庫 `mindmap/main`），施工單在 `docs/issues/`，三審報告在 `docs/qa/m0-review.md`。

## 現況一句話
M0 完成：施工單 01～09 全部實作、審查、175 個測試全綠（09＝驗收後的平衡與截斷修正）；三項真機驗收 2026-11-02 在老闆本機以 v1 戰鬥模型跑完（推翻率 8.8% → 4.0%、壞準則 0% 退步、Haiku 與 Ollama 都打完），數據在 `docs/qa/m0-review.md`。M1（Godot 戰鬥沙盤）2026-11-04 完成：施工單 10～15 全部 ✅（ADR-0014），老闆本機打完一場 5 分鐘會戰並用 `chief replay` 回放；唯一未驗項是 2018 內顯筆電的畫面效能（有低階機時 F5 看 HUD 幀時間 < 16.7 ms）。沙盒可下載 Godot 4.7.2 Linux 無頭版（GitHub release）跑 `godot/tests/*.gd`。老闆 2026-11-04 「下一步」→ M2 Stage 2：選型與施工單草案在 `docs/12-m2-architecture.md`，D23～D29 待老闆拍板後寫 ADR-0015、開施工單 16（參謀長服務 `chief serve`）。

## 雲端金鑰：行不通
雲端環境變數 `ANTHROPIC_API_KEY` 不會送進 session（本 session 與新開子 session 都看不到，`CHIEF_ANTHROPIC_KEY` 未試）。需要跑模型的事一律在老闆本機 PowerShell 做（下面指令在本機同樣適用，`.env` 會自動讀）。

## 真機驗收步驟（已完成，留作重跑參考）

1. **確認金鑰真的通**（不花錢的查詢）。老闆的設定方式是：雲端環境「Network secrets」加了 `api.anthropic.com` 的 `x-api-key` 標頭（代理在送出時加上，Claude 看不到），環境變數 `ANTHROPIC_API_KEY` 可能只是占位值 `proxy`。所以不要看變數內容，直接打一次 API：
   ```bash
   cd ai-commander-game/m0 && uv sync
   uv run python -c "import anthropic; print([m.id for m in anthropic.Anthropic().models.list(limit=3).data])"
   ```
   印出模型清單＝通。金鑰可能放在環境變數 `ANTHROPIC_API_KEY` 或備用名 `CHIEF_ANTHROPIC_KEY`（`chief` 指令會自動轉換；直接用 SDK 時先 `export ANTHROPIC_API_KEY=$CHIEF_ANTHROPIC_KEY`）。若 401／authentication 錯誤或 SDK 說 api_key must be set：請老闆到雲端環境設定的 Environment variables 檢查（不要貼進聊天），再開新對話。
2. **五場全自動驗收（模擬總司令，用 08 的戰鬥模型）**：風格固定在 `samples/commander_steady.json`；開局用均衡範本部署、敵方用含戰車迫砲與天氣變化的 v1 劇本。先確認準則是初始狀態（`harness/default/doctrine.md` 沒有 `## Last adopted` 行、沒有 `doctrine.prev.md`；若有，`uv run chief doctrine undo` 或請老闆決定是否歸零），`harness/default/evals/` 裡沒有舊的 cases.jsonl／prev.json 與成績檔（有就先搬走：舊戰例是玩具沙盤的；09 改了系統提示，舊成績的對齊率不能當基準，第一次 `evals run` 會重建）。五場各自有資料夾，戰後自動討論、採納、回歸。
   ```bash
   for i in 1 2 3 4 5; do uv run chief play --provider anthropic --model claude-haiku-5-5 --commander samples/commander_steady.json --harness default --template balanced --difficulty normal --quiet --out battles/sim-$i; done
   uv run chief stats --battles battles
   ```
   先用不花錢的 fake 供應商走一遍流程確認指令沒打錯：`uv run chief play --provider fake --model fake/empty --auto --skip-aar --quiet --harness none --template balanced --difficulty normal --ledger none --out battles/dry-run`。
   看最後一行「首場 x% → 末場 y%」。目標：下降。把曲線、每場的推翻率、`harness/default/doctrine.md` 的變化貼回給老闆。
3. **回歸抓壞準則**：
   ```bash
   uv run chief evals run --provider anthropic --model claude-haiku-5-5
   uv run chief evals run --provider anthropic --model claude-haiku-5-5 --doctrine samples/bad_doctrine.md
   ```
   第二條的對齊率應明顯低於第一條並印「退步」。
4. **雙供應商**：Ollama 只能在老闆本機跑（雲端裝不了），本機用 `--provider ollama --model qwen2.5:3b` 打一場即可。
5. 做完把結果寫進 `docs/qa/m0-review.md`「真機驗收」段與施工單 07／08，更新心智圖（`tools/sync_mindmap.py` 流程見 README）。之後 M1（Godot）只能在老闆明說時開始。

## 成本
Haiku 5.5 一場約 US$0.005～0.02（含戰後討論與回歸）；五場加回歸約 US$0.2。

## 不要做的事
- 不要把金鑰寫進任何檔案或對話。
- 不要在雲端嘗試安裝 Ollama（網路白名單擋住）。
- 階段切換（Stage 4、M1）要老闆明說。
