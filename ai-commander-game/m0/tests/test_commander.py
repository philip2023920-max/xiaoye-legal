"""施工單 07b：模擬總司令。期望值來自 samples/commander_steady.json 的規則（手讀）。"""
from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from chief.board import load_board
from chief.commander import SimCommander
from chief.gateway import FakeGateway
from chief.orders import ChiefOrders
from chief.play import run_play
from chief.sim import Order, load_script

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_rules_translate_to_key_sequence():
    c = SimCommander.from_file(SAMPLES / "commander_steady.json")
    b = load_board(SAMPLES / "board_start.json")
    accepted = [Order(unit_id="plt-A1", task="seize", target="C3"),        # 第 2 條規則：開局 ≤2 回合不准 seize → reserve B1
                Order(unit_id="plt-A3", task="seize", target="D4")]        # 第 1 條：機槍排非 hold → hold B2
    keys = c.turn_inputs(b, 1, accepted)
    assert keys == ["1", "6", "B1", "2", "2", "B2", ""]
    assert c.turn_inputs(b, 5, [Order(unit_id="plt-A3", task="hold", target="B2")]) == [""]   # 已符合風格就不推翻


def test_sim_commander_plays_whole_battle_and_logs_overrides(tmp_path):
    c = SimCommander.from_file(SAMPLES / "commander_steady.json")
    board = load_board(SAMPLES / "board_start.json"); enemy = load_script(SAMPLES / "enemy_script.json")
    gw = FakeGateway([ChiefOrders(assessment="t1", orders=[{"unit_id": "plt-A1", "task": "seize", "target": "C3"},
                                                           {"unit_id": "plt-A3", "task": "seize", "target": "D4"}])],
                     chats=["學到了。"], parsed=[{"summary": "穩紮穩打", "add": [{"section": "profile", "text": "Steady commander"}], "remove": []}])
    doc = tmp_path / "doctrine.md"; doc.write_text("# D\n\n## Commander profile\n- ?\n", encoding="utf-8")
    out = open(tmp_path / "o.txt", "w", encoding="utf-8")
    res = run_play(gw, board, enemy, doctrine="d", out_dir=tmp_path / "b", console=Console(file=out, width=120), commander=c, doctrine_path=doc)
    out.close()
    text = (tmp_path / "o.txt").read_text(encoding="utf-8")
    assert res.overrides == 2 and len(c.log) == 2 and res.battle.turns_played == 10
    assert "推翻率：2/2" in text and "準則已更新" in text                       # 模擬總司令也走完討論與採納
    assert "- Steady commander" in doc.read_text(encoding="utf-8")
