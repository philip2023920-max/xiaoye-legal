# 交接檔（給下一個 Claude session 或本機 Claude Code）

> 更新：2026-11-02。本專案的工作規則在 `README.md`，心智圖是真相來源（Artifact 資料庫 `mindmap/main`），施工單在 `docs/issues/`，三審報告在 `docs/qa/m0-review.md`。

## 現況一句話
M0（文字版沙盤＋AI 參謀長迴圈）程式完成：施工單 01～07 全部實作並經審查修正，119 個測試全綠。剩下「真機驗收」三項還沒有數據。

## 下一步（照順序）

1. **確認金鑰真的通**（不花錢的查詢）。老闆的設定方式是：雲端環境「Network secrets」加了 `api.anthropic.com` 的 `x-api-key` 標頭（代理在送出時加上，Claude 看不到），環境變數 `ANTHROPIC_API_KEY` 可能只是占位值 `proxy`。所以不要看變數內容，直接打一次 API：
   ```bash
   cd ai-commander-game/m0 && uv sync
   uv run python -c "import anthropic; print([m.id for m in anthropic.Anthropic().models.list(limit=3).data])"
   ```
   印出模型清單＝通。金鑰可能放在環境變數 `ANTHROPIC_API_KEY` 或備用名 `CHIEF_ANTHROPIC_KEY`（`chief` 指令會自動轉換；直接用 SDK 時先 `export ANTHROPIC_API_KEY=$CHIEF_ANTHROPIC_KEY`）。若 401／authentication 錯誤或 SDK 說 api_key must be set：請老闆到雲端環境設定的 Environment variables 檢查（不要貼進聊天），再開新對話。
2. **五場全自動驗收（模擬總司令）**：風格固定在 `samples/commander_steady.json`。五場各自有資料夾，戰後自動討論、採納、回歸。
   ```bash
   for i in 1 2 3 4 5; do uv run chief play --provider anthropic --model claude-haiku-5-5 --commander samples/commander_steady.json --harness default --quiet --out battles/sim-$i; done
   uv run chief stats --battles battles
   ```
   看最後一行「首場 x% → 末場 y%」。目標：下降。把曲線、每場的推翻率、`harness/default/doctrine.md` 的變化貼回給老闆。
3. **回歸抓壞準則**：
   ```bash
   uv run chief evals run --provider anthropic --model claude-haiku-5-5
   uv run chief evals run --provider anthropic --model claude-haiku-5-5 --doctrine samples/bad_doctrine.md
   ```
   第二條的對齊率應明顯低於第一條並印「退步」。
4. **雙供應商**：Ollama 只能在老闆本機跑（雲端裝不了），本機用 `--provider ollama --model qwen2.5:3b` 打一場即可。
5. 做完把結果寫進 `docs/qa/m0-review.md`「真機驗收」段與施工單 07，更新心智圖（`tools/sync_mindmap.py` 流程見 README），然後開施工單 08（`docs/issues/08-combat-model-v1.md`，決策 ADR-0013）。

## 成本
Haiku 5.5 一場約 US$0.005～0.02（含戰後討論與回歸）；五場加回歸約 US$0.2。

## 不要做的事
- 不要把金鑰寫進任何檔案或對話。
- 不要在雲端嘗試安裝 Ollama（網路白名單擋住）。
- 階段切換（Stage 4、M1）要老闆明說。
