"""施工單 03 驗收：驗證器 V1～V6。期望訊息來自 docs/10-sim-rules.md §10 規則表。"""
from __future__ import annotations

from pathlib import Path

from chief.board import load_board
from chief.sim import Order
from chief.validator import validate_orders

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "board_t0.json"


def o(unit, task, target):
    return Order(unit_id=unit, task=task, target=target)


def test_v1_unknown_or_destroyed_unit():
    b = load_board(SAMPLE)
    acc, rej = validate_orders(b, [o("plt-Z9", "hold", "B2")])
    assert acc == [] and rej[0].rule == "V1" and "不存在或已殲滅" in rej[0].reason
    b.unit("plt-A1").state = "destroyed"
    acc, rej = validate_orders(b, [o("plt-A1", "hold", "B2")])
    assert rej[0].rule == "V1"


def test_v2_player_controlled_unit_is_off_limits():
    b = load_board(SAMPLE)                      # plt-A3 是總司令直轄
    acc, rej = validate_orders(b, [o("plt-A3", "seize", "C3")])
    assert acc == [] and rej[0].rule == "V2" and "直轄" in rej[0].reason


def test_v3_targets():
    b = load_board(SAMPLE)
    _, rej = validate_orders(b, [o("plt-A2", "support", "C3")])        # support 給分區
    assert rej[0].rule == "V3"
    _, rej = validate_orders(b, [o("plt-A2", "support", "plt-A2")])    # support 自己
    assert rej[0].rule == "V3"
    _, rej = validate_orders(b, [o("plt-A2", "seize", "plt-A1")])      # seize 給單位
    assert rej[0].rule == "V3"
    acc, rej = validate_orders(b, [o("plt-A2", "support", "plt-A1"), o("plt-A1", "seize", "C3")])
    assert len(acc) == 2 and rej == []


def test_v4_one_order_per_unit():
    b = load_board(SAMPLE)
    acc, rej = validate_orders(b, [o("plt-A1", "hold", "B2"), o("plt-A1", "seize", "C3")])
    assert [x.task for x in acc] == ["hold"] and rej[0].rule == "V4"


def test_v5_max_five_orders():
    b = load_board(SAMPLE)
    orders = [o("co-A", "hold", "B2"), o("plt-A1", "hold", "B2"), o("plt-A2", "hold", "A2"),
              o("plt-A1", "seize", "C3"), o("plt-A2", "seize", "C3"), o("co-A", "seize", "C3")]
    acc, rej = validate_orders(b, orders)
    assert any(r.rule == "V5" for r in rej) and rej[-1].rule == "V5"   # 第 6 條以 V5 退回


def test_v7_company_and_its_platoon_cannot_both_be_ordered():
    b = load_board(SAMPLE)
    acc, rej = validate_orders(b, [o("co-A", "seize", "C3"), o("plt-A1", "hold", "B2")])
    assert [x.unit_id for x in acc] == ["co-A"] and rej[0].rule == "V7"
    acc, rej = validate_orders(b, [o("plt-A1", "hold", "B2"), o("co-A", "seize", "C3")])   # 反過來也一樣，先到先贏
    assert [x.unit_id for x in acc] == ["plt-A1"] and rej[0].rule == "V7"


def test_rule_priority_six_orders_example():
    """審查員建議的六條令：board_t0，預期放行 3、退回依序 V2、V1、V5。"""
    b = load_board(SAMPLE)
    orders = [o("co-A", "hold", "B2"), o("plt-A1", "hold", "B2"), o("plt-A2", "hold", "A2"),
              o("plt-A3", "hold", "B1"), o("ghost", "hold", "B2"), o("co-A", "seize", "C3")]
    acc, rej = validate_orders(b, orders)
    assert len(acc) == 1 and [r.rule for r in rej] == ["V7", "V7", "V2", "V1", "V5"]   # co-A 先到，plt-A1/A2 同鏈退回


def test_v6_routed_unit_may_only_withdraw():
    b = load_board(SAMPLE)
    b.unit("plt-A2").state = "routed"
    _, rej = validate_orders(b, [o("plt-A2", "seize", "C3")])
    assert rej[0].rule == "V6" and "撤退" in rej[0].reason
    acc, rej = validate_orders(b, [o("plt-A2", "withdraw", "A1")])
    assert len(acc) == 1 and rej == []
