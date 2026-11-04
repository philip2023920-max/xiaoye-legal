"""施工單 16：參謀長服務。用 fake 供應商與 Godot 樣板板走完整個流程；HTTP 在執行緒內起服務。
期望值來源：docs/10 §9（後果判定與推翻率）、§11（卡與討論）、§12（採納與回歸）、§16（服務合約）、docs/12 §2（端點）。"""
from __future__ import annotations

import http.client
import json
import shutil
import threading
import time
from pathlib import Path

import pytest

from chief.board import BoardError
from chief.bridge import ChiefSession, ConflictError, SessionConfig
from chief.serve import ChiefService, run_server

ROOT = Path(__file__).resolve().parent.parent
BOARD = json.loads((ROOT / "samples" / "godot_board_sample.json").read_text(encoding="utf-8"))          # 秒制：t=120 s
TURN_BOARD = json.loads((ROOT / "samples" / "board_deployed_balanced.json").read_text(encoding="utf-8"))  # 回合制：t=0
RESULT = {"battle_id": "hill-town-start", "turns_played": 10, "end_reason": "turns", "winner": "enemy", "score_us": 5, "score_enemy": 6,
          "strength_us": 7.1, "strength_enemy": 4.3}


def at(t: float, **unit_ctrl: str) -> dict:
    """同一張板換時間；unit_ctrl 可改某些單位的 controlled_by（模擬 Godot 標 player／放手）。"""
    b = json.loads(json.dumps(BOARD))
    b["t"] = t
    for u in b["orbat"]:
        if u["id"] in unit_ctrl:
            u["controlled_by"] = unit_ctrl[u["id"]]
    return b


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


# ---- 每回合 ----
def test_session_tick_override_outcome(workdir):
    s = ChiefSession(cfg(workdir), BOARD)
    assert s.info()["harness"] == "default" and s.opening_line() == "" and (s.out_dir / "t0.json").exists()
    r1 = s.tick(BOARD, t=120)
    assert r1["turn"] == 1 and r1["error"] is None and r1["assessment"].startswith("（示範）")
    assert [o["unit_id"] for o in r1["orders"]] == ["plt-A1", "plt-A2", "plt-A3"] and r1["rejected"] == []   # fake 劇本第 1 回合
    assert r1["usage"]["prompt_tokens"] == 100 and r1["cost_total_usd"] >= 0.0 and (s.out_dir / "llm_log.jsonl").exists()
    ov = s.override("plt-A1", {"task": "hold", "target": "B2"})
    assert ov["turn"] == 1 and ov["counted"] and ov["ai_order"]["task"] == "seize" and ov["override_rate"] == "1/3"
    assert (s.out_dir / "overrides.jsonl").exists() and (s.out_dir / "t0.json").exists()
    r2 = s.tick(at(140), t=140)                                      # 推翻後過了一個決策間隔（20 秒）→ 這拍判
    assert r2["turn"] == 2 and len(r2["outcomes"]) == 1
    assert r2["outcomes"][0]["outcome"] == "👍" and r2["outcomes"][0]["unit_id"] == "plt-A1"   # §9：戰力沒掉、B2 仍我方
    assert [o["unit_id"] for o in r2["orders"]] == ["co-A"]                                        # fake 劇本第 2 回合起
    with pytest.raises(BoardError, match="不在戰情板上"):
        s.override("plt-Z9", {"task": "hold", "target": "B2"})
    st = s.status()
    assert st["turn"] == 2 and st["overrides"] == 1 and st["chief_orders_total"] == 4 and st["override_rate"] == "1/4" and not st["ended"]
    assert st["player_units"] == []                                  # 板上沒標 player → 下一拍視為放手


def test_override_validates_player_order(workdir):
    """審查 2：壞命令在 /override 就擋（400），不能讓下一拍 KeyError 報廢。"""
    s = ChiefSession(cfg(workdir), BOARD)
    with pytest.raises(BoardError, match="任務"):
        s.override("plt-A1", {"target": "B2"})
    with pytest.raises(BoardError, match="任務"):
        s.override("plt-A1", {"task": "charge!!", "target": "B2"})
    with pytest.raises(BoardError, match="target"):
        s.override("plt-A1", {"task": "hold", "target": ""})
    with pytest.raises(BoardError, match="不是分區"):
        s.override("plt-A1", {"task": "seize", "target": "Z9"})
    with pytest.raises(BoardError, match="support"):
        s.override("plt-A1", {"task": "support", "target": "B2"})
    assert s.overrides.records == [] and s.player_units == set()
    ov = s.override("plt-A2", {"task": "support", "target": "plt-A1"})      # 第一拍前也能推翻：turn=1、分母 0
    assert ov["turn"] == 1 and ov["override_rate"] == "1/0" and ov["ai_order"] == {"task": "seize", "target": "C3"}   # 板上的 task 當被推翻的令
    r = s.tick(BOARD, t=120)
    assert r["turn"] == 1 and r["outcomes"] == [] and r["error"] is None


def test_override_counting_and_ai_order_chain(workdir):
    """審查 3、4：已直轄單位再改令不算推翻；ai_order 沿上級鏈找（連令拆到排），取最近一拍。"""
    s = ChiefSession(cfg(workdir), BOARD)
    s.tick(BOARD, t=120)                                             # 第 1 拍：plt-A1 seize、plt-A2 support、plt-A3 hold
    s.tick(at(140), t=140)                                           # 第 2 拍：co-A hold C3（連令）
    ov = s.override("plt-A4", {"task": "hold", "target": "B2"}, board=at(141, **{"plt-A4": "player"}))
    assert ov["counted"] and ov["ai_order"]["unit_id"] == "co-A" and ov["ai_order"]["task"] == "hold"   # 上級的連令
    again = s.override("plt-A4", {"task": "seize", "target": "C3"}, board=at(150, **{"plt-A4": "player"}))
    assert not again["counted"] and again["recorded"] == 1 and "不算推翻" in again["message"]
    ov1 = s.override("plt-A1", {"task": "hold", "target": "B2"})
    assert ov1["counted"] and ov1["ai_order"]["unit_id"] == "co-A"                                     # 第 2 拍的連令比第 1 拍的排令新
    assert s.override_rate() == "2/4"
    s.tick(at(160, **{"plt-A4": "ai"}), t=160)                       # Godot 放手：plt-A4 標回 ai
    assert s.status()["player_units"] == []                          # plt-A1 的板也沒標 player → 一併視為放手
    assert s.override("plt-A4", {"task": "hold", "target": "B2"})["counted"]                            # 放手後再接管算一次
    assert len(s.overrides.records) == 3


def test_release_makes_next_takeover_count(workdir):
    """施工單 19：放手立刻生效（不等下一拍的板），之後再接管算新的一次推翻。"""
    s = ChiefSession(cfg(workdir), BOARD)
    s.tick(BOARD, t=120)
    assert s.override("plt-A1", {"task": "hold", "target": "B2"}, board=at(121, **{"plt-A1": "player"}), t=121)["counted"]
    assert not s.override("plt-A1", {"task": "seize", "target": "C3"}, board=at(125, **{"plt-A1": "player"}), t=125)["counted"]
    rel = s.release(["plt-A1", "plt-A9"])
    assert rel["released"] == ["plt-A1"] and rel["player_units"] == [] and rel["override_rate"] == "1/3"
    assert s.override("plt-A1", {"task": "hold", "target": "B2"}, board=at(130, **{"plt-A1": "player"}), t=130)["counted"] and len(s.overrides.records) == 2
    svc = ChiefService(cfg(workdir)); svc.start({"board": BOARD})
    with pytest.raises(BoardError, match="unit_ids"):
        svc.handle("POST", "/release", {"unit_ids": "plt-A1"})
    assert svc.handle("POST", "/release", {"unit_ids": ["plt-A1"]})[1]["released"] == []


def test_company_takeover_counts_as_subtree(workdir):
    """19 審查 1：接管連＝整棵子樹直轄；放手連把子排一起放掉；之後再接管子排算新的一次。"""
    s = ChiefSession(cfg(workdir), BOARD)
    s.tick(BOARD, t=120)
    all_player = {u["id"]: "player" for u in BOARD["orbat"]}
    assert s.override("co-A", {"task": "seize", "target": "C3"}, board=at(121, **all_player), t=121)["counted"]
    assert "plt-A1" in s.player_units and "co-A" in s.player_units
    assert not s.override("plt-A1", {"task": "hold", "target": "B2"}, board=at(122, **all_player), t=122)["counted"]        # 連已直轄 → 改排不算
    rel = s.release(["co-A"] + [u["id"] for u in BOARD["orbat"] if u["id"] != "co-A"])
    assert "co-A" in rel["released"] and "plt-A1" in rel["released"] and rel["player_units"] == []
    assert s.override("plt-A1", {"task": "hold", "target": "B2"}, board=at(123, **{"plt-A1": "player"}), t=123)["counted"]   # 放手連後再接管子排：第 2 次
    assert len(s.overrides.records) == 2
    # 反向：接管排 → 放手排 → 接管連（算）→ 再改那個排（不算：released_units 已被連的子樹清掉）
    s2 = ChiefSession(cfg(workdir), BOARD)
    s2.tick(BOARD, t=120)
    assert s2.override("plt-A2", {"task": "hold", "target": "B2"}, board=at(121, **{"plt-A2": "player"}), t=121)["counted"]
    s2.release(["plt-A2"])
    assert s2.override("co-A", {"task": "seize", "target": "C3"}, board=at(122, **all_player), t=122)["counted"]
    assert not s2.override("plt-A2", {"task": "hold", "target": "B2"}, board=at(123, **all_player), t=123)["counted"] and len(s2.overrides.records) == 2
    # 接管連後只放手一個排 → 再接管那個排算
    s2.release(["plt-A5"])
    assert s2.override("plt-A5", {"task": "hold", "target": "B2"}, board=at(124, **all_player), t=124)["counted"] and len(s2.overrides.records) == 3
    # 三審：此時八個排全直轄 → 再對連下令不算（連還留在 released_units 也不算）
    assert not s2.override("co-A", {"task": "hold", "target": "C3"}, board=at(125, **all_player), t=125)["counted"] and len(s2.overrides.records) == 3


def test_judge_timing_seconds_and_turns(workdir):
    """審查 5：秒制板的後果至少隔 20 秒才判；回合制板維持下一拍。"""
    s = ChiefSession(cfg(workdir), BOARD)
    s.tick(BOARD, t=120)
    s.override("plt-A1", {"task": "hold", "target": "B2"})
    assert s.tick(at(130), t=130)["outcomes"] == []                 # 才過 10 秒（事件拍）：不判
    assert s.tick(at(139), t=139)["outcomes"] == []
    out = s.tick(at(140), t=140)["outcomes"]
    assert len(out) == 1 and out[0]["outcome"] == "👍" and s.overrides.records[0].judged_turn == 4
    t = ChiefSession(cfg(workdir), TURN_BOARD)
    t.tick(TURN_BOARD); t.override("plt-A1", {"task": "hold", "target": "B2"})
    assert len(t.tick(TURN_BOARD)["outcomes"]) == 1                 # 回合制：下一拍就判


def test_parse_failure_feedback(workdir):
    from chief.gateway import ChiefResponse
    from chief.meter import Usage
    s = ChiefSession(cfg(workdir), BOARD)
    s.gateway.issue_orders = lambda messages: ChiefResponse(orders=None, usage=Usage(10, 0), error="模型回了散文", raw="blah")
    r = s.tick(BOARD, t=120)
    assert r["error"] == "模型回了散文" and r["orders"] == [] and any("could not be parsed" in f for f in s.feedback)
    assert (s.out_dir / "llm_log.jsonl").read_text(encoding="utf-8").count("\n") == 1


# ---- 戰後 ----
def test_end_aar_discuss_propose_adopt_undo(workdir):
    s = ChiefSession(cfg(workdir), BOARD)
    s.tick(BOARD, t=120); s.override("plt-A1", {"task": "hold", "target": "B2"}); s.tick(at(140), t=140)
    end = s.end(at(300), RESULT)
    card = end["card"]
    assert card["winner"] == "enemy" and card["overrides"] == 1 and card["moments"][0]["kind"] == "override" and card["moments"][0]["outcome"] == "👍"
    assert card["hint"] and len(end["quick_replies"]) == 3 and end["unjudged"] == 0
    assert (s.out_dir / "aar.json").exists() and (s.out_dir / "t2.json").exists() and s.status()["turn"] == 2   # 最終板 t<拍數>.json，拍數不動
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
    assert prop["diff"]["add"][0]["section"] == "profile" and not prop["diff"]["empty"] and prop["error"] is None
    before = s.store.load()
    ad = s.adopt()
    assert ad["adopted"] and not ad["rolled_back"] and "demo" in ad["doctrine"] and any("戰例庫還是空的" in m for m in ad["messages"])
    cases = (workdir / "harness" / "default" / "evals" / "cases.jsonl")
    assert cases.exists() and len(cases.read_text(encoding="utf-8").splitlines()) == 1             # 這場的推翻進戰例庫
    aar_text = (s.out_dir / "aar.json").read_text(encoding="utf-8")
    aar = json.loads(aar_text)
    assert aar["adopted"] is True and aar["skipped"] is False and len(aar["transcript"]) == 6 and aar["card"]["chief_line"]
    with pytest.raises(ConflictError, match="已結束"):                                            # 審查 1：adopt 只能一次
        s.adopt()
    with pytest.raises(ConflictError, match="已結束"):                                            # adopt 後 skip 不得改寫 aar.json
        s.skip()
    with pytest.raises(ConflictError):
        s.discuss(text="還想講")
    assert (s.out_dir / "aar.json").read_text(encoding="utf-8") == aar_text and s.status()["aar_closed"]
    assert s.undo()["undone"] and s.store.load() == before                                        # 上一版＝採納前
    assert s.undo()["undone"] is False


def test_end_without_overrides_and_skip(workdir):
    s = ChiefSession(cfg(workdir, model="fake/empty"), BOARD)
    s.tick(BOARD, t=120)
    end = s.end(at(300), {**RESULT, "winner": "us", "score_us": 8, "score_enemy": 3})
    assert end["card"]["winner"] == "us" and end["card"]["hint"] == "" and end["card"]["overrides"] == 0
    assert s.skip()["skipped"] and json.loads((s.out_dir / "aar.json").read_text(encoding="utf-8"))["skipped"] is True
    again = s.end(BOARD, RESULT)
    assert again["card"]["winner"] == "us" and again["unjudged"] == 0 and len(again["quick_replies"]) == 3   # 重複 end 不重算、形狀相同
    with pytest.raises(ConflictError, match="已結束"):
        s.adopt()
    with pytest.raises(ConflictError, match="不能再 tick"):
        s.tick(BOARD)
    with pytest.raises(ConflictError, match="不能再推翻"):
        s.override("plt-A1", {"task": "hold", "target": "B2"})


def test_end_validates_result_before_mutating(workdir):
    """審查 11：result 先驗再改狀態；壞資料回人話、不留半套紀錄。"""
    s = ChiefSession(cfg(workdir), BOARD)
    s.tick(BOARD, t=120); s.tick(at(140), t=140)
    for bad in ({}, {**RESULT, "winner": "aliens"}, {**RESULT, "end_reason": "timeout"}, {**RESULT, "score_us": "many"}):
        with pytest.raises(BoardError, match="result 不合法"):
            s.end(at(300), bad)
    assert not s.ended and s.status()["turn"] == 2 and not (s.out_dir / "t2.json").exists()
    ok = s.end(at(300), {"winner": "draw", "score_us": 5, "score_enemy": 5, "end_reason": "strength"})
    assert ok["card"]["winner"] == "draw" and s.result.end_reason == "strength" and s.result.turns_played == 2 and (s.out_dir / "t2.json").exists()


def test_end_judges_due_overrides(workdir):
    s = ChiefSession(cfg(workdir), BOARD)
    s.tick(BOARD, t=120); s.override("plt-A1", {"task": "hold", "target": "B2"})
    assert s.end(at(300), RESULT)["unjudged"] == 0 and s.overrides.records[0].outcome == "👍"      # 最終板離推翻 ≥ 20 秒 → 判
    late = ChiefSession(cfg(workdir), BOARD)
    late.tick(BOARD, t=120); late.override("plt-A1", {"task": "hold", "target": "B2"})
    assert late.end(at(130), RESULT)["unjudged"] == 1                                                 # 最後 10 秒才推翻 → 不判（§9）


def test_aar_duration_starts_at_first_interaction(workdir):
    s = ChiefSession(cfg(workdir), BOARD)
    s.tick(BOARD, t=120); s.end(at(300), RESULT)
    assert s.aar_started is None
    s.aar_line()
    assert s.aar_started is not None and s.skip()["duration_s"] >= 0.0


def test_budget_pauses_chief(workdir):
    s = ChiefSession(cfg(workdir, budget_usd=0.0), BOARD)
    r1 = s.tick(BOARD)
    assert r1["budget_hit"] and any("預算" in m for m in r1["messages"]) and r1["orders"]
    r2 = s.tick(BOARD)
    assert r2["orders"] == [] and "預算" in r2["error"] and "cost_total_usd" in r2 and set(r2) == set(r1)   # 審查 12：暫停拍形狀相同
    assert s.settings(budget_usd=-1)["budget_usd"] is None and not s.budget_hit
    assert s.tick(BOARD)["orders"] != []


def test_settings_switch(workdir, monkeypatch):
    s = ChiefSession(cfg(workdir), BOARD)
    out = s.settings(provider="fake", model="fake/empty", lang="en", budget_usd=0.5)
    assert out["model"] == "fake/empty" and out["lang"] == "en" and out["budget_usd"] == 0.5 and s.aar_gateway.model == "fake/empty"
    assert s.tick(BOARD)["orders"] == []
    only_aar = s.settings(aar_model="fake/none")                                                     # 審查 8：aar_* 單獨送也生效
    assert only_aar["error"] is None and only_aar["aar_model"] == "fake/none" and s.aar_gateway.model == "fake/none" and s.gateway.model == "fake/empty"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False); monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    bad = s.settings(provider="anthropic", model="claude-haiku-5-5")
    assert "ANTHROPIC_API_KEY" in bad["error"] and bad["provider"] == "fake" and bad["model"] == "fake/empty"   # 沒金鑰 → 保留原設定
    assert s.cfg.provider == "fake" and s.tick(BOARD)["error"] is None


def test_custom_doctrine_without_harness(workdir):
    import chief.prompts as prompts
    ChiefSession(cfg(workdir), BOARD)                                                                # 先用參謀長包（會掛模板）
    doc = workdir / "my.md"; doc.write_text("# Doctrine v1\n\n## Verified tactics\n- Always hold B2.\n", encoding="utf-8")
    s = ChiefSession(cfg(workdir, harness="none", doctrine=str(doc)), BOARD)
    assert s.harness_name == "custom" and s.evals_dir is None and "Always hold B2" in s.doctrine
    assert prompts._template_override is None                                                        # 審查 14：上一場的包不殘留
    s.tick(BOARD, t=120); s.override("plt-A1", {"task": "hold", "target": "B2"}); s.end(at(300), RESULT); s.propose(); s.adopt()
    assert not (workdir / "harness" / "default" / "evals" / "cases.jsonl").exists()               # 沒有參謀長包就沒有戰例庫


def test_override_t_decides_judging_time(workdir):
    """二審 (b)5：/override 可帶 t；不帶板時推翻秒不再退化成上一拍的 t。"""
    s = ChiefSession(cfg(workdir), BOARD)
    s.tick(BOARD, t=120)
    ov = s.override("plt-A1", {"task": "hold", "target": "B2"}, t=139)
    assert ov["counted"] and s.overrides.records[0].t_at == 139.0 and '"t_at": 139.0' in (s.out_dir / "overrides.jsonl").read_text(encoding="utf-8")
    assert s.tick(at(140), t=140)["outcomes"] == [] and s.tick(at(158), t=158)["outcomes"] == []      # 139+20=159 才判
    assert len(s.tick(at(159), t=159)["outcomes"]) == 1
    with pytest.raises(BoardError, match="數字"):
        s.override("plt-A2", {"task": "hold", "target": "B2"}, t="soon")
    ov2 = s.override("plt-A2", {"task": "hold", "target": "B2"}, board=at(170, **{"plt-A2": "player"}))   # 沒 t → 用附帶板的 t
    assert s.overrides.records[1].t_at == 170.0 and ov2["counted"]


def test_end_exception_leaves_no_half_state(workdir, monkeypatch):
    """二審 (c)3：建卡中途例外 → 不算結束、再 end 一次要能成功。"""
    import chief.bridge as bridge
    s = ChiefSession(cfg(workdir), BOARD)
    s.tick(BOARD, t=120); s.override("plt-A1", {"task": "hold", "target": "B2"})
    real = bridge.build_card_from
    monkeypatch.setattr(bridge, "build_card_from", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        s.end(at(300), RESULT)
    assert not s.ended and s.card is None and s.override_outcomes == [] and s.overrides.records[0].outcome is None and not (s.out_dir / "t1.json").exists()
    monkeypatch.setattr(bridge, "build_card_from", real)
    assert s.end(at(300), RESULT)["unjudged"] == 0 and s.ended and (s.out_dir / "t1.json").exists()


def test_end_before_any_tick_keeps_t0(workdir):
    """二審 (c)4：還沒 tick 就結束 → 開局板 t0.json 不被最終板蓋掉。"""
    s = ChiefSession(cfg(workdir), BOARD)
    s.override("plt-A1", {"task": "hold", "target": "B2"})
    s.end(at(300), RESULT)
    assert json.loads((s.out_dir / "t0.json").read_text(encoding="utf-8"))["t"] == 120 and json.loads((s.out_dir / "final.json").read_text(encoding="utf-8"))["t"] == 300


def test_settings_applies_lang_before_gateway_failure(workdir, monkeypatch):
    """二審 (c)5：閘道失敗不會把同一請求的語言／預算丟掉。"""
    s = ChiefSession(cfg(workdir), BOARD)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = s.settings(provider="anthropic", lang="en", budget_usd=0.2)
    assert out["error"] and out["provider"] == "fake" and out["lang"] == "en" and out["budget_usd"] == 0.2 and s.lang == "en"


# ---- 服務層 ----
def test_service_validates_types_and_harness_name(workdir):
    """二審 (c)1、(c)2：壞型別與參謀長包路徑穿越在 /session/start、/settings、/aar/discuss 就擋（400 人話）。"""
    svc = ChiefService(cfg(workdir))
    for bad, why in (({"lang": 7}, "session 設定"), ({"budget_usd": "abc"}, "session 設定"), ({"effort": "max"}, "session 設定"),
                     ({"harness": "../../evil"}, "參謀長包名稱"), ({"harness": "a/b"}, "參謀長包名稱"), ({"harness": 5}, "session 設定")):
        with pytest.raises(BoardError, match=why):
            svc.start({"board": BOARD, **bad})
    assert svc.session is None
    assert svc.start({"board": BOARD, "lang": "en", "budget_usd": 0.5, "harness": "none"})["lang"] == "en"
    with pytest.raises(BoardError, match="settings 不合法"):
        svc.handle("POST", "/settings", {"budget_usd": "0.5"})
    with pytest.raises(BoardError, match="settings 不合法"):
        svc.handle("POST", "/settings", {"lang": "fr"})
    assert svc.handle("POST", "/settings", {"budget_usd": 1})[1]["budget_usd"] == 1.0
    svc.session.tick(BOARD, t=120); svc.session.end(at(300), RESULT)
    with pytest.raises(BoardError, match="index"):
        svc.handle("POST", "/aar/discuss", {"index": "abc"})
    with pytest.raises(BoardError, match="index"):
        svc.handle("POST", "/aar/discuss", {"index": 1.5})
    assert svc.handle("POST", "/aar/discuss", {"index": 1.0})[1]["round"] == 1
    with pytest.raises(BoardError, match="ai_order"):
        svc.handle("POST", "/override", {"unit_id": "plt-A1", "player_order": {"task": "hold", "target": "B2"}, "ai_order": "x"})


def test_service_start_whitelist_and_doctrine_containment(workdir):
    svc = ChiefService(cfg(workdir))
    with pytest.raises(BoardError, match="board"):
        svc.start({})
    with pytest.raises(BoardError, match="路徑"):                                                   # 審查 9：準則檔不得跳出工作目錄
        svc.start({"board": BOARD, "harness": "none", "doctrine": "/etc/hostname"})
    with pytest.raises(BoardError, match="路徑"):
        svc.start({"board": BOARD, "harness": "none", "doctrine": "../x.md"})
    assert svc.session is None
    info = svc.start({"board": BOARD, "out_root": str(workdir / "elsewhere"), "ledger": "/tmp/evil.jsonl", "prices": "/etc/passwd", "lang": "en"})
    assert info["lang"] == "en" and Path(info["out_dir"]).parent == workdir / "battles" and not (workdir / "elsewhere").exists()   # 非白名單欄位忽略
    (workdir / "my.md").write_text("# Doctrine v1\n\n## Verified tactics\n- Always hold B2.\n", encoding="utf-8")
    info = svc.start({"board": BOARD, "harness": "none", "doctrine": "my.md"})
    assert info["harness"] == "custom" and info["doctrine_path"].endswith("my.md")
    code, bare = svc.handle("POST", "/session/start", json.loads(json.dumps(BOARD)))                # 裸板也收（驗收腳本 -d @board.json）
    assert code == 200 and bare["battle_id"] == BOARD["battle_id"]
    assert svc.handle("GET", "/health", {})[0] == 200 and svc.handle("GET", "/nope", {})[0] == 404 and svc.handle("PUT", "/tick", {})[0] == 405


def test_session_switch_writes_cases(workdir):
    """審查 15：出了卡沒走到採納／跳過就開下一場 → 戰例仍進戰例庫。"""
    svc = ChiefService(cfg(workdir))
    svc.start({"board": BOARD})
    s = svc.session
    s.tick(BOARD, t=120); s.override("plt-A1", {"task": "hold", "target": "B2"}); s.tick(at(140), t=140); s.end(at(300), RESULT)
    cases = workdir / "harness" / "default" / "evals" / "cases.jsonl"
    assert not cases.exists()
    svc.start({"board": BOARD})
    assert cases.exists() and len(cases.read_text(encoding="utf-8").splitlines()) == 1 and s.aar_closed
    svc.close()
    assert len(cases.read_text(encoding="utf-8").splitlines()) == 1


def test_health_reports_key_flags_only(workdir, monkeypatch):
    """施工單 21（D25）：設定頁只看得到已設定／未設定，金鑰值絕不經過 HTTP。"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value"); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    svc = ChiefService(cfg(workdir))
    code, body = svc.handle("GET", "/health", {})
    assert code == 200 and body["keys"]["anthropic"] is True and body["keys"]["openai"] is False and "secret" not in json.dumps(body)


def test_service_token(workdir):
    svc = ChiefService(cfg(workdir), token="s3cret")
    assert svc.handle("GET", "/health", {})[0] == 200
    assert svc.handle("GET", "/status", {})[0] == 401 and svc.handle("POST", "/session/start", {"board": BOARD})[0] == 401
    assert svc.handle("POST", "/session/start", {"board": BOARD}, token="s3cret")[0] == 200 and svc.handle("GET", "/status", {}, token="s3cret")[0] == 200


def _post(conn, path, body=None, headers=None):
    conn.request("POST", path, body=json.dumps(body or {}).encode("utf-8"), headers={"Content-Type": "application/json", **(headers or {})})
    r = conn.getresponse()
    return r.status, json.loads(r.read().decode("utf-8"))


def _serve(workdir, **kw):
    port_box: dict = {}
    th = threading.Thread(target=run_server, args=(cfg(workdir),), kwargs=dict(port=0, ready_cb=lambda p: port_box.update(port=p), **kw), daemon=True)
    th.start()
    for _ in range(100):
        if port_box:
            break
        time.sleep(0.05)
    return th, http.client.HTTPConnection("127.0.0.1", port_box["port"], timeout=15)


def test_http_round_trip(workdir):
    th, conn = _serve(workdir, idle_exit_s=0)
    conn.request("GET", "/health"); r = conn.getresponse(); health = json.loads(r.read())
    assert r.status == 200 and health["ok"] and health["session"] is False and health["auth"] is False
    assert _post(conn, "/tick", {"board": BOARD})[0] == 400                                       # 還沒有會話
    code, info = _post(conn, "/session/start", {"board": BOARD, "lang": "en"})
    assert code == 200 and info["lang"] == "en" and info["provider"] == "fake"
    code, tick = _post(conn, "/tick", {"t": 120, "board": BOARD})
    assert code == 200 and len(tick["orders"]) == 3
    code, bad = _post(conn, "/override", {"unit_id": "plt-A1", "player_order": {"target": "B2"}})
    assert code == 400 and "任務" in bad["error"]
    code, ov = _post(conn, "/override", {"unit_id": "plt-A1", "player_order": {"task": "hold", "target": "B2"}})
    assert code == 200 and ov["recorded"] == 1 and ov["counted"]
    code, bad_end = _post(conn, "/battle/end", {"board": BOARD, "result": {"winner": "aliens"}})
    assert code == 400 and "result 不合法" in bad_end["error"]
    code, end = _post(conn, "/battle/end", {"board": at(300), "result": RESULT})
    assert code == 200 and end["card"]["overrides"] == 1 and end["unjudged"] == 0
    assert _post(conn, "/tick", {"board": BOARD})[0] == 409                                       # 戰後再 tick
    assert _post(conn, "/aar/line")[1]["chief_line"] and _post(conn, "/aar/discuss", {"index": 1})[1]["round"] == 1
    assert _post(conn, "/aar/propose")[1]["diff"]["add"] and _post(conn, "/aar/adopt")[1]["adopted"]
    assert _post(conn, "/aar/adopt")[0] == 409 and _post(conn, "/aar/undo")[1]["undone"]
    conn.request("GET", "/status"); r = conn.getresponse(); st = json.loads(r.read())
    assert r.status == 200 and st["ended"] and st["overrides"] == 1 and st["turn"] == 1
    conn.request("POST", "/tick", body=b"{not json", headers={"Content-Type": "application/json"}); r = conn.getresponse()
    assert r.status == 400 and "JSON" in json.loads(r.read())["error"]
    assert _post(conn, "/nope")[0] == 404
    conn.request("GET", "/nope"); r = conn.getresponse(); r.read(); assert r.status == 404
    conn.request("PUT", "/tick", body=b"{}"); r = conn.getresponse(); r.read(); assert r.status == 405
    conn.request("POST", "/health"); r = conn.getresponse(); r.read(); assert r.status == 405
    conn.request("GET", "/health", body=b'{"junk": 1}'); r = conn.getresponse(); r.read()    # GET 帶 body：讀掉，不毒化下一個請求
    assert r.status == 200 and _post(conn, "/aar/skip")[0] == 409                              # adopt 過了 → 409（連線仍乾淨）
    conn.request("HEAD", "/status"); r = conn.getresponse(); r.read()
    assert r.status == 405 and r.getheader("Connection") == "close"
    conn.close(); conn = http.client.HTTPConnection("127.0.0.1", conn.port, timeout=15)
    conn.request("POST", "/tick", body=b"{}", headers={"Content-Length": "abc"}); r = conn.getresponse()
    assert r.status == 400 and "Content-Length" in json.loads(r.read())["error"]
    conn.close(); conn = http.client.HTTPConnection("127.0.0.1", conn.port, timeout=15)        # 壞長度後服務關了那條連線
    assert _post(conn, "/shutdown")[1]["bye"]
    th.join(timeout=10)
    assert not th.is_alive()


def test_http_token_required(workdir):
    th, conn = _serve(workdir, idle_exit_s=0, token="t0k3n")
    conn.request("GET", "/health"); r = conn.getresponse(); assert r.status == 200 and json.loads(r.read())["auth"] is True
    assert _post(conn, "/session/start", {"board": BOARD})[0] == 401
    assert _post(conn, "/session/start", {"board": BOARD}, headers={"X-Chief-Token": "t0k3n"})[0] == 200
    assert _post(conn, "/shutdown")[0] == 401 and _post(conn, "/shutdown", headers={"X-Chief-Token": "t0k3n"})[1]["bye"]
    th.join(timeout=10)
    assert not th.is_alive()


def test_idle_exit_waits_for_in_flight_request(workdir, monkeypatch):
    """審查 7：長 LLM 呼叫中不得閒置退出；請求結束後才重新計時。"""
    from chief.gateway import FakeGateway
    orig = FakeGateway.issue_orders
    def slow(self, messages):
        time.sleep(2.2)
        return orig(self, messages)
    monkeypatch.setattr(FakeGateway, "issue_orders", slow)
    th, conn = _serve(workdir, idle_exit_s=1.0)                                                   # 輪詢 0.5 秒
    assert _post(conn, "/session/start", {"board": BOARD})[0] == 200
    t0 = time.time()
    code, tick = _post(conn, "/tick", {"board": BOARD, "t": 120})
    assert code == 200 and len(tick["orders"]) == 3 and time.time() - t0 >= 2.0 and th.is_alive()
    th.join(timeout=10)                                                                           # 之後才閒置退出
    assert not th.is_alive()


def test_parent_pid_watch_exits_when_parent_dies(workdir):
    """施工單 17 審查 1：Godot 被殺（或編輯器停止）→ 服務靠 --parent-pid 自己退出，不留孤兒。"""
    import os
    import subprocess
    import sys
    from chief.serve import pid_alive
    assert pid_alive(os.getpid()) and not pid_alive(0) and not pid_alive(2 ** 22 + 12345)
    dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        assert pid_alive(dummy.pid)
        th, conn = _serve(workdir, idle_exit_s=0, parent_pid=dummy.pid, parent_poll_s=0.2)
        conn.request("GET", "/health"); r = conn.getresponse(); assert r.status == 200; r.read()
        dummy.kill(); dummy.wait()
        th.join(timeout=10)
        assert not th.is_alive()                                                                   # 父程序沒了 → 服務退出
    finally:
        if dummy.poll() is None:
            dummy.kill()
    if sys.platform.startswith("linux"):                                                             # 殭屍不算活著（Godot 不一定 wait 它開的子程序）
        zombie = subprocess.Popen([sys.executable, "-c", "pass"])
        for _ in range(100):
            if Path(f"/proc/{zombie.pid}/stat").read_text().rsplit(")", 1)[-1].split()[0] == "Z":
                break
            time.sleep(0.02)
        assert not pid_alive(zombie.pid)
        zombie.wait()


def test_cli_serve_idle_exit(workdir, capsys):
    from chief.cli import main
    rc_box: dict = {}
    import os
    th = threading.Thread(target=lambda: rc_box.update(rc=main(["serve", "--port", "0", "--idle-exit", "1", "--out-root", str(workdir / "b"), "--ledger", "none", "--token", "x", "--parent-pid", str(os.getpid())])), daemon=True)
    th.start()
    th.join(timeout=20)
    assert not th.is_alive() and rc_box["rc"] == 0
    out = capsys.readouterr().out
    assert "參謀長服務 http://127.0.0.1:" in out and "需 X-Chief-Token" in out and f"父程序 {os.getpid()} 消失就退出" in out
