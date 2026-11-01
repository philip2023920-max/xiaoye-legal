"""施工單 02 驗收測試。期望值來源：docs/10-sim-rules.md（§2 每回合 1 格、§3 任務行為、§4 手算範例、
§5 門檻、§6 歸屬、§7 結束條件）。不照程式再算一遍。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chief.board import Board, MapGrid, Sector, Task, Unit, load_board
from chief.formation_ai import decide_move
from chief.grid import distance, neighbors
from chief.sim import Battle, Order, Script, load_script, resolve_sector_combat

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def open_grid(n: int = 5) -> MapGrid:
    sectors = {}
    for r in range(1, n + 1):
        for c in range(n):
            sid = f"{'ABCDE'[c]}{r}"
            sectors[sid] = Sector(id=sid, terrain="open", cover=0.2)
    return MapGrid(cols=n, rows=n, sectors=sectors)


def plt(uid: str, sector: str, task: Task | None = None, typ: str = "infantry", strength: float = 1.0, state: str = "idle") -> Unit:
    return Unit(id=uid, name=uid, echelon="platoon", type=typ, sector=sector, task=task, strength=strength, state=state)


def mini_board(units: list[Unit], battle_id: str = "mini") -> Board:
    return Board(battle_id=battle_id, t=0, map=open_grid(), orbat=units, objectives=[])


# ---- §4 手算範例 ----
def test_damage_hand_example():
    us = [plt("plt-A1", "C3", strength=0.90)]
    en = [plt("e-plt-12", "C3", typ="mg", strength=0.60)]
    dmg = resolve_sector_combat(us, en, cover=0.6, rng=None)
    assert dmg["e-plt-12"] == pytest.approx(0.090)   # 0.90×1.0×0.4×0.25
    assert dmg["plt-A1"] == pytest.approx(0.078)     # 0.60×1.3×0.4×0.25
    assert 0.60 - dmg["e-plt-12"] == pytest.approx(0.510)
    assert 0.90 - dmg["plt-A1"] == pytest.approx(0.822)


# ---- §3 六種任務 ----
def test_seize_moves_one_sector_toward_target():
    g = open_grid()
    u = plt("u", "A1", Task(type="seize", target="C3"))
    dest = decide_move(u, g, [u], ["A1"], {"u": u})
    assert dest is not None and distance(dest, "C3") == distance("A1", "C3") - 1


def test_hold_at_target_stays():
    g = open_grid()
    u = plt("u", "B2", Task(type="hold", target="B2"))
    assert decide_move(u, g, [u], ["B2"], {"u": u}) is None


def test_withdraw_moves_and_does_not_fire():
    us = [plt("u", "C3", Task(type="withdraw", target="A1"))]
    en = [plt("e", "C3")]
    dmg = resolve_sector_combat(us, en, cover=0.2, rng=None)
    assert "e" not in dmg                               # 撤退不開火
    assert dmg["u"] == pytest.approx(0.2)               # 1.0×1.0×0.8×0.25
    g = open_grid()
    dest = decide_move(us[0], g, us, ["A1"], {"u": us[0]})
    assert dest is not None and distance(dest, "A1") == distance("C3", "A1") - 1


def test_support_stops_adjacent_to_buddy():
    g = open_grid()
    buddy = plt("b", "C3", Task(type="hold", target="C3"))
    u = plt("u", "A1", Task(type="support", target="b"))
    by_id = {"u": u, "b": buddy}
    for _ in range(6):
        dest = decide_move(u, g, [u, buddy], ["A1"], by_id)
        if dest is None:
            break
        u.sector = dest
    assert u.sector in neighbors(g, "C3")
    assert decide_move(u, g, [u, buddy], ["A1"], by_id) is None


def test_reserve_reaches_target_and_idles(tmp_path):
    b = mini_board([plt("u", "A1", Task(type="reserve", target="A3"))])
    battle = Battle(b, enemy_units=[], out_dir=tmp_path)
    battle.step([], [])
    battle.step([], [])
    u = battle.board.unit("u")
    assert u.sector == "A3" and u.state == "idle"


def test_flank_enters_via_far_side_neighbor():
    g = open_grid()
    main = plt("main", "A3", strength=1.0)              # 主力在西側
    u = plt("u", "C1", Task(type="flank", target="C3"), strength=0.5)
    by_id = {"main": main, "u": u}
    first = decide_move(u, g, [u, main], ["A3"], by_id)
    assert first == "C2"                                # §3：離主力最遠的鄰格，同距依上、左、右、下取第一個
    u.sector = first
    assert decide_move(u, g, [u, main], ["A3"], by_id) == "C3"


def test_flank_detour_does_not_pass_through_target():
    g = open_grid()
    main = plt("main", "A3", strength=1.0)
    u = plt("u", "B3", Task(type="flank", target="C3"), strength=0.5)   # 側翼點是 D3，繞路不可穿過 C3
    by_id = {"main": main, "u": u}
    assert decide_move(u, g, [u, main], ["A3"], by_id) != "C3"


# ---- 審查員補測（手算自 §4～§6）----
def test_armor_takes_reduced_damage_and_hits_harder():
    us = [plt("u", "C3", typ="infantry")]
    en = [plt("e", "C3", typ="armor")]
    dmg = resolve_sector_combat(us, en, cover=0.6, rng=None)
    assert dmg["e"] == pytest.approx(0.060)   # 1.0×1.0×0.4×0.25×0.6
    assert dmg["u"] == pytest.approx(0.150)   # 1.0×1.5×0.4×0.25


def test_damage_split_by_strength_and_thresholds(tmp_path):
    us = [plt("u1", "C3", Task(type="hold", target="C3")), plt("u2", "C3", Task(type="hold", target="C3"))]
    b = mini_board(us); b.map.sectors["C3"].cover = 0.0
    en = [plt("e1", "C3", Task(type="hold", target="C3"), strength=0.60), plt("e2", "C3", Task(type="hold", target="C3"), strength=0.20)]
    battle = Battle(b, enemy_units=en, out_dir=tmp_path)
    rep = battle.step([], [])
    e1 = next(u for u in battle.enemy if u.id == "e1"); e2 = next(u for u in battle.enemy if u.id == "e2")
    assert e1.strength == pytest.approx(0.225, abs=1e-4) and e1.state == "routed"   # 0.5×0.75 = 0.375
    assert e2.strength == pytest.approx(0.075, abs=1e-4) and e2.state == "routed"   # 0.5×0.25 = 0.125，未殲滅
    assert sum(1 for e in rep.events if e.kind == "routed") == 2


def test_destroyed_unit_logs_event_and_sector_changes_hands(tmp_path):
    us = [plt(f"u{i}", "C3", Task(type="hold", target="C3")) for i in range(3)]
    b = mini_board(us); b.map.sectors["C3"].cover = 0.0; b.map.sectors["C3"].owner = "enemy"
    en = [plt("e", "C3", Task(type="hold", target="C3"), strength=0.10)]
    battle = Battle(b, enemy_units=en, out_dir=tmp_path)
    rep = battle.step([], [])
    assert battle.enemy[0].state == "destroyed"                     # 受 0.75 > 0.10
    assert any(e.kind == "destroyed" for e in rep.events)
    assert battle.board.map.sectors["C3"].owner == "us" and any(e.kind == "seized" for e in rep.events)


def test_contested_sector_keeps_owner(tmp_path):
    b = mini_board([plt("u", "B2", Task(type="hold", target="B2"))])
    b.map.sectors["B2"].owner = "us"; b.map.sectors["B2"].cover = 0.4
    en = [plt("e", "B2", Task(type="seize", target="B2"))]
    battle = Battle(b, enemy_units=en, out_dir=tmp_path)
    rep = battle.step([], [])
    s = battle.board.map.sectors["B2"]
    assert s.owner == "us" and s.contested is True
    assert not any(e.kind == "seized" for e in rep.events)
    assert battle.board.unit("u").strength == pytest.approx(0.85)   # 1.0×1.0×0.6×0.25 = 0.15


def test_engine_rejects_bad_target_instead_of_corrupting_snapshot(tmp_path):
    b = mini_board([plt("u", "A1")])
    battle = Battle(b, enemy_units=[], out_dir=tmp_path)
    rep = battle.step([Order(unit_id="u", task="flank", target="z9")], [])
    assert any("退回" in e.text for e in rep.events) and battle.board.unit("u").task is None
    from chief.board import load_board as lb
    assert lb(tmp_path / "t1.json").t == 1                            # 快照仍可重讀


def test_company_order_does_not_touch_player_platoon(tmp_path):
    board = load_board(SAMPLES / "board_start.json")
    board.unit("plt-A3").controlled_by = "player"
    board.unit("plt-A3").task = Task(type="hold", target="B1")
    battle = Battle(board, enemy_units=[], out_dir=tmp_path)
    battle.step([Order(unit_id="co-A", task="seize", target="C3")], [])
    assert battle.board.unit("plt-A3").task.type == "hold" and battle.board.unit("plt-A3").task.target == "B1"
    assert battle.board.unit("plt-A1").task.type == "seize"


def test_platoon_explicit_order_beats_company_order_same_turn(tmp_path):
    board = load_board(SAMPLES / "board_start.json")
    battle = Battle(board, enemy_units=[], out_dir=tmp_path)
    battle.step([Order(unit_id="plt-A3", task="hold", target="B2"), Order(unit_id="co-A", task="seize", target="C3")], [])
    assert battle.board.unit("plt-A3").task.type == "hold" and battle.board.unit("plt-A3").task.target == "B2"
    assert battle.board.unit("plt-A1").task.type == "seize" and battle.board.unit("plt-A2").task.type == "seize"


def test_routed_unit_in_own_sector_stays_put():
    g = open_grid()
    u = plt("u", "A1", state="routed", strength=0.2)
    assert decide_move(u, g, [u], ["A1", "A2"], {"u": u}) is None


def test_engaged_state_resets_when_fighting_stops(tmp_path):
    b = mini_board([plt("u", "C3", Task(type="hold", target="C3"))]); b.map.sectors["C3"].cover = 0.0
    en = [plt("e", "C3", Task(type="hold", target="C3"), strength=0.10)]
    battle = Battle(b, enemy_units=en, out_dir=tmp_path)
    battle.step([], [])                                             # 敵被殲滅
    assert battle.board.unit("u").state == "engaged"
    battle.step([], [])
    assert battle.board.unit("u").state == "idle"


def test_cli_sim_runs(tmp_path, capsys):
    from chief.cli import main
    rc = main(["sim", "--orders", str(SAMPLES / "orders_scripted.json"), "--seed", "7", "--quiet", "--out", str(tmp_path / "cli")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "結果：" in out and (tmp_path / "cli" / "t1.json").exists()


# ---- §6 歸屬、§5 門檻、§7 結束 ----
def test_alone_in_sector_takes_ownership_and_logs_seized(tmp_path):
    b = mini_board([plt("u", "A1", Task(type="seize", target="A2"))])
    battle = Battle(b, enemy_units=[], out_dir=tmp_path)
    rep = battle.step([], [])
    assert battle.board.map.sectors["A2"].owner == "us"
    assert any(e.kind == "seized" and e.sector == "A2" for e in rep.events)


def test_strength_below_30_percent_ends_battle_with_rout_event(tmp_path):
    us = [plt(f"u{i}", "C3", Task(type="hold", target="C3")) for i in range(3)]   # 3×1.0 步兵
    b = mini_board(us)
    b.map.sectors["C3"].cover = 0.0
    en = [plt("e1", "C3", Task(type="hold", target="C3"), strength=0.5),
          plt("e2", "C3", Task(type="hold", target="C3"), strength=0.5)]
    battle = Battle(b, enemy_units=en, out_dir=tmp_path)
    rep = battle.step([], [])
    # 我方火力 3.0×1.0×1.0×0.25 = 0.75，均分 0.375 → 敵各 0.125 → 潰散；總戰力 0.25 < 1.0×30%
    assert battle.finished() and battle.end_reason == "strength"
    assert any(e.kind == "routed" for e in rep.events)
    assert battle.result().winner == "us"


def test_company_strength_is_mean_of_platoons(tmp_path):
    b = load_board(SAMPLES / "board_t0.json")        # 子排 0.90、0.75、0.80
    battle = Battle(b, enemy_units=[], out_dir=tmp_path)
    battle.step([], [])
    assert battle.board.unit("co-A").strength == pytest.approx((0.90 + 0.75 + 0.80) / 3, abs=1e-3)


# ---- 整場劇本 ----
def run_scripted(tmp_path: Path, seed: int | None = 7):
    board = load_board(SAMPLES / "board_start.json")
    friendly = load_script(SAMPLES / "orders_scripted.json")
    enemy = load_script(SAMPLES / "enemy_script.json")
    battle = Battle(board, enemy.units, seed=seed, out_dir=tmp_path / f"run-{seed}")
    return battle.run(friendly, enemy)


def test_scripted_battle_runs_to_a_result(tmp_path):
    r = run_scripted(tmp_path)
    assert 1 <= r.turns_played <= 10
    assert r.winner in ("us", "enemy", "draw")
    assert r.score_us + r.score_enemy <= 11            # O1+O2+O3 = 3+5+3
    assert "結果" in r.summary()


def test_same_seed_same_result(tmp_path):
    a = run_scripted(tmp_path / "a", seed=7)
    b = run_scripted(tmp_path / "b", seed=7)
    assert (a.turns_played, a.winner, a.score_us, a.score_enemy, a.strength_us, a.strength_enemy) == \
           (b.turns_played, b.winner, b.score_us, b.score_enemy, b.strength_us, b.strength_enemy)


def test_snapshot_per_turn_is_written(tmp_path):
    r = run_scripted(tmp_path)
    files = sorted((tmp_path / "run-7").glob("t*.json"))
    assert len(files) == r.turns_played
    first = json.loads(files[0].read_text(encoding="utf-8"))
    assert first["t"] == 1 and first["battle_id"] == "hill-town-start"
