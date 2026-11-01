"""施工單 01 驗收測試。期望值來源：samples/board_t0.json 是手工設計的（數字在設計時就定好），
token 上限 2,000 來自 PRD 的「壓縮快照 < 2K token」。"""
from __future__ import annotations

import json
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
    assert len(b.orbat) == 4                 # 1 連 + 3 排（範例設計）
    assert [u.id for u in b.roots()] == ["co-A"]
    assert len(b.children("co-A")) == 3
    assert len(b.enemy_known) == 3
    assert len(b.objectives) == 3
    assert len(b.events) == 4
    assert b.scale == "battle"


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
    d["orbat"][0]["parent"] = "plt-A1"       # 連掛在排底下：循環且層級錯
    d["orbat"][0]["echelon"] = "platoon"     # 同層級也不行
    with pytest.raises(BoardError) as err:
        board_from_dict(d)
    assert "層級" in str(err.value)


def test_missing_file_message_names_path():
    with pytest.raises(BoardError) as err:
        load_board("samples/does-not-exist.json")
    assert "does-not-exist.json" in str(err.value)


def test_cli_show_prints_map_and_tree(capsys):
    assert main(["show", str(SAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "分區地圖" in out and "友軍部隊樹" in out and "A3 機槍排" in out


def test_cli_show_compact_prints_token_estimate(capsys):
    assert main(["show", str(SAMPLE), "--compact"]) == 0
    out = capsys.readouterr().out
    assert '"friendly"' in out and "token" in out


def test_cli_show_bad_file_returns_1(capsys):
    assert main(["show", "samples/nope.json"]) == 1
    assert "找不到" in capsys.readouterr().out
