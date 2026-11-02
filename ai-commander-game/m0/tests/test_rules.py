"""施工單 08：規則資料表。期望值來自 rules/ww2_1944.json（手讀）與 docs/10 §4 v1 手算。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chief.board import BoardError, board_from_dict, load_board
from chief.rules import load_rules

ROOT = Path(__file__).resolve().parent.parent


def test_ww2_rules_load_and_template_costs():
    r = load_rules("ww2_1944")
    assert set(r.units) == {"infantry", "mg", "mortar", "at", "tank", "recon", "engineer"}
    assert r.template_cost("balanced") == 94 and r.template_cost("armor") == 94 and r.template_cost("infantry") == 92   # 手算
    assert all(r.template_cost(n) <= r.budget for n in r.templates)
    assert r.unit("armor").cost == 25                      # 舊名 armor → tank


def test_cold_war_skeletons_load():
    assert load_rules("coldwar_early").era == "coldwar_early" and load_rules("coldwar_late").budget == 100


def test_effective_fire_hand_values():
    r = load_rules()
    assert r.effective_fire("infantry", "tank") == pytest.approx(0.58)     # 1.0×0.4 + 0.3×0.6
    assert r.effective_fire("at", "tank") == pytest.approx(1.02)           # 0.3×0.4 + 1.5×0.6
    assert r.effective_fire("tank", "infantry") == pytest.approx(1.2)      # 1.2×1.0 + 1.0×0
    assert r.effective_fire("mg", "infantry") == pytest.approx(1.3)


def test_cover_sight_mobility_passability():
    r = load_rules()
    assert r.effective_cover("town", "fog", "night") == pytest.approx(0.8)          # 0.6+0.1+0.2=0.9 → cap 0.8
    assert r.effective_cover("open", "rain", "day") == pytest.approx(0.2)
    assert r.effective_cover("hill", "clear", "day", engineer_holding=True) == pytest.approx(0.5)
    assert r.fire_mult("fog", "night") == pytest.approx(0.42)                        # 0.7×0.6
    assert r.sight("recon", "clear", "day") == 2 and r.sight("recon", "fog", "day") == 0 and r.sight("infantry", "clear", "night") == 0
    assert r.mobility("tank", "rain") == 0.5 and r.mobility("infantry", "rain") == 1.0 and r.mobility("infantry", "snow") == 0.5
    assert r.can_enter("tank", "forest") is False and r.can_enter("tank", "river") is False
    assert r.can_enter("tank", "river", engineer_present=True) is True and r.can_enter("infantry", "river") is True


def test_bad_rules_file_reports_plainly(tmp_path):
    d = tmp_path / "rules"; d.mkdir()
    data = json.loads((ROOT / "rules" / "ww2_1944.json").read_text(encoding="utf-8"))
    del data["units"]["mortar"]
    (d / "x.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BoardError) as err:
        load_rules("x", rules_dir=str(d))
    assert "mortar" in str(err.value)
    with pytest.raises(BoardError) as err2:
        load_rules("nope", rules_dir=str(d))
    assert "找不到" in str(err2.value)


def test_prompt_text_mentions_all_types():
    t = load_rules().prompt_text()
    for u in ("infantry", "mortar", "engineer", "fog", "night"):
        assert u in t


def test_board_v02_fields_and_v01_upgrade():
    b = load_board(ROOT / "samples" / "board_start.json")
    assert (b.schema_version, b.era, b.weather, b.time_of_day) == ("0.2", "ww2_1944", "clear", "day")
    assert "weather" in b.compact() and b.compact()["era"] == "ww2_1944"
    old = json.loads((ROOT / "samples" / "board_t0.json").read_text(encoding="utf-8"))
    old["schema_version"] = "0.1"; old.pop("era"); old.pop("weather"); old.pop("time_of_day")
    old["enemy_known"][-1]["type"] = "armor"
    b2 = board_from_dict(old)
    assert b2.schema_version == "0.2" and b2.enemy_known[-1].type == "tank" and b2.weather == "clear"
