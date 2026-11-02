"""施工單 03／04 驗收：Token 計量。期望值：Haiku 5.5 官方價 $0.10／$0.50 每百萬 token（claude-api skill 2026-10 價格表），
1000 輸入 + 200 輸出 = 0.0001 + 0.0001 = $0.0002（手算）。本地模型 $0。"""
from __future__ import annotations

import json

import pytest

from chief.meter import PriceTable, Usage, UsageMeter


def test_haiku_cost_hand_example():
    from pathlib import Path
    pt = PriceTable(Path(__file__).resolve().parent.parent / "chief" / "prices.json")   # 04-3：用專案的價格表
    assert pt.cost("claude-haiku-5-5", Usage(prompt_tokens=1000, completion_tokens=200)) == pytest.approx(0.0002)


def test_ollama_is_free_but_tokens_counted(tmp_path):
    m = UsageMeter(log_path=tmp_path / "usage.jsonl")
    m.record(1, "ollama", "ollama/qwen2.5:3b", Usage(prompt_tokens=500, completion_tokens=50), 1.2)
    m.record(2, "ollama", "ollama/qwen2.5:3b", Usage(prompt_tokens=600, completion_tokens=40), 0.8)
    assert m.cost_usd == 0 and m.prompt_tokens == 1100 and m.completion_tokens == 90
    lines = (tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["turn"] == 1
    assert "$0.0000" in m.summary() and "估算值" in m.summary()


def test_ledger_today_and_month(tmp_path):
    import time
    from chief.meter import Ledger
    led = Ledger(tmp_path / "ledger.jsonl")
    now = time.time()
    led.add("b1", "anthropic", "claude-haiku-5-5", 0.10, Usage(1, 1), at=now)
    led.add("b0", "anthropic", "claude-haiku-5-5", 0.05, Usage(1, 1), at=now - 2 * 86400)      # 前天
    led.add("old", "anthropic", "claude-haiku-5-5", 1.00, Usage(1, 1), at=now - 40 * 86400)   # 上個月以前
    tot = led.totals(now)
    assert tot["today"] == pytest.approx(0.10)
    assert 0.10 - 1e-9 <= tot["month"] <= 0.15 + 1e-9        # 前天是否同月看日期；40 天前一定不算


def test_price_key_alias_with_provider_prefix():
    pt = PriceTable()
    assert pt.lookup("anthropic/claude-haiku-5-5").input_per_m == pytest.approx(pt.lookup("claude-haiku-5-5").input_per_m)
    assert pt.lookup("claude-haiku-5-5").input_per_m == pytest.approx(0.10)


def test_prices_json_overrides_builtin(tmp_path):
    p = tmp_path / "prices.json"
    p.write_text(json.dumps({"updated_at": "2026-11-01", "models": {"claude-haiku-5-5": {"input_per_m": 1.0, "output_per_m": 2.0}}}), encoding="utf-8")
    pt = PriceTable(p)
    assert pt.lookup("claude-haiku-5-5").source == "prices.json"
    assert pt.cost("claude-haiku-5-5", Usage(prompt_tokens=1_000_000, completion_tokens=0)) == pytest.approx(1.0)
