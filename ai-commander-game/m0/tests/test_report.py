"""施工單 06 驗收：戰報卡、徽章、討論、準則。期望值來自 docs/10-sim-rules.md §11 與手算。"""
from __future__ import annotations

from pathlib import Path

from rich.console import Console

from chief.badges import award
from chief.board import Event
from chief.discussion import run_discussion
from chief.doctrine import DoctrineDiff, DoctrineLine, DoctrineStore, apply_diff
from chief.gateway import FakeGateway
from chief.override import OverrideRecord
from chief.report import BattleCard, first_sentences, pick_moments


def rec(turn, unit, outcome=None):
    return OverrideRecord(turn=turn, unit_id=unit, ai_order={"unit_id": unit, "task": "seize", "target": "C3"},
                          player_order={"unit_id": unit, "task": "hold", "target": "B2"}, snapshot_ref="x", strength_at=1.0, outcome=outcome)


def test_moments_prefer_overrides_then_turning_points():
    events = [Event(t=2, kind="seized", text="敵方取得 C3"), Event(t=4, kind="routed", text="我方 A2 排潰散"), Event(t=5, kind="order", text="x")]
    ms = pick_moments([rec(1, "plt-A3", "👍"), rec(3, "plt-A1", "➖")], events)
    assert [m.kind for m in ms] == ["override", "override", "turning"] and ms[2].t == 2
    assert ms[0].ai_text == "奪取 C3" and ms[0].player_text == "固守 B2" and ms[0].outcome == "👍"


def test_badges_hand_examples():
    b = award("us", ["👍", "👍"], 2, 0.0, {"O1"}, {"O1", "O2"})
    assert {x.id for x in b} == {"decisive", "thrifty_winner", "ground_holder"}
    assert [x.id for x in award("us", [], 0, 0.5, set(), set())] == ["hands_off"]
    assert award("enemy", ["👍"], 1, 0.0, {"O1"}, {"O1"}) == []                      # 敗局不頒守土
    assert {x.id for x in award("us", [], 1, 0.0, set(), set(), local_model=True)} == {"local_hero"}   # 本地模型不給省錢贏家


def test_first_sentences_truncates_to_two():
    assert first_sentences("第一句。第二句！第三句？") == "第一句。第二句！"
    assert first_sentences("Only one sentence") == "Only one sentence"
    assert first_sentences("Hold B2. Then push. Done.") == "Hold B2. Then push."
    assert first_sentences("Cost was $0.01 total. Next time hold. Third.") == "Cost was $0.01 total. Next time hold."
    assert first_sentences("Use e.g. the MG platoon first. Then armor. Last.") == "Use e.g. the MG platoon first. Then armor."


def test_remove_needs_exact_line_or_long_substring():
    base = (Path(__file__).resolve().parent.parent / "harness" / "default" / "doctrine.md").read_text(encoding="utf-8")
    new, rep = apply_diff(base, DoctrineDiff(summary="s", add=[], remove=["e", "the"]), stamp="d")
    assert rep["removed"] == 0 and rep["ignored_removes"] == ["e", "the"] and "Seize the highest-value objective" in new
    new, rep = apply_diff(base, DoctrineDiff(summary="s", add=[], remove=["Keep at least one platoon uncommitted"]), stamp="d")
    assert rep["removed"] == 1 and "uncommitted" not in new


def test_hand_edited_headings_are_recognised_and_notes_kept():
    from chief.doctrine import _split_sections
    title, buckets, last, notes = _split_sections("\ufeff# D\r\n\r\n## Rejected\r\n- r\r\n\r\n## Notes\r\n- keep me\r\n\r\n## Last adopted\r\n\r\n2026-11-01: 摘要\r\n")
    assert buckets["rejected"] == ["- r"] and notes == ["## Notes", "- keep me"] and last == "- 2026-11-01: 摘要"
    new, rep = apply_diff("# D\n\n## Rejected\n- r\n\n## Notes\n- keep me\n", DoctrineDiff(summary="x", add=[], remove=[]), stamp="d")
    assert "- keep me" in new and "- r" in new


def test_discussion_three_rounds_and_two_sentence_replies(tmp_path):
    card = BattleCard("b", "enemy", 3, 8, 10, "turns", 1, "1/5", 0.0, "fake", "fake/none", moments=pick_moments([rec(1, "plt-A3", "👍")], []))
    gw = FakeGateway(chats=["一。二。三。", "好。", "收到。"])
    out = open(tmp_path / "o.txt", "w", encoding="utf-8")
    it = iter(["1", "自由輸入", "3", "4"])
    hist = run_discussion(gw, card, "doc", "zh-TW", Console(file=out, width=100), input_fn=lambda prompt="": next(it, ""))
    assert len(gw.chat_calls) == 3                                   # 第 4 次輸入不會被問
    assert hist[1]["content"] == "一。二。" and hist[0]["content"].startswith("為什麼第①幕")
    assert hist[4]["content"] == "這場先不改準則"                      # 第 3 回合的第 3 個選項（輪替）
    assert gw.chat_calls[0][0]["role"] == "system" and "doc" in gw.chat_calls[0][0]["content"]


def test_apply_diff_adds_removes_and_limits(tmp_path):
    base = "# Doctrine v1\n\n## Commander profile\n- Unknown yet.\n\n## Verified tactics\n- Seize the town early.\n\n## Rejected practices (do not propose)\n- (none yet)\n\n## Hypotheses to test\n- Maybe holds when behind.\n"
    diff = DoctrineDiff(summary="您偏好固守", add=[DoctrineLine(section="profile", text="Prefers holding ground when behind"),
                                                 DoctrineLine(section="rejected", text="Armor alone across the river")],
                        remove=["Seize the town early"])
    new, rep = apply_diff(base, diff, stamp="2026-11-01")
    assert rep["added"] == 2 and rep["removed"] == 1
    assert "- Prefers holding ground when behind" in new and "Seize the town early" not in new and "- (none yet)" not in new.split("## Rejected")[1].split("##")[0]
    assert "## Last adopted\n- 2026-11-01: 您偏好固守" in new
    store = DoctrineStore(tmp_path / "d.md"); store.save(base); store.save(new)
    assert store.opening_line() == "您偏好固守"                        # 開局引用不含日期戳
    assert store.undo() and store.load() == base and not store.undo()


def test_apply_diff_trims_hypotheses_first_when_over_limit():
    hyp = "\n".join(f"- hypothesis {i} " + "x" * 90 for i in range(25))
    base = f"# D\n\n## Commander profile\n- p\n\n## Verified tactics\n- t\n\n## Rejected practices (do not propose)\n- r\n\n## Hypotheses to test\n{hyp}\n"
    new, rep = apply_diff(base, DoctrineDiff(summary="s", add=[DoctrineLine(section="tactic", text="new tactic")], remove=[]), stamp="d")
    assert rep["chars"] <= 2000 and rep["trimmed"] > 0 and "- t" in new and "- new tactic" in new and "hypothesis 0 " not in new


def test_limit_holds_even_when_profile_is_huge_and_new_lines_survive():
    prof = "\n".join(f"- profile {i} " + "y" * 90 for i in range(30))
    base = f"# D\n\n## Commander profile\n{prof}\n\n## Verified tactics\n- t\n"
    new, rep = apply_diff(base, DoctrineDiff(summary="s", add=[DoctrineLine(section="tactic", text="brand new")], remove=[]), stamp="d")
    assert len(new) <= 2000 and "- brand new" in new
