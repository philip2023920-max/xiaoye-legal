"""施工單 16：參謀長服務。用 fake 供應商與 Godot 樣板板走完整個流程；HTTP 在執行緒內起服務。
期望值來源：docs/10 §9（後果判定）、§11（卡與討論）、§12（採納與回歸）、docs/12 §2（端點）。"""
from __future__ import annotations

import http.client
import json
import shutil
import threading
import time
from pathlib import Path

import pytest

from chief.board import BoardError
from chief.bridge import ChiefSession, SessionConfig
from chief.serve import ChiefService, run_server

ROOT = Path(__file__).resolve().parent.parent
BOARD = json.loads((ROOT / "samples" / "godot_board_sample.json").read_text(encoding="utf-8"))
RESULT = {"battle_id": "hill-town-start", "turns_played": 10, "end_reason": "turns", "winner": "enemy", "score_us": 5, "score_enemy": 6,
          "strength_us": 7.1, "strength_enemy": 4.3}


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    (tmp_path / "harness").mkdir()
    shutil.copytree(ROOT / "harness" / "default", tmp_path / "harness" / "default")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def cfg(workdir: Path, **kw) -> SessionConfig:
    base = dict(provider="fake", out_root=str(workdir / "battles"), ledger=str(workdir / "battles" / "ledger.jsonl"))
    base.update(kw)
    return SessionConfig(**base)


def test_session_tick_override_outcome(workdir):
    s = ChiefSession(cfg(workdir), BOARD)
    assert s.info()["harness"] == "default" and s.opening_line() == "" and (s.out_dir / "t0.json").exists()
    r1 = s.tick(BOARD, t=0)
    assert r1["turn"] == 1 and r1["error"] is None and r1["assessment"].startswith("（示範）")
    assert [o["unit_id"] for o in r1["orders"]] == ["plt-A1", "plt-A2", "plt-A3"] and r1["rejected"] == []   # fake 劇本第 1 回合
    assert r1["usage"]["prompt_tokens"] == 100 and r1["cost_total_usd"] >= 0.0 and (s.out_dir / "llm_log.jsonl").exists()
    ov = s.override("plt-A1", {"task": "hold", "target": "B2"})
    assert ov["turn"] == 1 and ov["ai_order"]["task"] == "seize" and ov["override_rate"] == "1/3"
    assert (s.out_dir / "overrides.jsonl").exists() and (s.out_dir / "t0.json").exists()
    r2 = s.tick(BOARD, t=20)
    assert r2["turn"] == 2 and len(r2["outcomes"]) == 1
    assert r2["outcomes"][0]["outcome"] == "👍" and r2["outcomes"][0]["unit_id"] == "plt-A1"   # §9：戰力沒掉、B2 仍我方
    assert [o["unit_id"] for o in r2["orders"]] == ["co-A"]                                        # fake 劇本第 2 回合起
    with pytest.raises(BoardError, match="不在戰情板上"):
        s.override("plt-Z9", {"task": "hold", "target": "B2"})
    st = s.status()
    assert st["turn"] == 2 and st["overrides"] == 1 and st["chief_orders_total"] == 4 and st["override_rate"] == "1/4" and not st["ended"]


def test_end_aar_discuss_propose_adopt_undo(workdir):
    s = ChiefSession(cfg(workdir), BOARD)
    s.tick(BOARD); s.override("plt-A1", {"task": "hold", "target": "B2"}); s.tick(BOARD)
    end = s.end(BOARD, RESULT)
    card = end["card"]
    assert card["winner"] == "enemy" and card["overrides"] == 1 and card["moments"][0]["kind"] == "override" and card["moments"][0]["outcome"] == "👍"
    assert card["hint"] and len(end["quick_replies"]) == 3 and end["unjudged"] == 0
    assert (s.out_dir / "aar.json").exists() and (s.out_dir / "t2.json").exists()
    assert s.aar_line()["chief_line"] == "（示範）我學到您偏好穩紮穩打。"
    d1 = s.discuss(index=1)
    assert d1["round"] == 1 and d1["reply"] and len(d1["next_quick"]) == 3 and not d1["done"]
    with pytest.raises(BoardError, match="編號"):
        s.discuss(index=9)
    d2 = s.discuss(text="下次先守 B2")
    d3 = s.discuss(index=2)
    assert d3["round"] == 3 and d3["done"] and d3["next_quick"] == []
    assert s.discuss(text="再講")["done"] is True and len(s.transcript) == 6                      # 第 4 回合不算
    prop = s.propose()
    assert prop["diff"]["add"][0]["section"] == "profile" and not prop["diff"]["empty"]
    before = s.store.load()
    ad = s.adopt()
    assert ad["adopted"] and not ad["rolled_back"] and "demo" in ad["doctrine"] and any("戰例庫還是空的" in m for m in ad["messages"])
    cases = (workdir / "harness" / "default" / "evals" / "cases.jsonl")
    assert cases.exists() and len(cases.read_text(encoding="utf-8").splitlines()) == 1             # 這場的推翻進戰例庫
    aar = json.loads((s.out_dir / "aar.json").read_text(encoding="utf-8"))
    assert aar["adopted"] is True and aar["skipped"] is False and len(aar["transcript"]) == 6 and aar["card"]["chief_line"]
    assert s.undo()["undone"] and s.store.load() == before
    assert s.undo()["undone"] is False


def test_end_without_overrides_and_skip(workdir):
    s = ChiefSession(cfg(workdir, model="fake/empty"), BOARD)
    s.tick(BOARD)
    end = s.end(BOARD, {**RESULT, "winner": "us", "score_us": 8, "score_enemy": 3})
    assert end["card"]["winner"] == "us" and end["card"]["hint"] == "" and end["card"]["overrides"] == 0
    assert s.skip()["skipped"] and json.loads((s.out_dir / "aar.json").read_text(encoding="utf-8"))["skipped"] is True
    assert s.end(BOARD, RESULT)["card"]["winner"] == "us"                                           # 重複 end 不重算
    with pytest.raises(BoardError, match="propose"):
        s.adopt()
    assert s.tick(BOARD)["error"] == "這場已經結束"


def test_budget_pauses_chief(workdir):
    s = ChiefSession(cfg(workdir, budget_usd=0.0), BOARD)
    r1 = s.tick(BOARD)
    assert r1["budget_hit"] and any("預算" in m for m in r1["messages"]) and r1["orders"]
    r2 = s.tick(BOARD)
    assert r2["orders"] == [] and "預算" in r2["error"]
    assert s.settings(budget_usd=-1)["budget_usd"] is None and not s.budget_hit
    assert s.tick(BOARD)["orders"] != []


def test_settings_switch(workdir):
    s = ChiefSession(cfg(workdir), BOARD)
    out = s.settings(provider="fake", model="fake/empty", lang="en", budget_usd=0.5)
    assert out["model"] == "fake/empty" and out["lang"] == "en" and out["budget_usd"] == 0.5 and s.aar_gateway.model == "fake/empty"
    assert s.tick(BOARD)["orders"] == []
    bad = s.settings(provider="anthropic", model="claude-haiku-5-5")
    assert ("error" in bad and bad["model"] == "fake/empty") or bad["provider"] == "anthropic"     # 沙盒沒金鑰 → 保留原設定


def test_custom_doctrine_without_harness(workdir):
    doc = workdir / "my.md"; doc.write_text("# Doctrine v1\n\n## Verified tactics\n- Always hold B2.\n", encoding="utf-8")
    s = ChiefSession(cfg(workdir, harness="none", doctrine=str(doc)), BOARD)
    assert s.harness_name == "custom" and s.evals_dir is None and "Always hold B2" in s.doctrine
    s.tick(BOARD); s.override("plt-A1", {"task": "hold", "target": "B2"}); s.end(BOARD, RESULT); s.propose(); s.adopt()
    assert not (workdir / "harness" / "default" / "evals" / "cases.jsonl").exists()               # 沒有參謀長包就沒有戰例庫


def _post(conn, path, body=None):
    conn.request("POST", path, body=json.dumps(body or {}).encode("utf-8"), headers={"Content-Type": "application/json"})
    r = conn.getresponse()
    return r.status, json.loads(r.read().decode("utf-8"))


def test_http_round_trip(workdir):
    port_box: dict = {}
    th = threading.Thread(target=run_server, args=(cfg(workdir),), kwargs=dict(port=0, idle_exit_s=0, ready_cb=lambda p: port_box.update(port=p)), daemon=True)
    th.start()
    for _ in range(100):
        if port_box:
            break
        time.sleep(0.05)
    conn = http.client.HTTPConnection("127.0.0.1", port_box["port"], timeout=10)
    conn.request("GET", "/health"); r = conn.getresponse(); health = json.loads(r.read())
    assert r.status == 200 and health["ok"] and health["session"] is False
    assert _post(conn, "/tick", {"board": BOARD})[0] == 400                                       # 還沒有會話
    code, info = _post(conn, "/session/start", {"board": BOARD, "lang": "en"})
    assert code == 200 and info["lang"] == "en" and info["provider"] == "fake"
    code, tick = _post(conn, "/tick", {"t": 0, "board": BOARD})
    assert code == 200 and len(tick["orders"]) == 3
    code, ov = _post(conn, "/override", {"unit_id": "plt-A1", "player_order": {"task": "hold", "target": "B2"}})
    assert code == 200 and ov["recorded"] == 1
    code, end = _post(conn, "/battle/end", {"board": BOARD, "result": RESULT})
    assert code == 200 and end["card"]["overrides"] == 1
    assert _post(conn, "/aar/line")[1]["chief_line"] and _post(conn, "/aar/discuss", {"index": 1})[1]["round"] == 1
    assert _post(conn, "/aar/propose")[1]["diff"]["add"] and _post(conn, "/aar/adopt")[1]["adopted"] and _post(conn, "/aar/undo")[1]["undone"]
    conn.request("GET", "/status"); r = conn.getresponse(); st = json.loads(r.read())
    assert r.status == 200 and st["ended"] and st["overrides"] == 1
    conn.request("POST", "/tick", body=b"{not json", headers={"Content-Type": "application/json"}); r = conn.getresponse()
    assert r.status == 400 and "JSON" in json.loads(r.read())["error"]
    assert _post(conn, "/nope")[0] == 404
    conn.request("GET", "/nope"); r = conn.getresponse(); r.read(); assert r.status == 405
    assert _post(conn, "/shutdown")[1]["bye"]
    th.join(timeout=10)
    assert not th.is_alive()


def test_service_start_requires_board(workdir):
    svc = ChiefService(cfg(workdir))
    with pytest.raises(BoardError, match="board"):
        svc.start({})
    code, _ = svc.handle("GET", "/health", {})
    assert code == 200


def test_cli_serve_idle_exit(workdir, capsys):
    from chief.cli import main
    rc_box: dict = {}
    th = threading.Thread(target=lambda: rc_box.update(rc=main(["serve", "--port", "0", "--idle-exit", "1", "--out-root", str(workdir / "b"), "--ledger", "none"])), daemon=True)
    th.start()
    th.join(timeout=20)
    assert not th.is_alive() and rc_box["rc"] == 0
    assert "參謀長服務 http://127.0.0.1:" in capsys.readouterr().out
