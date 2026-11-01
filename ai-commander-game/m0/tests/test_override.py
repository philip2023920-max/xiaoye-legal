"""施工單 05 驗收：總司令推翻與接管。後果判定期望值來自 docs/10-sim-rules.md §9（含手算例）。"""
from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from chief.board import load_board
from chief.gateway import FakeGateway
from chief.orders import ChiefOrders
from chief.override import OverrideRecord, judge_outcome, player_order_problem
from chief.play import run_play
from chief.sim import Order, load_script

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def scripted_inputs(seq):
    it = iter(seq)
    return lambda prompt="": next(it, "")


def rec(unit="plt-A3", task="hold", target="B1", strength=0.80, turn=3):
    return OverrideRecord(turn=turn, unit_id=unit, ai_order=None, player_order={"unit_id": unit, "task": task, "target": target}, snapshot_ref="x", strength_at=strength)


def test_judge_hand_example_good():
    b = load_board(SAMPLES / "board_t0.json")        # plt-A3 0.80 @B1，B1 我方
    assert judge_outcome(b, rec(), owner_before="us") == "👍"


def test_judge_bad_when_routed_or_target_lost():
    b = load_board(SAMPLES / "board_t0.json")
    b.unit("plt-A3").state = "routed"
    assert judge_outcome(b, rec(), owner_before="us") == "👎"
    b2 = load_board(SAMPLES / "board_t0.json")
    b2.map.sectors["B1"].owner = "enemy"
    assert judge_outcome(b2, rec(), owner_before="us") == "👎"


def test_judge_neutral_when_strength_dropped():
    b = load_board(SAMPLES / "board_t0.json")
    b.unit("plt-A3").strength = 0.70                   # 掉 0.10 ≥ 0.05，B1 仍我方 → ➖
    assert judge_outcome(b, rec(), owner_before="us") == "➖"


def test_player_order_checks():
    b = load_board(SAMPLES / "board_t0.json")
    assert player_order_problem(b, Order(unit_id="plt-A3", task="hold", target="B2")) is None
    assert "分區" in player_order_problem(b, Order(unit_id="plt-A3", task="seize", target="Z9"))
    assert "不存在" in player_order_problem(b, Order(unit_id="nope", task="hold", target="B2"))


def run_interactive(tmp_path, scripted_orders, inputs):
    board = load_board(SAMPLES / "board_start.json")
    enemy = load_script(SAMPLES / "enemy_script.json")
    gw = FakeGateway(scripted_orders)
    out = open(tmp_path / "out.txt", "w", encoding="utf-8")
    res = run_play(gw, board, enemy, doctrine="t", out_dir=tmp_path / "b", console=Console(file=out, width=120),
                   auto=False, input_fn=scripted_inputs(inputs))
    out.close()
    return res, gw, (tmp_path / "out.txt").read_text(encoding="utf-8")


def test_override_marks_unit_player_and_blocks_chief_next_turn(tmp_path):
    turn1 = ChiefOrders(assessment="t1", orders=[{"unit_id": "plt-A1", "task": "seize", "target": "C3"}, {"unit_id": "plt-A3", "task": "seize", "target": "C3"}])
    turn2 = ChiefOrders(assessment="t2", orders=[{"unit_id": "plt-A3", "task": "seize", "target": "C3"}])   # 對直轄單位下令 → V2
    inputs = ["2", "2", "B2", ""] + [""] * 20          # 第 1 回合：改第 2 條（plt-A3）→ hold B2 → 採納；之後都 Enter
    res, gw, out = run_interactive(tmp_path, [turn1, turn2], inputs)
    b1 = json.loads((tmp_path / "b" / "t1.json").read_text(encoding="utf-8"))
    a3 = next(u for u in b1["orbat"] if u["id"] == "plt-A3")
    assert a3["controlled_by"] == "player" and a3["task"] == {"type": "hold", "target": "B2"}
    assert res.overrides == 1 and res.turns[1]["rejected"][0].startswith("V2 plt-A3")
    recs = [json.loads(l) for l in (tmp_path / "b" / "overrides.jsonl").read_text(encoding="utf-8").splitlines()]
    assert recs[0]["ai_order"]["task"] == "seize" and recs[0]["player_order"]["target"] == "B2" and recs[0]["turn"] == 1
    assert recs[0]["outcome"] in ("👍", "👎", "➖") and recs[0]["judged_turn"] == 2   # t+1 回合結束判定
    assert Path(recs[0]["snapshot_ref"]).exists()                                     # 指向開局快照 t0.json
    assert "推翻率：1/2" in out and "推翻後果：t1 plt-A3" in out                       # 第 1 回合參謀長放行 2 條，推翻 1


def test_take_over_and_release(tmp_path):
    inputs = ["+plt-A2", "hold", "A2", "", "-plt-A2", ""] + [""] * 20
    res, gw, out = run_interactive(tmp_path, [], inputs)
    b1 = json.loads((tmp_path / "b" / "t1.json").read_text(encoding="utf-8"))
    assert next(u for u in b1["orbat"] if u["id"] == "plt-A2")["controlled_by"] == "player"
    b2 = json.loads((tmp_path / "b" / "t2.json").read_text(encoding="utf-8"))
    assert next(u for u in b2["orbat"] if u["id"] == "plt-A2")["controlled_by"] == "ai"
    assert res.overrides == 1


def test_take_over_company_marks_platoons_and_blocks_chief(tmp_path):
    turn2 = ChiefOrders(assessment="t2", orders=[{"unit_id": "plt-A1", "task": "seize", "target": "C3"}])
    inputs = ["+co-A", "hold", "B1", ""] + [""] * 20
    res, gw, out = run_interactive(tmp_path, [ChiefOrders(assessment="t1", orders=[]), turn2], inputs)
    b1 = json.loads((tmp_path / "b" / "t1.json").read_text(encoding="utf-8"))
    ctrl = {u["id"]: u["controlled_by"] for u in b1["orbat"]}
    assert ctrl == {"co-A": "player", "plt-A1": "player", "plt-A2": "player", "plt-A3": "player"}
    tasks = {u["id"]: u["task"] for u in b1["orbat"]}
    assert tasks["plt-A1"] == {"type": "hold", "target": "B1"}        # 玩家的連令拆給自己直轄的排
    assert res.turns[1]["rejected"][0].startswith("V2 plt-A1")


def test_hostile_or_odd_input_does_not_crash(tmp_path):
    inputs = ["+plt-A3", "hold", "[/red]", "+[/]", "²", "-plt-A1", "3", ""] + [""] * 20
    res, gw, out = run_interactive(tmp_path, [], inputs)
    assert res.battle.turns_played >= 1 and "不是分區 id" in out and "本來就由參謀長指揮" in out


def test_eof_on_input_quits_cleanly(tmp_path):
    def boom(prompt=""):
        raise EOFError
    board = load_board(SAMPLES / "board_start.json")
    enemy = load_script(SAMPLES / "enemy_script.json")
    out = open(tmp_path / "o.txt", "w", encoding="utf-8")
    res = run_play(FakeGateway([]), board, enemy, doctrine="t", out_dir=tmp_path / "e", console=Console(file=out, width=120), auto=False, input_fn=boom)
    out.close()
    assert res.battle.end_reason == "quit" and "推翻率" in (tmp_path / "o.txt").read_text(encoding="utf-8")


def test_judge_boundary_is_strict():
    b = load_board(SAMPLES / "board_t0.json")
    b.unit("plt-A3").strength = 0.80
    assert judge_outcome(b, rec(strength=0.85), owner_before="us") == "➖"      # 掉 0.05 不算 < 0.05


def test_aar_flow_adopts_doctrine_and_next_game_quotes_it(tmp_path):
    doc = tmp_path / "doctrine.md"
    doc.write_text((Path(__file__).resolve().parent.parent / "harness" / "default" / "doctrine.md").read_text(encoding="utf-8"), encoding="utf-8")
    board = load_board(SAMPLES / "board_start.json")
    enemy = load_script(SAMPLES / "enemy_script.json")
    gw = FakeGateway([], chats=["我學到您偏好固守。", "因為城鎮價值最高。"],
                     parsed=[{"summary": "您偏好先守再攻", "add": [{"section": "profile", "text": "Prefers holding before attacking"}], "remove": []}])
    inputs = ["q", "", "1", "", ""]         # q 結束戰鬥 → Enter 討論 → 快速回覆 1 → Enter 結束討論 → Enter 採納
    out = open(tmp_path / "o.txt", "w", encoding="utf-8")
    res = run_play(gw, board, enemy, doctrine=doc.read_text(encoding="utf-8"), out_dir=tmp_path / "b", console=Console(file=out, width=120),
                   auto=False, input_fn=scripted_inputs(inputs), doctrine_path=doc)
    out.close()
    text = (tmp_path / "o.txt").read_text(encoding="utf-8")
    assert "戰報卡" in text and "參謀長：「我學到您偏好固守。」" in text and "準則已更新：新增 1、刪除 0" in text
    assert "- Prefers holding before attacking" in doc.read_text(encoding="utf-8") and doc.with_suffix(".prev.md").exists()
    assert (tmp_path / "b" / "aar.json").exists() and res.card is not None and res.card.chief_line
    # 下一場開局引用
    out2 = open(tmp_path / "o2.txt", "w", encoding="utf-8")
    run_play(FakeGateway([]), load_board(SAMPLES / "board_start.json"), enemy, doctrine="d", out_dir=tmp_path / "c", console=Console(file=out2, width=120),
             auto=False, input_fn=scripted_inputs(["q", "s"]), doctrine_path=doc)
    out2.close()
    assert "上次您採納了「" in (tmp_path / "o2.txt").read_text(encoding="utf-8")


def test_aar_skip_and_decline(tmp_path):
    doc = tmp_path / "doctrine.md"; doc.write_text("# D\n\n## Commander profile\n- x\n", encoding="utf-8")
    board = load_board(SAMPLES / "board_start.json"); enemy = load_script(SAMPLES / "enemy_script.json")
    gw = FakeGateway([], parsed=[{"summary": "s", "add": [{"section": "tactic", "text": "t"}], "remove": []}])
    out = open(tmp_path / "o.txt", "w", encoding="utf-8")
    run_play(gw, board, enemy, doctrine="d", out_dir=tmp_path / "b", console=Console(file=out, width=120), auto=False,
             input_fn=scripted_inputs(["q", "a", "n"]), doctrine_path=doc)      # a＝直接採納提案 → n 不採納
    out.close()
    assert "未採納" in (tmp_path / "o.txt").read_text(encoding="utf-8") and "- t" not in doc.read_text(encoding="utf-8")


def test_quit_ends_battle_early(tmp_path):
    res, gw, out = run_interactive(tmp_path, [], ["", "q"])
    assert res.battle.turns_played == 1 and res.battle.end_reason == "quit"
