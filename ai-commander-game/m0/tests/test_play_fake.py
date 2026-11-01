"""施工單 03 驗收：整場自動指揮（FakeGateway，不連網）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console

from chief.board import load_board
from chief.gateway import FakeGateway
from chief.orders import ChiefOrders
from chief.play import run_play
from chief.sim import Order, load_script

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_auto_play_completes_and_logs_usage(tmp_path):
    board = load_board(SAMPLES / "board_start.json")
    board.unit("plt-A3").controlled_by = "player"          # 讓假參謀長踩到 V2
    enemy = load_script(SAMPLES / "enemy_script.json")
    scripted = [ChiefOrders(assessment="第一回合先搶城鎮", orders=[
        {"unit_id": "plt-A1", "task": "seize", "target": "C3", "reason": "價值最高"},
        {"unit_id": "plt-A3", "task": "hold", "target": "B2", "reason": "會被退回"},
    ])]
    gw = FakeGateway(scripted)
    res = run_play(gw, board, enemy, doctrine="test", out_dir=tmp_path / "b", console=Console(file=open(tmp_path / "out.txt", "w", encoding="utf-8")), quiet=True)
    assert res.battle.turns_played >= 1 and res.battle.winner in ("us", "enemy", "draw")
    assert res.rejections == 1 and res.turns[0]["rejected"][0].startswith("V2 plt-A3")
    assert len(gw.calls) == res.battle.turns_played               # 每回合問一次參謀長
    lines = (tmp_path / "b" / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == res.battle.turns_played
    assert res.meter.cost_usd == 0                                   # fake/none 無價格
    assert "Turn 2" in gw.calls[1][1]["content"] and "V2 plt-A3" in gw.calls[1][1]["content"]  # 退回回饋進下一回合
    assert (tmp_path / "b" / "llm_log.jsonl").exists()
    assert "Units you may order this turn: co-A, plt-A1, plt-A2." in gw.calls[0][1]["content"]   # 直轄排不列入


def test_budget_pauses_chief(tmp_path):
    from chief.meter import Ledger, PriceTable
    prices = tmp_path / "p.json"
    prices.write_text(json.dumps({"models": {"fake/none": {"input_per_m": 1000.0, "output_per_m": 0.0}}}), encoding="utf-8")
    board = load_board(SAMPLES / "board_start.json")
    enemy = load_script(SAMPLES / "enemy_script.json")
    gw = FakeGateway([])                      # 每回合 100 輸入 token → $0.1/回合
    res = run_play(gw, board, enemy, doctrine="t", out_dir=tmp_path / "b", prices=PriceTable(prices), quiet=True,
                   console=Console(file=open(tmp_path / "o.txt", "w", encoding="utf-8")), budget_usd=0.25,
                   ledger=Ledger(tmp_path / "ledger.jsonl"))
    assert res.budget_hit and len(gw.calls) == 3          # 第 3 回合累計 $0.3 ≥ 0.25 → 之後暫停
    assert res.battle.turns_played > 3
    assert Ledger(tmp_path / "ledger.jsonl").totals()["today"] == pytest.approx(0.3)
