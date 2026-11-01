"""施工單 03 驗收：閘道（用 LiteLLM 的 mock_response 離線測，不連網）。
LiteLLM 的 mock 固定回 usage 10/20（LiteLLM 行為，非本程式算出）。"""
from __future__ import annotations

import json

from chief.gateway import make_gateway
from chief.gateway.litellm_adapter import LiteLLMGateway
from chief.prompts import build_messages

VALID = json.dumps({"assessment": "守住高地", "orders": [{"unit_id": "plt-A1", "task": "hold", "target": "B2", "reason": "高地有掩蔽"}]})


def gw(mock: str) -> LiteLLMGateway:
    return LiteLLMGateway(provider="ollama", model="qwen2.5:3b", extra={"mock_response": mock})


def test_valid_json_is_parsed_and_usage_recorded():
    resp = gw(VALID).issue_orders(build_messages("doctrine", {"t": 1}, 1))
    assert resp.error is None and resp.orders is not None
    assert resp.orders.orders[0].unit_id == "plt-A1" and resp.orders.orders[0].task == "hold"
    assert resp.usage.prompt_tokens == 10 and resp.usage.completion_tokens == 20 and not resp.usage.estimated


def test_bad_json_retries_then_reports_without_crashing():
    resp = gw("這不是 JSON").issue_orders(build_messages("doctrine", {"t": 1}, 1))
    assert resp.orders is None
    assert resp.attempts == 3                      # 1 次 + 重試 2 次
    assert "無新命令" in (resp.error or "")


def test_ollama_model_name_and_api_base_defaults(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    g = make_gateway("ollama", "qwen2.5:3b")
    assert g.model == "ollama/qwen2.5:3b" and g.api_base == "http://127.0.0.1:11434"


def test_fenced_json_and_sloppy_fields_are_normalized():
    fenced = "好的：\n```json\n" + json.dumps({"assessment": "守" * 260, "orders": [
        {"unit_id": " plt-A1 ", "task": "Attack", "target": "c3", "reason": "x" * 300},
        {"unit_id": "plt-A2", "task": "fall back", "target": "A1"}]}, ensure_ascii=False) + "\n```"
    resp = gw(fenced).issue_orders(build_messages("d", {"t": 1}, 1))
    assert resp.error is None and resp.orders is not None
    o = resp.orders.sim_orders()
    assert len(resp.orders.assessment) == 200                       # 太長截斷，不退回
    assert (o[0].unit_id, o[0].task, o[0].target, len(o[0].reason)) == ("plt-A1", "seize", "C3", 120)
    assert o[1].task == "withdraw"


def test_ollama_requests_json_mode():
    g = gw(VALID)
    assert g.force_json is True


def test_prompt_contains_board_and_feedback():
    msgs = build_messages("MY-DOCTRINE", {"t": 2, "friendly": []}, 2, "zh-TW", ["V2 plt-A3 seize C3：直轄"])
    assert msgs[0]["role"] == "system" and "MY-DOCTRINE" in msgs[0]["content"] and "Traditional Chinese" in msgs[0]["content"]
    assert "Turn 2" in msgs[1]["content"] and "V2 plt-A3" in msgs[1]["content"]
