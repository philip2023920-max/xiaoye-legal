# 04 Anthropic 原生路徑＋費用計量

**重用**：anthropic SDK 2.3（strict tool、`messages.parse()`、prompt caching、串流）、LiteLLM 的 `model_prices_and_context_window.json` 當價格表初始值。自製：費用 HUD 與預算警示。

## 做什麼（老闆視角）
同一個參謀長換成 Claude（預設 Haiku 5.5）來指揮：`--provider anthropic`。每回合即時顯示本場花了多少錢、今天累計多少；超過老闆設的預算會提醒。價格表玩家可改、附更新日期，畫面寫明「估算值，以帳單為準」。

## Blocked by
03。

## 驗收清單
- [x] `uv run chief play --provider anthropic --model claude-haiku-5-5 --auto` 打完一場（老闆真機：$0.0051、無回應 0）
- [x] 系統提示＋準則放前面並設快取；第 2 回合起 `cache_read_input_tokens` > 0（測試用假回應驗證欄位讀取；真實呼叫由老闆驗收時看 HUD）
- [x] `prices.json` 含 claude-haiku-5-5、claude-sonnet-5-5、deepseek-chat、ollama/*（$0）；費用＝token×單價，手算一例當測試期望值
- [x] HUD：本場／今天／本月；`--budget 0.5` 到 80% 印提醒、到 100% 印「已達預算，參謀長暫停」並改為無新命令
- [ ] 流式輸出：第一個字出現時間印在事件流（< 2 秒為目標，不做硬性測試）—— 本版用 `messages.parse()` 非串流，串流延後到 M2 的畫面
- [x] `.env.example` ↔ 程式讀取名稱逐字一致：ANTHROPIC_API_KEY（anthropic SDK）、OPENAI_API_KEY／DEEPSEEK_API_KEY（LiteLLM）、OLLAMA_HOST（litellm_adapter）、OLLAMA_MODEL（doctor；play 用 --model）

## 30 秒驗收腳本
`uv run chief play --provider anthropic --auto --budget 0.5` → 看到每回合右上角「本場 $0.0x」，結尾「本場 $0.0x｜今天 $0.0x」。

## 預估檔案
`chief/gateway/anthropic_adapter.py`、`chief/prices.json`、`chief/meter.py`（擴充）、`tests/test_meter.py`
