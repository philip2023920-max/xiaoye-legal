"""施工單 04 驗收：Anthropic adapter（假 client，不連網、不花錢）。
期望值：快取欄位名稱來自 claude-api skill README「Verifying Cache Hits」段；費用手算見 test_meter。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from chief.gateway.anthropic_adapter import AnthropicGateway, usage_from_anthropic
from chief.meter import PriceTable, Usage
from chief.orders import ChiefOrders
from chief.prompts import build_messages


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def fake_client(response=None, error=None):
    return SimpleNamespace(messages=FakeMessages(response, error))


def ok_response(cache_read=0, cache_write=0):
    orders = ChiefOrders(assessment="固守高地", orders=[{"unit_id": "plt-A1", "task": "hold", "target": "B2", "reason": "掩蔽"}])
    return SimpleNamespace(parsed_output=orders, stop_reason="end_turn",
                           usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=cache_read, cache_creation_input_tokens=cache_write),
                           content=[SimpleNamespace(type="text", text='{"assessment":"固守高地","orders":[]}')])


def test_system_prompt_is_cached_and_user_turn_separate():
    client = fake_client(ok_response())
    gw = AnthropicGateway(model="claude-haiku-5-5", client=client)
    resp = gw.issue_orders(build_messages("DOCTRINE", {"t": 1}, 1))
    call = client.messages.calls[0]
    assert call["model"] == "claude-haiku-5-5" and call["output_format"] is ChiefOrders
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"} and "DOCTRINE" in call["system"][0]["text"]
    assert call["messages"] == [{"role": "user", "content": call["messages"][0]["content"]}] and "Turn 1" in call["messages"][0]["content"]
    assert resp.orders.orders[0].unit_id == "plt-A1" and resp.error is None


def test_cache_read_tokens_are_read_from_usage():
    gw = AnthropicGateway(client=fake_client(ok_response(cache_read=900, cache_write=0)))
    resp = gw.issue_orders(build_messages("d", {}, 2))
    assert resp.usage.prompt_tokens == 1000 and resp.usage.cache_read_tokens == 900 and not resp.usage.estimated


def test_cost_with_cache_read_hand_example():
    # Haiku 5.5：輸入 $0.10／M、輸出 $0.50／M、快取讀 $0.01／M（prices.json）
    from pathlib import Path
    pt = PriceTable(Path(__file__).resolve().parent.parent / "chief" / "prices.json")
    cost = pt.cost("claude-haiku-5-5", Usage(prompt_tokens=100, completion_tokens=200, cache_read_tokens=900))
    assert cost == pytest.approx(100 * 0.10 / 1e6 + 200 * 0.50 / 1e6 + 900 * 0.01 / 1e6)   # = 0.000119


def test_api_error_becomes_plain_language_not_crash():
    import anthropic, httpx
    resp = httpx.Response(401, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    err = anthropic.AuthenticationError("invalid x-api-key", response=resp, body=None)
    gw = AnthropicGateway(client=fake_client(error=err))
    resp = gw.issue_orders(build_messages("d", {}, 1))
    assert resp.orders is None and "金鑰" in (resp.error or "")


def test_refusal_and_truncation_are_reported():
    r = ok_response(); r.stop_reason = "refusal"
    assert "refusal" in AnthropicGateway(client=fake_client(r)).issue_orders(build_messages("d", {}, 1)).error
    r2 = ok_response(); r2.stop_reason = "max_tokens"
    assert "max_tokens" in AnthropicGateway(client=fake_client(r2)).issue_orders(build_messages("d", {}, 1)).error


def test_make_gateway_builds_anthropic_without_network(monkeypatch):
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: fake_client(ok_response()))   # 不碰真 SDK client
    from chief.gateway import make_gateway
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False); monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):                       # 施工單 16 審查：沒金鑰建閘道就擋，別等第一拍
        make_gateway("anthropic", None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    gw = make_gateway("anthropic", None)
    assert gw.model == "claude-haiku-5-5" and gw.issue_orders(build_messages("d", {}, 1)).orders is not None
