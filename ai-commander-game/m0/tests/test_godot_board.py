"""施工單 13 合約測試：Godot 引擎寫出的戰情板必須被 M0 的 Board 模型原封不動讀進來（docs/09 v0.2、ADR-0014 D18）。

兩層：
1. 永遠跑：`samples/godot_board_sample.json`（用 godot/tools/dump_board.gd 跑 120 秒產生、已提交）。
2. 有 Godot 才跑：環境變數 GODOT_BIN 指向 4.7.2 無頭可用的執行檔時，現場跑 dump_board 再驗。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from chief.board import estimate_tokens, load_board

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "samples" / "godot_board_sample.json"
GODOT_DIR = ROOT.parent / "godot"


def _check(path: Path) -> None:
    b = load_board(path)
    assert b.schema_version == "0.2" and b.time_unit == "second" and b.era == "ww2_1944"
    assert b.t >= 100 and b.phase in ("mid", "late")                      # 120 秒 → mid（>90）
    assert b.map.cols == 5 and len(b.map.sectors) == 25
    leaves = [u for u in b.orbat if u.echelon == "platoon"]
    assert len(leaves) == 8 and all(u.parent == "co-A" for u in leaves) and all(u.cost > 0 for u in leaves)
    assert b.unit("co-A").type == "mixed" and 0.0 <= b.unit("co-A").strength <= 1.0
    assert {u.type for u in leaves} == {"infantry", "mg", "mortar", "at", "recon", "engineer"}
    kinds = {e.kind for e in b.events}
    assert {"order", "seized", "contact"} <= kinds                        # A 連奪取 C3：有命令、易手、接觸
    assert any(e.kind == "seized" and e.sector == "C2" for e in b.events)
    assert b.enemy_known and all(0.5 <= c.confidence <= 1.0 for c in b.enemy_known)
    assert set(b.fog.visible_sectors) >= {"C3"}                            # 打到城鎮，看得見它
    assert {o.id for o in b.objectives} == {"O1", "O2", "O3"}
    assert estimate_tokens(b.compact_json()) < 2000                        # PRD：壓縮快照 < 2K token
    assert any(u.state in ("engaged", "routed", "destroyed") for u in leaves) or any(e.kind in ("routed", "destroyed") for e in b.events)


def test_committed_godot_sample_loads_with_m0_board_model():
    _check(SAMPLE)


def test_chief_show_renders_godot_board(capsys):
    from chief.cli import main
    assert main(["show", str(SAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "hill-town-start" in out and "A 連" in out and "t=120" in out


@pytest.mark.skipif(not os.getenv("GODOT_BIN"), reason="設 GODOT_BIN=<Godot 4.7.2 執行檔> 才現場跑引擎")
def test_live_godot_dump(tmp_path):
    out = tmp_path / "board.json"
    cmd = [os.environ["GODOT_BIN"], "--headless", "--path", str(GODOT_DIR), "-s", "tools/dump_board.gd", "--", f"out={out}", "seconds=120"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert res.returncode == 0, res.stdout[-2000:] + res.stderr[-2000:]
    _check(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["t"] == 120


# ---- 施工單 14：整場快照與 result.json（godot/tools/run_battle.gd -- difficulty=normal 產生）----
BATTLE_DIR = ROOT / "samples" / "godot_battle_sample"


def test_godot_battle_snapshots_replay_in_m0(capsys):
    from chief.cli import main
    assert sorted(int(p.stem[1:]) for p in BATTLE_DIR.glob("t*.json")) == list(range(0, 11))   # t0～t10
    result = json.loads((BATTLE_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["winner"] == "us" and (result["score_us"], result["score_enemy"]) == (8, 3)   # docs/10 §14：normal 我方勝 8:3
    assert result["end_reason"] == "turns" and result["seconds"] == 300 and result["turns_played"] == 10
    last = load_board(BATTLE_DIR / "t10.json")
    assert last.time_unit == "second" and last.t == 300 and last.phase == "late"
    assert main(["replay", str(BATTLE_DIR)]) == 0
    out = capsys.readouterr().out
    assert "共 10 回合（每回合 30 秒）" in out and "t1 " in out and "t10" in out
    assert "固守 B3" in out and "[weather] 天氣轉雨" in out and "我方取得 C3" in out   # 劇本命令、天氣變化、易手都落在正確回合
    assert "t3 " in out and out.index("[weather] 天氣轉雨") > out.index("t3 ")
