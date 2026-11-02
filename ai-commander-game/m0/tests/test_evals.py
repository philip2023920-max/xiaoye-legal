"""施工單 07 驗收：戰例庫回歸（規則 §12）與 5 場驗收曲線。"""
from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from chief.acceptance import battle_stats, rate_value, render_curve
from chief.board import load_board
from chief.doctrine import DoctrineStore
from chief.evals import EvalCase, EvalResult, build_cases_from_battle, compare, load_cases, run_evals, save_cases, save_result
from chief.gateway import FakeGateway
from chief.orders import ChiefOrders
from chief.play import run_play
from chief.sim import load_script

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def scripted(seq):
    it = iter(seq)
    return lambda p="": next(it, "")


def play_with_override(tmp_path, name="b", doctrine_path=None, evals_dir=None, gw=None, inputs=None):
    board = load_board(SAMPLES / "board_start.json"); enemy = load_script(SAMPLES / "enemy_script.json")
    gw = gw or FakeGateway([ChiefOrders(assessment="t1", orders=[{"unit_id": "plt-A3", "task": "seize", "target": "C3"}])])
    out = open(tmp_path / f"{name}.txt", "w", encoding="utf-8")
    res = run_play(gw, board, enemy, doctrine="d", out_dir=tmp_path / name, console=Console(file=out, width=120), auto=False,
                   input_fn=scripted(inputs or ["1", "2", "B2", "", "q", "s"]), doctrine_path=doctrine_path, evals_dir=evals_dir)
    out.close()
    return res, (tmp_path / f"{name}.txt").read_text(encoding="utf-8")


def test_cases_built_from_overrides_and_capped_at_ten(tmp_path):
    play_with_override(tmp_path)
    cases = build_cases_from_battle(tmp_path / "b")
    assert len(cases) == 1 and cases[0].unit_id == "plt-A3" and cases[0].player_task == "hold" and cases[0].player_target == "B2"
    assert cases[0].ai_task == "seize" and cases[0].board["t"] == 0           # 推翻當下＝上一回合快照
    p = tmp_path / "cases.jsonl"
    for i in range(12):
        c = EvalCase(**{**cases[0].__dict__, "id": f"c{i}"})
        save_cases([c], p)
    assert len(load_cases(p)) == 10


def test_two_battles_on_same_board_give_two_cases(tmp_path):
    play_with_override(tmp_path, "b1"); play_with_override(tmp_path, "b2")
    p = tmp_path / "cases.jsonl"
    for d in ("b1", "b2"):
        save_cases(build_cases_from_battle(tmp_path / d), p)
    assert len(load_cases(p)) == 2


def test_compare_refuses_to_judge_without_cases_or_with_other_model():
    empty = EvalResult(harness="t", provider="fake", model="m", cases=0, aligned=0, rejected_orders=0, total_orders=0)
    assert compare({"cases": 4, "aligned": 4, "model": "m"}, empty)[0] is False
    other = EvalResult(harness="t", provider="fake", model="m2", cases=2, aligned=0, rejected_orders=0, total_orders=2)
    regressed, msg = compare({"cases": 4, "aligned": 4, "model": "m"}, other)
    assert regressed is False and "不同模型" in msg
    noisy = EvalResult(harness="t", provider="fake", model="m", cases=2, aligned=0, rejected_orders=0, total_orders=0,
                       details=[{"error": "x"}, {"error": "y"}])
    assert compare({"cases": 4, "aligned": 4, "model": "m"}, noisy)[0] is False


def test_run_evals_alignment_and_regression_compare(tmp_path):
    play_with_override(tmp_path)
    cases = build_cases_from_battle(tmp_path / "b")
    aligned_gw = FakeGateway([ChiefOrders(assessment="", orders=[{"unit_id": "plt-A3", "task": "hold", "target": "B2"}])])
    res = run_evals(aligned_gw, cases, "doc", "default")
    assert res.cases == 1 and res.aligned == 1 and res.aligned_pct == 100.0
    assert "ctrl" not in json.dumps(aligned_gw.calls[0][1]["content"])      # 回歸時單位已還給參謀長
    wrong_gw = FakeGateway([ChiefOrders(assessment="", orders=[{"unit_id": "co-A", "task": "seize", "target": "C3"}])])
    res2 = run_evals(wrong_gw, cases, "doc", "default")
    assert res2.aligned == 0
    regressed, msg = compare({"cases": 1, "aligned": 1}, res2)
    assert regressed and "退步" in msg                                      # 100% → 0%：退步超過 5 點
    assert compare(None, res)[0] is False
    company_gw = FakeGateway([ChiefOrders(assessment="", orders=[{"unit_id": "co-A", "task": "hold", "target": "B2"}])])
    assert run_evals(company_gw, cases, "doc", "default").aligned == 1      # 對上級下同樣的令也算對齊


def test_adoption_regression_rolls_back_bad_doctrine(tmp_path):
    doc = tmp_path / "doctrine.md"
    doc.write_text("# D\n\n## Commander profile\n- Prefers holding B2 with the MG platoon.\n", encoding="utf-8")
    evals_dir = tmp_path / "evals"
    # 第 1 場：推翻並建立戰例；戰後跳過
    play_with_override(tmp_path, "b1", doctrine_path=doc, evals_dir=evals_dir)
    assert len(load_cases(evals_dir / "cases.jsonl")) == 1
    # 記一個「上一版成績」：對齊率 100%
    save_result(EvalResult(harness="t", provider="fake", model="fake/none", cases=1, aligned=1, rejected_orders=0, total_orders=1), evals_dir / "last.json")
    # 第 2 場：採納一條壞準則；回歸時參謀長對齊率掉到 0 → 自動回滾
    gw = FakeGateway([ChiefOrders(assessment="t1", orders=[{"unit_id": "plt-A3", "task": "seize", "target": "C3"}]),
                      ChiefOrders(assessment="", orders=[{"unit_id": "plt-A3", "task": "seize", "target": "C3"}])],   # 回歸時仍不對齊
                     chats=["學到了。"], parsed=[{"summary": "壞主意", "add": [{"section": "tactic", "text": "Never hold high ground; hills are a trap"}], "remove": []}])
    before = doc.read_text(encoding="utf-8")
    res, out = play_with_override(tmp_path, "b2", doctrine_path=doc, evals_dir=evals_dir, gw=gw, inputs=["1", "2", "B2", "", "q", "a", ""])
    assert "準則已更新" in out and "退步" in out and "已自動回滾" in out
    assert doc.read_text(encoding="utf-8") == before


def test_cmd_acceptance_runs_two_fake_battles(tmp_path, monkeypatch, capsys):
    import shutil
    from chief.cli import main
    harness_root = tmp_path / "harness"; (harness_root / "default").mkdir(parents=True)
    src = Path(__file__).resolve().parent.parent / "harness" / "default"
    for f in ("manifest.json", "doctrine.md"):
        shutil.copy(src / f, harness_root / "default" / f)
    (tmp_path / "samples").mkdir()
    for f in ("board_start.json", "enemy_script.json"):
        shutil.copy(SAMPLES / f, tmp_path / "samples" / f)
    monkeypatch.chdir(tmp_path)
    answers = iter(["q", "s", "q", "s"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers, ""))
    assert main(["acceptance", "--provider", "fake", "--battles", "2", "--quiet"]) == 0
    out = capsys.readouterr().out
    assert "M0 驗收：推翻率曲線" in out and len(list((tmp_path / "battles").glob("acceptance-*"))) == 2


def test_stats_curve_from_aar_files(tmp_path):
    for i, rate in enumerate(["2/4", "1/4", "0/4"], 1):
        d = tmp_path / f"b{i}"; d.mkdir()
        (d / "aar.json").write_text(json.dumps({"card": {"winner": "us", "score": [8, 3], "turns": 10, "override_rate": rate, "cost_usd": 0.0, "model": "m"}}), encoding="utf-8")
        import os, time
        os.utime(d / "aar.json", (time.time() + i, time.time() + i))
    rows = battle_stats(tmp_path)
    assert [rate_value(r["override_rate"]) for r in rows] == [50.0, 25.0, 0.0]
    out = open(tmp_path / "o.txt", "w", encoding="utf-8"); render_curve(rows, Console(file=out, width=120)); out.close()
    assert "下降 ✅" in (tmp_path / "o.txt").read_text(encoding="utf-8")


def test_cli_evals_build_run_and_stats(tmp_path, monkeypatch, capsys):
    """走 cli.main：build 從 battles 目錄建戰例，run 用 fake 供應商跑回歸，stats 列曲線。"""
    from chief.cli import main
    play_with_override(tmp_path, "b1")
    harness_root = tmp_path / "harness"; (harness_root / "default").mkdir(parents=True)
    import shutil
    src = Path(__file__).resolve().parent.parent / "harness" / "default"
    for f in ("manifest.json", "doctrine.md"):
        shutil.copy(src / f, harness_root / "default" / f)
    monkeypatch.chdir(tmp_path)
    assert main(["evals", "build", "--battles", str(tmp_path)]) == 0
    assert "戰例庫現有 1 筆" in capsys.readouterr().out
    assert main(["evals", "run", "--provider", "fake"]) == 0                     # 無基準：記為基準，不退步
    out = capsys.readouterr().out
    assert "對齊率" in out and (harness_root / "default" / "evals" / "last.json").exists()
    # 試水溫：壞準則 + --rollback 不得動真準則
    bad = tmp_path / "bad.md"; bad.write_text("# bad\n", encoding="utf-8")
    doc = harness_root / "default" / "doctrine.md"; before = doc.read_text(encoding="utf-8")
    main(["evals", "run", "--provider", "fake", "--doctrine", str(bad), "--rollback"])
    assert doc.read_text(encoding="utf-8") == before and not doc.with_suffix(".prev.md").exists()
    assert main(["stats", "--battles", str(tmp_path)]) == 0
    assert "推翻率" in capsys.readouterr().out
