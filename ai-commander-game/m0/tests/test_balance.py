"""施工單 09：平衡與截斷。期望值來自 docs/10-sim-rules.md §2（潰散撤出）、§14（難度劇本對打結果）、§11（提示）與施工單 09 驗收清單。"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from chief.board import Board, MapGrid, Sector, Task, Unit, load_board, Objective
from chief.deploy import apply_plan, plan_from_template
from chief.gateway.anthropic_adapter import AnthropicGateway, BREVITY_NOTE, MAX_TOKENS
from chief.orders import ChiefOrders
from chief.prompts import build_messages, score_line, system_prompt, user_prompt
from chief.report import BattleCard, objective_hint, render_card, card_summary_text
from chief.rules import load_rules
from chief.sim import Battle, Script, load_script

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
RULES = load_rules()


def grid() -> MapGrid:
    sectors = {}
    for r in range(1, 6):
        for c in range(5):
            sid = f"{'ABCDE'[c]}{r}"
            sectors[sid] = Sector(id=sid, terrain="open", cover=0.2)
    return MapGrid(cols=5, rows=5, sectors=sectors)


def plt(uid, sector, typ="infantry", task=None, strength=1.0, state="idle") -> Unit:
    return Unit(id=uid, name=uid, echelon="platoon", type=typ, sector=sector, task=task, strength=strength, state=state)


# ---- §2 v1.1：潰散單位撤出有敵軍的分區（效果：不再分攤火力）----
def test_routed_unit_leaves_contested_sector_and_stops_absorbing_fire(tmp_path):
    """守軍 1.0 旁邊有 0.2 的潰散單位：潰散者退走後，守軍吃滿 1.0×1.0×0.8×0.25 = 0.20（留著當肉盾只剩 0.1667）。"""
    g = grid(); g.sectors["C3"].owner = "enemy"; g.sectors["D3"].owner = "enemy"
    us = [plt("u", "C3", task=Task(type="hold", target="C3"))]
    en = [plt("d", "C3", task=Task(type="hold", target="C3")), plt("e", "C3", strength=0.2, state="routed")]
    battle = Battle(Board(battle_id="b", t=0, map=g, orbat=us, objectives=[]), en, out_dir=tmp_path)
    rep = battle.step([], [])
    routed = next(x for x in battle.enemy if x.id == "e")
    assert routed.sector == "D3"                                    # 退到最近沒有敵軍（我方）的本方分區
    assert "e" not in rep.damage and rep.damage["d"] == pytest.approx(0.20, abs=1e-4)


def test_routed_unit_retreat_path_avoids_hostile_sectors(tmp_path):
    """我方潰散排在 A3，唯一安全本方格 A1，敵軍在 A2 → 不穿 A2，繞 B3（BFS 避開敵格的第一步）。"""
    g = grid(); g.sectors["A1"].owner = "us"
    us = [plt("r", "A3", strength=0.2, state="routed")]
    en = [plt("e", "A2", task=Task(type="hold", target="A2"))]
    battle = Battle(Board(battle_id="b", t=0, map=g, orbat=us, objectives=[]), en, out_dir=tmp_path)
    battle.step([], [])
    assert battle.board.unit("r").sector == "B3"


def test_routed_unit_with_no_safe_sector_stays(tmp_path):
    g = grid(); g.sectors["C3"].owner = "enemy"
    us = [plt("u", "C3", task=Task(type="hold", target="C3"))]
    en = [plt("e", "C3", strength=0.2, state="routed")]
    battle = Battle(Board(battle_id="b", t=0, map=g, orbat=us, objectives=[]), en, out_dir=tmp_path)
    battle.step([], [])
    assert battle.enemy[0].sector == "C3"


# ---- §14 難度劇本對打（無隨機）----
def run_assault(enemy_file: str, out: Path):
    board = apply_plan(load_board(SAMPLES / "board_start.json"), plan_from_template(RULES, "balanced"), RULES)
    friendly = load_script(SAMPLES / "orders_v1_assault.json")
    enemy = load_script(SAMPLES / enemy_file)
    return Battle(board, enemy.units, out_dir=out).run(friendly, enemy)


@pytest.mark.parametrize("enemy_file,winner,score,end", [
    ("enemy_v1_easy.json", "us", (8, 3), "turns"),
    ("enemy_script_v1.json", "us", (8, 3), "turns"),
    ("enemy_v1_hard.json", "enemy", (3, 8), "turns"),
])
def test_assault_plan_vs_difficulties(tmp_path, enemy_file, winner, score, end):
    r = run_assault(enemy_file, tmp_path / enemy_file)
    assert (r.winner, (r.score_us, r.score_enemy), r.end_reason) == (winner, score, end)


def test_difficulty_scripts_match_their_description():
    easy = load_script(SAMPLES / "enemy_v1_easy.json"); hard = load_script(SAMPLES / "enemy_v1_hard.json")
    assert not {u.type for u in easy.units} & {"tank", "mortar"}
    assert all(o.target != "B2" for os in easy.orders.values() for o in os)          # §14：easy 只守 C3、不推 B2
    assert sum(1 for u in hard.units if u.type == "tank") == 2 and hard.weather_changes
    assert any(o.target == "C2" for o in hard.for_turn(1))                            # §14：hard 第 1 回合就壓 C2


def test_cli_difficulty_flag(tmp_path, capsys):
    from chief.cli import main
    rc = main(["sim", "--orders", str(SAMPLES / "orders_v1_assault.json"), "--template", "balanced", "--difficulty", "hard", "--quiet", "--out", str(tmp_path / "h")])
    assert rc == 0 and "敵方勝" in capsys.readouterr().out
    rc = main(["sim", "--orders", str(SAMPLES / "orders_v1_assault.json"), "--template", "balanced", "--difficulty", "easy", "--quiet", "--out", str(tmp_path / "e")])
    assert rc == 0 and "我方勝" in capsys.readouterr().out
    # 明確給 --enemy 時 --difficulty 不生效：02 舊劇本對舊板是我方勝 8:3（hard 會是敵方勝）
    rc = main(["sim", "--orders", str(SAMPLES / "orders_scripted.json"), "--enemy", str(SAMPLES / "enemy_script.json"), "--difficulty", "hard", "--quiet", "--out", str(tmp_path / "o")])
    assert rc == 0 and "我方勝" in capsys.readouterr().out
    import argparse
    from chief.cli import build_parser
    assert "--difficulty" not in [a.option_strings[0] for a in build_parser()._subparsers._group_actions[0].choices["deploy"]._actions if a.option_strings]


# ---- 提示：分數與剩餘回合；精簡要求 ----
def test_score_line_in_user_prompt():
    snap = {"objectives": [{"id": "O1", "sector": "B2", "value": 3, "owner": "us"}, {"id": "O2", "sector": "C3", "value": 5, "owner": "enemy"},
                           {"id": "O3", "sector": "D4", "value": 3, "owner": "enemy"}], "map": {"sectors": {"A1": "open/us"}}, "friendly": []}
    line = score_line(snap, 3)
    assert "Score now: us 3 : enemy 8" in line and "O2 (5 pts at C3, enemy)" in line and "Turns left including this one: 8" in line
    assert "You do not win on points unless you seize at least one more objective" in line
    unowned = dict(snap); unowned["objectives"] = [{"id": "O2", "sector": "C3", "value": 5, "owner": "none"}]
    assert "O2 (5 pts at C3, unowned)" in score_line(unowned, 1)
    assert "Score now" in user_prompt(snap, 3)
    ahead = dict(snap); ahead["objectives"] = [{"id": "O1", "sector": "B2", "value": 5, "owner": "us"}, {"id": "O2", "sector": "C3", "value": 3, "owner": "enemy"}]
    assert "unless you seize" not in score_line(ahead, 10) and "Turns left including this one: 1" in score_line(ahead, 10)
    secs = dict(snap); secs.update(t=120, unit="second")                                          # 施工單 16：Godot 秒制板
    assert "Time left: about 180 s of 300 (roughly 9 more decisions" in score_line(secs, 11) and "Turns left" not in score_line(secs, 11)
    assert user_prompt(secs, 11).startswith("Decision 11 (t=120 s).") and "Time left: about 0 s of 300 (roughly 0 more" in score_line({**secs, "t": 300}, 16)


def test_system_prompt_asks_for_brevity_and_points():
    sp = system_prompt("(no doctrine yet)")
    assert "<=120 chars" in sp and "well under 600 characters" in sp and "concentrate at least three platoons" in sp


# ---- 截斷重試（假 client，不連網）----
class SeqMessages:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _resp(stop, parsed=None, cache_read=0):
    return SimpleNamespace(parsed_output=parsed, stop_reason=stop,
                           usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=cache_read, cache_creation_input_tokens=0),
                           content=[SimpleNamespace(type="text", text="{}")])


class RaisingMessages:
    def __init__(self, err):
        self.err, self.calls = err, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        raise self.err


def test_truncated_reply_is_retried_once_with_brevity_note():
    good = ChiefOrders(assessment="短", orders=[{"unit_id": "plt-A1", "task": "seize", "target": "C3", "reason": ""}])
    client = SimpleNamespace(messages=SeqMessages([_resp("max_tokens", cache_read=900), _resp("end_turn", good, cache_read=900)]))
    gw = AnthropicGateway(model="claude-haiku-5-5", client=client)
    resp = gw.issue_orders(build_messages("d", {"t": 1}, 1))
    assert resp.error is None and resp.orders.orders[0].task == "seize" and resp.attempts == 2
    assert resp.usage.prompt_tokens == 2000 and resp.usage.completion_tokens == 400 and resp.usage.cache_read_tokens == 1800   # 兩次都計費
    assert client.messages.calls[0]["max_tokens"] == MAX_TOKENS == 4096
    second = client.messages.calls[1]["messages"]
    assert len(second) == 1 and second[-1]["content"].endswith(BREVITY_NOTE)               # 併進同一則 user 訊息


def test_api_error_mentioning_max_tokens_is_not_retried():
    import anthropic
    err = anthropic.BadRequestError.__new__(anthropic.BadRequestError)   # 不建 HTTP 回應，只要型別與訊息
    err.args = ("max_tokens: 4096 exceeds the model limit",)
    err.status_code = 400
    client = SimpleNamespace(messages=RaisingMessages(err))
    resp = AnthropicGateway(client=client).issue_orders(build_messages("d", {}, 1))
    assert resp.orders is None and resp.attempts == 1 and len(client.messages.calls) == 1 and "截斷" not in resp.error


def test_truncated_twice_reports_plainly():
    client = SimpleNamespace(messages=SeqMessages([_resp("max_tokens"), _resp("max_tokens")]))
    resp = AnthropicGateway(client=client).issue_orders(build_messages("d", {}, 1))
    assert resp.orders is None and resp.attempts == 2 and "精簡重試 1 次" in resp.error and "本回合無新命令" in resp.error


# ---- §11 戰報卡提示 ----
def objs(**owners):
    base = {"O1": ("B2", 3), "O2": ("C3", 5), "O3": ("D4", 3)}
    return [Objective(id=k, sector=base[k][0], value=base[k][1], owner=owners.get(k, "none")) for k in base]


def test_objective_hint_only_when_nothing_new_taken_and_not_won():
    start = objs(O1="us", O3="enemy")
    assert "O2（5 分，C3）戰後仍是敵方" in objective_hint(start, objs(O1="us", O2="enemy", O3="enemy"), "enemy")
    assert objective_hint(start, objs(O1="us", O2="us", O3="enemy"), "enemy") == ""        # 拿下過 O2 就不提示
    assert objective_hint(start, objs(O1="us", O2="enemy", O3="enemy"), "us") == ""         # 贏了不提示
    assert "ended enemy-held" in objective_hint(start, objs(O1="us", O2="enemy", O3="enemy"), "enemy", "en")


def test_hint_shows_on_card_and_in_summary_and_quick_reply():
    from chief.discussion import quick_replies
    from rich.console import Console
    card = BattleCard(battle_id="x", winner="enemy", score_us=3, score_enemy=8, turns=10, end_reason="turns", overrides=0,
                      override_rate="0/10", cost_usd=0.0, provider="fake", model="fake", hint="整場沒有奪取任何新據點：O2")
    c = Console(record=True, width=120); c.print(render_card(card)); out = c.export_text()
    assert "提示：整場沒有奪取任何新據點" in out and "hint=整場沒有奪取任何新據點" in card_summary_text(card)
    assert quick_replies(card, "zh-TW", 1)[0] == "為什麼整場沒去拿新據點？" and quick_replies(card, "en", 1)[0].startswith("Why did we never")
    card.hint = ""
    assert quick_replies(card, "zh-TW", 1)[0] != "為什麼整場沒去拿新據點？"


def test_play_fills_hint_in_auto_mode(tmp_path):
    from chief.cli import main
    rc = main(["play", "--provider", "fake", "--model", "fake/empty", "--auto", "--quiet", "--harness", "", "--ledger", "",
               "--template", "balanced", "--difficulty", "normal", "--out", str(tmp_path / "p")])
    assert rc == 0
    aar = json.loads((tmp_path / "p" / "aar.json").read_text(encoding="utf-8"))
    card = aar.get("card", aar)
    assert "O2（5 分，C3）" in card["hint"]                                               # 空劇本不動 → 沒拿 C3 → 提示


# ---- chief replay（回放，離線）----
def test_replay_prints_orders_and_key_events(tmp_path, capsys):
    from chief.cli import main
    assert main(["play", "--provider", "fake", "--auto", "--skip-aar", "--quiet", "--harness", "", "--ledger", "",
                 "--template", "balanced", "--difficulty", "normal", "--out", str(tmp_path / "b")]) == 0
    capsys.readouterr()
    assert main(["replay", str(tmp_path / "b")]) == 0
    out = capsys.readouterr().out
    assert "共 10 回合" in out and "t1 " in out and "令：A1 步兵排 奪取 C3" in out and "[seized]" in out
    assert "[contact]" not in out
    assert main(["replay", str(tmp_path / "b"), "--all"]) == 0 and "[contact]" in capsys.readouterr().out
    assert main(["replay", str(tmp_path / "nothing")]) == 1


def test_harness_and_ledger_accept_none_for_powershell(tmp_path, capsys):
    from chief.cli import main
    rc = main(["play", "--provider", "fake", "--model", "fake/empty", "--auto", "--skip-aar", "--quiet", "--harness", "none", "--ledger", "none",
               "--doctrine", str(SAMPLES / "doctrine_fresh.md"), "--template", "balanced", "--difficulty", "normal", "--out", str(tmp_path / "p")])
    assert rc == 0 and (tmp_path / "p" / "t1.json").exists() and not Path("none").exists()
