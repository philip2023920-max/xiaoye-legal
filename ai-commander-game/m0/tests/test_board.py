"""施工單 01 驗收測試。期望值來源：samples/board_t0.json 是手工設計的（數字在設計時就定好），
token 上限 2,000 來自 PRD 的「壓縮快照 < 2K token」。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from chief.board import BoardError, board_from_dict, estimate_tokens, load_board
from chief.cli import main

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "board_t0.json"


def sample_dict() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_sample_counts_match_design():
    b = load_board(SAMPLE)
    assert len(b.map.sectors) == 25          # 5x5（決策 S1）
    # 驗收第 2 條原文：「會戰規模（連級，含敵我各 1 個連、3 個排）」
    assert Counter(u.echelon for u in b.orbat) == {"company": 1, "platoon": 3}
    assert Counter(c.echelon for c in b.enemy_known) == {"company": 1, "platoon": 3}
    assert [u.id for u in b.roots()] == ["co-A"]
    assert len(b.children("co-A")) == 3
    assert len(b.objectives) == 3
    assert b.scale == "battle"


def test_compact_drops_destroyed_units_and_dangling_parent():
    d = sample_dict()
    d["orbat"][0]["state"] = "destroyed"      # 連部被殲滅
    b = board_from_dict(d)
    c = b.compact()
    ids = [u["id"] for u in c["friendly"]]
    assert ids == ["plt-A1", "plt-A2", "plt-A3"]
    assert all(u.get("parent", "plt-A1") in ids for u in c["friendly"])  # 不留懸空 parent
    assert [u.id for u in b.units_in("B2")] == ["plt-A1"]


def test_empty_fog_means_all_visible(capsys):
    d = sample_dict()
    d["fog"]["visible_sectors"] = []
    b = board_from_dict(d)
    assert b.compact()["visible"] == "all"
    from chief.render import render_board
    render_board(b)
    out = capsys.readouterr().out
    assert out.count("?") == 1                # docs/09「終端機字元」：? 是迷霧符號；全圖可見時只剩圖例那一個


def test_support_target_must_be_friendly_unit_not_self():
    d = sample_dict()
    d["orbat"][2]["task"] = {"type": "support", "target": "C3"}   # 分區不行
    with pytest.raises(BoardError) as err:
        board_from_dict(d)
    assert "support" in str(err.value) and "plt-A2" in str(err.value)
    d["orbat"][2]["task"] = {"type": "support", "target": "plt-A2"}  # 自己不行
    with pytest.raises(BoardError):
        board_from_dict(d)


def test_seize_target_must_be_sector():
    d = sample_dict()
    d["orbat"][2]["task"] = {"type": "seize", "target": "plt-A1"}
    with pytest.raises(BoardError) as err:
        board_from_dict(d)
    assert "分區" in str(err.value)


def test_unit_id_cannot_clash_with_sector_id():
    d = sample_dict()
    d["orbat"][1]["id"] = "C3"
    with pytest.raises(BoardError) as err:
        board_from_dict(d)
    assert "C3" in str(err.value)


def test_unknown_schema_version_is_rejected():
    d = sample_dict()
    d["schema_version"] = "9.9"   # 0.1 會自動升級，9.9 不會
    with pytest.raises(BoardError) as err:
        board_from_dict(d)
    assert "9.9" in str(err.value)


def test_objective_and_sector_must_agree_both_ways():
    d = sample_dict()
    d["objectives"].append({"id": "O4", "sector": "E5", "value": 1, "owner": "none"})   # E5 沒標記 O4
    with pytest.raises(BoardError) as err:
        board_from_dict(d)
    assert "O4" in str(err.value)


def test_bom_file_loads(tmp_path):
    p = tmp_path / "bom.json"
    p.write_bytes(b"\xef\xbb\xbf" + SAMPLE.read_bytes())
    assert load_board(p).battle_id == "sample-hill-town"


def test_enum_error_is_in_plain_language():
    d = sample_dict()
    d["map"]["sectors"]["A1"]["terrain"] = "swamp"
    with pytest.raises(BoardError) as err:
        board_from_dict(d)
    assert "允許" in str(err.value) and "A1" in str(err.value)


def test_compact_fits_llm_budget():
    b = load_board(SAMPLE)
    text = b.compact_json()
    assert estimate_tokens(text) < 2000      # PRD：壓縮快照 < 2K token


def test_compact_marks_player_control_only_on_taken_units():
    c = load_board(SAMPLE).compact()
    by_id = {u["id"]: u for u in c["friendly"]}
    assert by_id["plt-A3"]["ctrl"] == "player"   # 範例：總司令接管 A3 機槍排
    assert "ctrl" not in by_id["plt-A1"]
    assert c["overrides"] == 1


def test_invalid_parent_is_reported_in_plain_language():
    d = sample_dict()
    d["orbat"][1]["parent"] = "co-Z"
    with pytest.raises(BoardError) as err:
        board_from_dict(d)
    assert "plt-A1" in str(err.value) and "co-Z" in str(err.value)


def test_missing_sector_lists_the_missing_id():
    d = sample_dict()
    del d["map"]["sectors"]["E5"]
    with pytest.raises(BoardError) as err:
        board_from_dict(d)
    assert "E5" in str(err.value)


def test_parent_must_be_higher_echelon():
    d = sample_dict()
    d["orbat"][1]["echelon"] = "company"     # 排改成連，與上級同層級
    with pytest.raises(BoardError) as err:
        board_from_dict(d)
    assert "層級" in str(err.value)


def test_parent_cannot_be_self():
    d = sample_dict()
    d["orbat"][0]["parent"] = "co-A"
    with pytest.raises(BoardError) as err:
        board_from_dict(d)
    assert "自己" in str(err.value)


def test_missing_file_message_names_path():
    with pytest.raises(BoardError) as err:
        load_board("samples/does-not-exist.json")
    assert "does-not-exist.json" in str(err.value)


def test_cli_show_prints_four_panels(capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "120")      # 固定終端寬度，窄終端不會把名稱折行
    assert main(["show", str(SAMPLE)]) == 0
    out = capsys.readouterr().out
    for panel in ("分區地圖", "友軍部隊樹", "目標", "事件流"):   # 驗收第 1 條的四個面板
        assert panel in out
    assert "A3 機槍排" in out and "直轄" in out


def test_cli_show_compact_prints_token_estimate(capsys):
    assert main(["show", str(SAMPLE), "--compact"]) == 0
    out = capsys.readouterr().out
    assert '"friendly"' in out and "token" in out


def test_cli_show_bad_file_returns_1_and_reports_on_stderr(capsys):
    assert main(["show", "samples/nope.json"]) == 1
    assert "找不到" in capsys.readouterr().err
