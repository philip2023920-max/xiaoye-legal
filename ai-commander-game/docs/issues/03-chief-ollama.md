# 03 參謀長下令：Ollama 本地路徑

**重用**：LiteLLM（OpenAI 相容呼叫、統一 usage）、instructor（schema 驗證＋把錯誤回饋給模型重試）、pydantic。自製：閘道介面、遊戲規則驗證器（單位存在、不是玩家直轄、任務與層級相符、一單位一令）。

## 做什麼（老闆視角）
讓本地模型 qwen2.5:3b 當參謀長：每回合讀壓縮版沙盤與作戰準則，回傳「評估＋最多 5 條命令」的固定格式；不合規則的命令被退回並記錄，最多重試 2 次。整場自動打完，終端機每回合顯示參謀長說了什麼、下了什麼令、哪些被退回、用了多少 token。零費用。

## Blocked by
02。

## 驗收清單
- [ ] `uv run chief play --provider ollama --auto` 用本地模型打完一場（10 回合或提前結束）
- [ ] 每回合顯示 assessment、orders、被驗證器退回的條目與原因
- [ ] 閘道介面 `Gateway.issue_orders(snapshot, doctrine) -> Orders` 不依賴任何供應商細節；`provider.json` 記錄供應商能力（strict schema、串流、價格）
- [ ] 驗證器測試：單位不存在、玩家直轄、任務層級不符、重複下令，四種各一個測試（期望值來自 `docs/10-sim-rules.md` 的規則表）
- [ ] 模型回傳壞 JSON 時重試最多 2 次，仍失敗則本回合「無新命令」並記事件，不崩潰
- [ ] UsageMeter 記錄每回合 prompt／completion token，本地模型費用顯示 $0

## 30 秒驗收腳本
確認 Ollama 在跑 → `uv run chief play --provider ollama --auto` → 看到參謀長每回合的評估與命令，結尾印「本場 token：xxxx，費用 $0.00」。

## 預估檔案
`chief/gateway/base.py`、`chief/gateway/litellm_adapter.py`、`chief/orders.py`、`chief/validator.py`、`chief/meter.py`、`chief/prompts/chief_system.md`、`harness/default/doctrine.md`、`provider.json`、`tests/test_validator.py`、`tests/test_gateway_fake.py`
