"""施工單 08：戰鬥模型 v1 透過引擎驗證。期望值全部來自 docs/10-sim-rules.md §2 v1、§4 v1、§13（手算），不照程式再算。"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from chief.board import Board, BoardError, MapGrid, Sector, Task, Unit, estimate_tokens, load_board
from chief.deploy import apply_plan, deployment_sectors, parse_suggestion, plan_from_list, plan_from_template, plan_lines
from chief.rules import load_rules
from chief.sim import Battle, Order, Script, load_script

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
RULES = load_rules()


def grid(n: int = 5, terrain: str = "open") -> MapGrid:
    sectors = {}
    for r in range(1, n + 1):
        for c in range(n):
            sid = f"{'ABCDE'[c]}{r}"
            sectors[sid] = Sector(id=sid, terrain=terrain, cover=RULES.terrain[terrain].cover)
    return MapGrid(cols=n, rows=n, sectors=sectors)


def plt(uid: str, sector: str, typ: str = "infantry", task: Task | None = None, strength: float = 1.0) -> Unit:
    return Unit(id=uid, name=uid, echelon="platoon", type=typ, sector=sector, task=task, strength=strength)


def board(units: list[Unit], weather: str = "clear", time_of_day: str = "day", terrain: str = "open") -> Board:
    return Board(battle_id="v1", t=0, map=grid(terrain=terrain), orbat=units, objectives=[], weather=weather, time_of_day=time_of_day)


def hold(sector: str) -> Task:
    return Task(type="hold", target=sector)


# ---- §4 v1 三個手算例 ----
def test_hand_example_1_infantry_vs_tank_rain_open(tmp_path):
    """雨天平地日間：步兵對戰車 0.1044；戰車對步兵 0.216。"""
    b = board([plt("inf", "C3", "infantry", hold("C3"))], weather="rain")
    battle = Battle(b, [plt("tank", "C3", "tank", hold("C3"))], out_dir=tmp_path)
    rep = battle.step([], [])
    assert rep.damage["tank"] == pytest.approx(0.1044, abs=1e-4)
    assert rep.damage["inf"] == pytest.approx(0.216, abs=1e-4)
    assert battle.enemy[0].strength == pytest.approx(0.8956, abs=1e-4) and battle.board.unit("inf").strength == pytest.approx(0.784, abs=1e-4)


def test_hand_example_2_mg_in_fog_night_town(tmp_path):
    """霧夜城鎮：掩蔽 0.6+0.1+0.2 → 上限 0.8；火力倍率 0.7×0.6=0.42。機槍對步兵 0.0273；步兵對機槍 0.021。"""
    b = board([plt("mg", "C3", "mg", hold("C3"))], weather="fog", time_of_day="night", terrain="town")
    battle = Battle(b, [plt("inf", "C3", "infantry", hold("C3"))], out_dir=tmp_path)
    rep = battle.step([], [])
    assert rep.damage["inf"] == pytest.approx(0.0273, abs=1e-4)
    assert rep.damage["mg"] == pytest.approx(0.021, abs=1e-4)


def test_hand_example_3_mortar_indirect_fire_from_adjacent_sector(tmp_path):
    """晴天平地：C3 步兵對步兵，B3 迫砲間接支援。敵受 (1.0+0.9)×0.8×0.25=0.38；我步兵受 0.2；迫砲不在格內不被打。"""
    b = board([plt("inf", "C3", "infantry", hold("C3")), plt("mortar", "B3", "mortar", hold("B3"))])
    battle = Battle(b, [plt("e", "C3", "infantry", hold("C3"))], out_dir=tmp_path)
    rep = battle.step([], [])
    assert rep.damage["e"] == pytest.approx(0.38, abs=1e-4)
    assert rep.damage["inf"] == pytest.approx(0.20, abs=1e-4)
    assert "mortar" not in rep.damage
    assert battle.board.unit("mortar").state != "engaged"          # 支援射擊不算交戰


def test_mortar_alone_next_to_enemy_does_not_fire(tmp_path):
    """§4 v1：間接射擊需要本方非潰散單位在該格交戰當觀測；只有迫砲在鄰格不會開火。"""
    b = board([plt("mortar", "B3", "mortar", hold("B3"))])
    battle = Battle(b, [plt("e", "C3", "infantry", hold("C3"))], out_dir=tmp_path)
    rep = battle.step([], [])
    assert rep.damage == {}


def test_at_platoon_vs_tank_hand_value(tmp_path):
    """反戰車對戰車混合火力 0.3×0.4+1.5×0.6=1.02；晴天平地 → 1.02×0.8×0.25=0.204。戰車對反戰車（armor 0.1）：1.2×0.9+1.0×0.1=1.18 → 0.236。"""
    b = board([plt("at", "C3", "at", hold("C3"))])
    battle = Battle(b, [plt("tank", "C3", "tank", hold("C3"))], out_dir=tmp_path)
    rep = battle.step([], [])
    assert rep.damage["tank"] == pytest.approx(0.204, abs=1e-4)
    assert rep.damage["at"] == pytest.approx(0.236, abs=1e-4)


def test_engineer_holding_adds_cover_for_its_side_only(tmp_path):
    """§4 v1：工兵固守的分區，本方掩蔽 +0.1（平地 0.2 → 0.3）；敵方不加。敵受 (1.0+0.8)×0.8×0.25=0.36 均分；我方各受 1.0×0.7×0.25×share。"""
    b = board([plt("inf", "C3", "infantry", hold("C3")), plt("eng", "C3", "engineer", hold("C3"))])
    battle = Battle(b, [plt("e", "C3", "infantry", hold("C3"))], out_dir=tmp_path)
    rep = battle.step([], [])
    assert rep.damage["e"] == pytest.approx(0.36, abs=1e-4)
    assert rep.damage["inf"] == pytest.approx(0.0875, abs=1e-4)   # 1.0×1.0×0.5×0.7×0.25
    assert rep.damage["eng"] == pytest.approx(0.0875, abs=1e-4)


# ---- §2 v1 移動：機動力、速度、通行 ----
def test_rain_halves_tank_mobility_moves_only_on_even_turns(tmp_path):
    b = board([plt("tank", "A1", "tank", Task(type="seize", target="A5")), plt("inf", "B1", "infantry", Task(type="seize", target="B5"))], weather="rain")
    battle = Battle(b, [], out_dir=tmp_path)
    battle.step([], [])                                   # t1 奇數：戰車不動，步兵動
    assert battle.board.unit("tank").sector == "A1" and battle.board.unit("inf").sector == "B2"
    battle.step([], [])                                   # t2 偶數：兩個都動
    assert battle.board.unit("tank").sector == "A2" and battle.board.unit("inf").sector == "B3"


def test_snow_halves_everyone(tmp_path):
    b = board([plt("inf", "B1", "infantry", Task(type="seize", target="B5"))], weather="snow")
    battle = Battle(b, [], out_dir=tmp_path)
    battle.step([], []); assert battle.board.unit("inf").sector == "B1"
    battle.step([], []); assert battle.board.unit("inf").sector == "B2"


def test_recon_moves_two_sectors_per_turn(tmp_path):
    b = board([plt("rc", "A1", "recon", Task(type="seize", target="A5"))])
    battle = Battle(b, [], out_dir=tmp_path)
    battle.step([], [])
    assert battle.board.unit("rc").sector == "A3"


def test_tank_cannot_enter_forest_and_detours(tmp_path):
    """A1 → A3 的最短路經 A2；A2 是森林 → 戰車繞 B1（或原地若無路）。步兵不受限。"""
    g = grid()
    g.sectors["A2"].terrain = "forest"; g.sectors["A2"].cover = 0.5
    b = Board(battle_id="v1", t=0, map=g, orbat=[plt("tank", "A1", "tank", Task(type="seize", target="A3")), plt("inf", "E1", "infantry", Task(type="seize", target="A2"))], objectives=[])
    battle = Battle(b, [], out_dir=tmp_path)
    battle.step([], [])
    assert battle.board.unit("tank").sector == "B1" and battle.board.unit("inf").sector == "D1"   # 步兵照常走（速度 1）
    for _ in range(4):
        battle.step([], [])
    assert battle.board.unit("tank").sector == "A3"         # B1 → B2 → B3 → A3（4 步，繞過森林 A2）
    assert battle.board.unit("inf").sector == "A2"          # 步兵可進森林（E1 → A2 共 5 步）


def test_tank_crosses_river_only_with_engineer(tmp_path):
    g = grid()
    g.sectors["A2"].terrain = "river"; g.sectors["A2"].cover = 0.1
    for c in "BCDE":                                       # 其他路都堵成河，逼它走 A2
        g.sectors[f"{c}2"].terrain = "river"; g.sectors[f"{c}2"].cover = 0.1
    units = [plt("tank", "A1", "tank", Task(type="seize", target="A3"))]
    battle = Battle(Board(battle_id="v1", t=0, map=g, orbat=units, objectives=[]), [], out_dir=tmp_path)
    battle.step([], []); battle.step([], [])
    assert battle.board.unit("tank").sector == "A1"        # 沒工兵過不了河
    units2 = [plt("tank", "A1", "tank", Task(type="seize", target="A3")), plt("eng", "A2", "engineer", hold("A2"))]
    battle2 = Battle(Board(battle_id="v1", t=0, map=g, orbat=units2, objectives=[]), [], out_dir=tmp_path / "2")
    battle2.step([], [])
    assert battle2.board.unit("tank").sector == "A2"       # 工兵在河上 → 可過


# ---- §2 v1 視距 ----
def test_sight_radius_infantry_recon_night_fog(tmp_path):
    def visible(b: Board) -> set[str]:
        return Battle(b, [], out_dir=tmp_path / b.weather / b.time_of_day).visible_sectors()
    inf = board([plt("inf", "C3", "infantry")])
    assert visible(inf) == {"C3", "B3", "D3", "C2", "C4"}                      # 視距 1
    rc = board([plt("rc", "C3", "recon")])
    assert len(visible(rc)) == 13                                               # 曼哈頓距離 ≤ 2
    assert visible(board([plt("inf", "C3", "infantry")], time_of_day="night")) == {"C3"}   # 夜間 −1
    assert visible(board([plt("rc", "C3", "recon")], time_of_day="night")) == {"C3", "B3", "D3", "C2", "C4"}
    assert visible(board([plt("rc", "C3", "recon")], weather="fog")) == {"C3"}             # 霧 −9 → 0


# ---- 天氣／時段依劇本變化 ----
def test_weather_change_events_and_effect(tmp_path):
    enemy = Script(units=[plt("e", "C3", "infantry", hold("C3"))], weather_changes={"2": "rain"}, time_changes={"3": "night"})
    friendly = Script(orders={"1": [Order(unit_id="inf", task="hold", target="C3")]})
    b = board([plt("inf", "C3", "infantry", hold("C3"))])
    battle = Battle(b, enemy.units, out_dir=tmp_path)
    reports = []
    battle.run(friendly, enemy, on_turn=lambda bt, r: reports.append(r))
    assert any(e.kind == "weather" and e.text == "天氣轉雨" for e in reports[1].events)
    assert any(e.kind == "weather" and e.text == "進入夜間" for e in reports[2].events)
    assert reports[0].damage["e"] == pytest.approx(0.2, abs=1e-4)             # t1 晴日：1.0×1.0×0.8×0.25（雙方都剩 0.8）
    assert reports[1].damage["e"] == pytest.approx(0.144, abs=1e-4)           # t2 雨：0.8×1.0×0.8×0.25×0.9（雙方都剩 0.656）
    assert reports[2].damage["e"] == pytest.approx(0.0531, abs=1e-4)          # t3 雨夜：掩蔽 0.2+0.2=0.4、倍率 0.9×0.6=0.54 → 0.656×0.6×0.25×0.54
    assert battle.board.weather == "rain" and battle.board.time_of_day == "night"
    assert any(e.kind == "weather" for e in battle.board.events)              # 事件流留底


def test_enemy_script_v1_loads_and_runs(tmp_path):
    enemy = load_script(SAMPLES / "enemy_script_v1.json")
    assert {u.type for u in enemy.units} >= {"tank", "mortar", "at"} and enemy.weather_changes == {"3": "rain", "8": "fog"}
    b = load_board(SAMPLES / "board_start.json")
    rules = load_rules()
    b = apply_plan(b, plan_from_template(rules, "balanced"), rules)
    battle = Battle(b, enemy.units, seed=7, out_dir=tmp_path)
    r = battle.run(Script(), enemy)
    assert r.turns_played >= 3
    texts = [e.text for e in battle.board.events if e.kind == "weather"]
    assert texts[0] == "天氣轉雨" and "contact" in {e.kind for e in battle.board.events}


def test_ten_turns_resolve_under_one_second(tmp_path):
    enemy = load_script(SAMPLES / "enemy_script_v1.json")
    b = apply_plan(load_board(SAMPLES / "board_start.json"), plan_from_template(RULES, "balanced"), RULES)
    t0 = time.perf_counter()
    for i in range(3):
        Battle(b, enemy.units, out_dir=tmp_path / str(i)).run(Script(), enemy)
    assert (time.perf_counter() - t0) / 3 < 1.0


# ---- §13 部署 ----
def test_templates_and_custom_list_within_budget():
    p = plan_from_template(RULES, "armor")
    assert p.units == ["tank", "tank", "infantry", "infantry", "mg", "recon"] and p.cost == 94 and p.remaining == 6
    q = plan_from_list(RULES, ["infantry", " Armor", "mg"])
    assert q.units == ["infantry", "tank", "mg"] and q.cost == 47
    with pytest.raises(BoardError, match="超過預算"):
        plan_from_list(RULES, ["tank"] * 5)                    # 125 > 100
    with pytest.raises(BoardError, match="不認識的兵種"):
        plan_from_list(RULES, ["cavalry"])
    with pytest.raises(BoardError, match="沒有範本"):
        plan_from_template(RULES, "blitz")


def test_apply_plan_places_units_on_own_sectors_objective_first():
    b = load_board(SAMPLES / "board_start.json")
    assert deployment_sectors(b) == ["B2", "A2", "B1", "A1"]           # 有目標的 B2 先；再依離最近非我方目標 C3 的距離（A2、B1 皆 3 格 → id 序）；A1 是 4 格
    nb = apply_plan(b, plan_from_template(RULES, "balanced"), RULES)
    leaves = [u for u in nb.orbat if u.parent == "co-A"]
    assert len(leaves) == 8 and [u.sector for u in leaves] == ["B2", "A2", "B1", "A1", "B2", "A2", "B1", "A1"]
    assert all(u.cost == RULES.unit(u.type).cost for u in leaves) and nb.unit("co-A").cost == 94
    assert leaves[0].name == "A1 步兵排" and leaves[3].type == "mg"
    assert estimate_tokens(nb.compact_json()) < 2000                   # PRD：壓縮快照 < 2K token
    assert len(b.orbat) == 4                                           # 原板不動


def test_apply_plan_without_own_sectors_fails_plainly():
    b = board([plt("inf", "C3")])
    with pytest.raises(BoardError, match="沒有 us 擁有的分區"):
        apply_plan(b, plan_from_template(RULES, "infantry"), RULES)


def test_plan_lines_and_suggestion_parsing():
    p = plan_from_template(RULES, "infantry")
    lines = plan_lines(p, RULES)
    assert lines[-1].startswith("範本：步兵固守（infantry）") and "92/100" in lines[-1]
    assert parse_suggestion("I'd go with the ARMOR template because the ground is dry.", RULES) == "armor"
    assert parse_suggestion("選均衡吧", RULES) is None


def test_cli_deploy_and_play_template(tmp_path, capsys):
    from chief.cli import main
    assert main(["deploy"]) == 0 and "balanced" in capsys.readouterr().out
    out = tmp_path / "deployed.json"
    assert main(["deploy", "--template", "armor", "--weather", "rain", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "94/100" in text and out.exists()
    saved = load_board(out)
    assert saved.weather == "rain" and sum(1 for u in saved.orbat if u.type == "tank") == 2
    assert main(["deploy", "--units", "tank,tank,tank,tank,tank"]) == 1
    assert "超過預算" in capsys.readouterr().err
    assert main(["deploy", "--suggest", "--provider", "fake"]) == 0
    assert "採「均衡」" in capsys.readouterr().out                                 # fake 回覆沒指名範本 → 均衡並說明
    assert main(["deploy", "--template", "armor", "--era", "bogus"]) == 1
    assert "找不到世代規則檔" in capsys.readouterr().err                           # 壞 era 是人話不是 traceback
    assert main(["sim", "--orders", str(SAMPLES / "orders_scripted.json"), "--template", "armor", "--era", "coldwar_early",
                 "--quiet", "--out", str(tmp_path / "sim")]) == 0
    assert load_board(tmp_path / "sim" / "t1.json").era == "coldwar_early"       # --era 沒搭 deploy 也要生效
    capsys.readouterr()
    rc = main(["play", "--provider", "fake", "--model", "fake/empty", "--auto", "--skip-aar", "--quiet", "--harness", "",
               "--template", "infantry", "--time", "night", "--enemy", str(SAMPLES / "enemy_script_v1.json"),
               "--ledger", "", "--out", str(tmp_path / "play")])
    assert rc == 0
    snap = json.loads((tmp_path / "play" / "t1.json").read_text(encoding="utf-8"))
    assert snap["time_of_day"] == "night" and sum(1 for u in snap["orbat"] if u["echelon"] == "platoon") == 8


# ---- 審查員補測（08 code-reviewer 軸）----
def test_unreachable_goal_stays_put(tmp_path):
    """§2：目標本身進不去（戰車 seize 森林）→ 原地不動。"""
    g = grid(); g.sectors["A2"].terrain = "forest"; g.sectors["A2"].cover = 0.5
    b = Board(battle_id="v1", t=0, map=g, orbat=[plt("tank", "A1", "tank", Task(type="seize", target="A2"))], objectives=[])
    battle = Battle(b, [], out_dir=tmp_path)
    battle.step([], [])
    assert battle.board.unit("tank").sector == "A1"


def test_mortar_withdrawing_or_routed_does_not_support(tmp_path):
    b = board([plt("inf", "C3", "infantry", hold("C3")), plt("m1", "B3", "mortar", Task(type="withdraw", target="A3")),
               plt("m2", "D3", "mortar", hold("D3"), strength=0.2)])
    b.orbat[2].state = "routed"
    battle = Battle(b, [plt("e", "C3", "infantry", hold("C3"))], out_dir=tmp_path)
    rep = battle.step([], [])
    assert rep.damage["e"] == pytest.approx(0.20, abs=1e-4)             # 只有步兵 1.0 開火


def test_mortar_fires_in_own_sector_and_adjacent(tmp_path):
    """迫砲在 B3 與敵 e2 交戰（直接），同時支援 C3（間接）。e1 受 (1.0+0.9)×0.8×0.25=0.38；e2 受 0.9×0.8×0.25=0.18；迫砲只被 e2 打 0.2。"""
    b = board([plt("inf", "C3", "infantry", hold("C3")), plt("mortar", "B3", "mortar", hold("B3"))])
    battle = Battle(b, [plt("e1", "C3", "infantry", hold("C3")), plt("e2", "B3", "infantry", hold("B3"))], out_dir=tmp_path)
    rep = battle.step([], [])
    assert rep.damage["e1"] == pytest.approx(0.38, abs=1e-4) and rep.damage["e2"] == pytest.approx(0.18, abs=1e-4)
    assert rep.damage["mortar"] == pytest.approx(0.20, abs=1e-4)


def test_routed_unit_retreats_one_sector_even_if_fast(tmp_path):
    g = grid(); g.sectors["A1"].owner = "us"
    rc = plt("rc", "E1", "recon", strength=0.2); rc.state = "routed"
    battle = Battle(Board(battle_id="v1", t=0, map=g, orbat=[rc], objectives=[]), [], out_dir=tmp_path)
    battle.step([], [])
    assert battle.board.unit("rc").sector == "D1"                        # §2：潰散每回合只退 1 格


def test_fast_unit_stops_when_entering_hostile_sector(tmp_path):
    b = board([plt("rc", "A3", "recon", Task(type="seize", target="C3"))])
    battle = Battle(b, [plt("e", "B3", "infantry", hold("B3"))], out_dir=tmp_path)
    rep = battle.step([], [])
    assert battle.board.unit("rc").sector == "B3" and "rc" in rep.damage   # 進敵格就停、交戰


def test_engineer_bonus_needs_hold_on_that_sector(tmp_path):
    b = board([plt("eng", "C3", "engineer", hold("A1"))])                 # 路過，不算固守 C3
    battle = Battle(b, [], out_dir=tmp_path)
    assert battle.cover_for("us", "C3") == pytest.approx(0.2)
    battle.board.unit("eng").task = hold("C3")
    assert battle.cover_for("us", "C3") == pytest.approx(0.3)


def test_river_crossing_uses_turn_start_engineer_positions(tmp_path):
    """§2：以回合開始的工兵位置為準，結果不隨單位 id 字母序改變。"""
    def run(tank_id: str, eng_id: str) -> str:
        g = grid()
        for c in "ABCDE":
            g.sectors[f"{c}2"].terrain = "river"; g.sectors[f"{c}2"].cover = 0.1
        units = [plt(tank_id, "A1", "tank", Task(type="seize", target="A3")), plt(eng_id, "A1", "engineer", Task(type="seize", target="A2"))]
        battle = Battle(Board(battle_id="v1", t=0, map=g, orbat=units, objectives=[]), [], out_dir=tmp_path / tank_id)
        battle.step([], [])
        return battle.board.unit(tank_id).sector
    assert run("a-tank", "z-eng") == run("z-tank", "a-eng") == "A1"      # 回合開始工兵還在岸上 → 兩種 id 序都過不了


def test_bad_weather_in_script_and_mixed_leaf_are_plain_errors(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"units": [], "orders": {}, "weather_changes": {"1": "hail"}}), encoding="utf-8")
    with pytest.raises(BoardError, match="劇本"):
        load_script(bad)
    b = board([plt("x", "C3", "mixed")])
    with pytest.raises(BoardError, match="mixed"):
        Battle(b, [], out_dir=tmp_path)


def test_v01_orbat_armor_becomes_tank_and_v02_armor_too():
    from chief.board import board_from_dict
    old = json.loads((SAMPLES / "board_start.json").read_text(encoding="utf-8"))
    old["schema_version"] = "0.1"; old.pop("era"); old.pop("weather"); old.pop("time_of_day")
    old["orbat"][-1]["type"] = "armor"
    assert board_from_dict(old).orbat[-1].type == "tank"
    new = json.loads((SAMPLES / "board_start.json").read_text(encoding="utf-8"))
    new["orbat"][-1]["type"] = "armor"; new["orbat"][-1]["equipment"] = "M4 Sherman"
    nb = board_from_dict(new)
    assert nb.orbat[-1].type == "tank" and nb.orbat[-1].equipment == "M4 Sherman"
    assert "equipment" not in json.dumps(nb.compact())                      # 不進壓縮快照


def test_rules_template_over_budget_is_plain(tmp_path):
    d = tmp_path / "rules"; d.mkdir()
    data = json.loads((ROOT / "rules" / "ww2_1944.json").read_text(encoding="utf-8"))
    data["templates"]["big"] = {"zh": "太貴", "units": ["tank"] * 5}
    (d / "x.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BoardError, match="超過預算"):
        load_rules("x", rules_dir=str(d))


def test_prompt_rules_fallback_when_template_has_no_hook(tmp_path, capsys):
    from chief.prompts import system_prompt, use_template
    tpl = tmp_path / "t.md"; tpl.write_text("You are chief. {doctrine}", encoding="utf-8")
    use_template(tpl)
    try:
        out = system_prompt("rule one")
    finally:
        use_template(None)
    assert "Combat model" in out and "rule one" in out and "掛點" in capsys.readouterr().err
