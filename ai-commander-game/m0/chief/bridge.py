"""參謀長服務的核心（施工單 16，ADR-0015 D23）：把 play.py 的每回合流程與戰後流程拆成不靠終端機的方法。

引擎（Godot）每 20 秒送整份戰情板（Board v0.2）過來，這裡做：壓縮快照 → 閘道 → 驗證器 → 計費 → 推翻後果判定；
戰後：戰報卡 → 一句話 → 討論 → 準則 diff → 採納（回歸退步自動回滾）→ 戰例進戰例庫。
所有狀態都在 ChiefSession 裡；每場一個 battles/<id>-<時間>/ 資料夾（usage.jsonl、llm_log.jsonl、overrides.jsonl、t<n>.json、aar.json）。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, Optional

from pydantic import BaseModel, ValidationError

from .badges import award
from .board import Board, BoardError, board_from_dict, save_board
from .discussion import quick_replies, system_prompt as discussion_system_prompt
from .doctrine import DoctrineStore, apply_diff, propose_diff, save_aar
from .gateway import make_gateway
from .meter import Ledger, PriceTable, UsageMeter
from .override import OverrideLog, OverrideRecord, TASK_CHOICES, judge_outcome, player_order_problem, target_sector
from .prompts import build_messages, load_doctrine, use_template
from .report import build_card_from, card_dict, card_summary_text, chief_line, first_sentences, objective_hint
from .sim import BattleResult, Order
from .validator import validate_orders

MAX_DISCUSSION_ROUNDS = 3
JUDGE_DELAY_S = 20          # §9：秒制板的推翻後果，至少過一個決策間隔（20 秒）才判，不然「下一拍」可能只隔 1 秒
GATEWAY_ERRORS = (ValueError, NotImplementedError, ImportError)


class ConflictError(BoardError):
    """狀態不對的呼叫（戰後再 tick、adopt 兩次…）→ HTTP 409。"""


class EndResult(BaseModel):
    """`/battle/end` 的 result：先驗再改狀態，壞資料不會留下半套紀錄。"""
    winner: Literal["us", "enemy", "draw"]
    score_us: int
    score_enemy: int
    end_reason: Literal["turns", "strength", "quit"] = "turns"
    battle_id: Optional[str] = None
    turns_played: Optional[int] = None
    strength_us: float = 0.0
    strength_enemy: float = 0.0


@dataclass
class SessionConfig:
    provider: str = "fake"
    model: Optional[str] = None
    harness: str = "default"
    doctrine: Optional[str] = None       # 明確給就不用參謀長包
    lang: str = "zh-TW"
    budget_usd: Optional[float] = None
    effort: Optional[str] = None
    aar_provider: Optional[str] = None
    aar_model: Optional[str] = None
    out_root: str = "battles"
    ledger: Optional[str] = "battles/ledger.jsonl"
    prices: Optional[str] = None


def _time_tag() -> str:
    return time.strftime("%m%d-%H%M%S")


def _validation_text(err: ValidationError) -> str:
    return "；".join(f"{'.'.join(str(x) for x in e['loc']) or '(root)'}：{e['msg']}" for e in err.errors())


class ChiefSession:
    """一場會戰的參謀長：引擎送板、這裡回命令。"""

    def __init__(self, cfg: SessionConfig, board: dict) -> None:
        self.cfg = cfg
        self.gateway = make_gateway(cfg.provider, cfg.model, effort=cfg.effort)
        self.aar_gateway = self._make_aar_gateway()
        self.start_board: Board = board_from_dict(board)
        self.board: Board = self.start_board
        self.lang = cfg.lang
        self.budget_usd = cfg.budget_usd
        self.doctrine_path, self.evals_dir, self.harness_name = self._resolve_doctrine()
        self.doctrine = load_doctrine(self.doctrine_path)
        self.store = DoctrineStore(self.doctrine_path)
        self.out_dir = Path(cfg.out_root) / f"{self.start_board.battle_id}-{_time_tag()}"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        prices_path = cfg.prices or os.path.join(os.path.dirname(__file__), "prices.json")
        self.meter = UsageMeter(prices=PriceTable(prices_path), log_path=self.out_dir / "usage.jsonl")
        self.ledger = Ledger(cfg.ledger) if cfg.ledger else None
        self.overrides = OverrideLog(self.out_dir / "overrides.jsonl")
        self.owner_before: dict[int, Optional[str]] = {}
        self.override_t: dict[int, Optional[float]] = {}   # 推翻當下的遊戲秒（秒制板才有）→ 判定時點（§9）
        self.player_units: set[str] = set()                 # 目前由總司令直轄的單位（再改令不算推翻，§9）
        self.turn = 0
        self.feedback: list[str] = []
        self.chief_orders_total = 0
        self.override_outcomes: list[str] = []
        self.last_orders: dict[str, tuple[int, dict]] = {}   # unit_id -> (拍, 參謀長最近一次對它的令)
        self.budget_hit = False
        self.warned_80 = False
        self.ended = False
        self.result: Optional[BattleResult] = None
        self.card = None
        self.summary = ""
        self.transcript: list[dict] = []
        self.discussion_round = 1
        self.diff = None
        self.aar_started: Optional[float] = None
        self.aar_closed = False          # adopt／skip 做過一次就關門：undo 的「上一版」與 aar.json 不能被第二次呼叫改寫
        save_board(self.start_board, self.out_dir / "t0.json")

    # ---- 建立 ----
    def _make_aar_gateway(self):
        cfg = self.cfg
        if cfg.aar_model or cfg.aar_provider:
            return make_gateway(cfg.aar_provider or cfg.provider, cfg.aar_model, effort=cfg.effort)
        if cfg.provider == "anthropic":
            return make_gateway("anthropic", "claude-sonnet-5-5", effort=cfg.effort)   # 戰後檢討用中階模型（D3）
        return self.gateway

    def _resolve_doctrine(self) -> tuple[str, Optional[Path], str]:
        if self.cfg.doctrine and self.cfg.harness in ("", "none", "-", "off", "default"):
            use_template(None)       # 不用參謀長包就用內建系統提示（上一場的包不得殘留）
            return self.cfg.doctrine, None, "custom"
        if self.cfg.harness in ("", "none", "-", "off"):
            use_template(None)
            return self.cfg.doctrine or "harness/default/doctrine.md", None, "custom"
        from .harness import load_harness
        h = load_harness(self.cfg.harness)
        use_template(h.prompt_path)
        return str(h.doctrine_path), Path(h.evals_dir), self.cfg.harness

    def opening_line(self) -> str:
        return self.store.opening_line()

    def info(self) -> dict:
        return {"battle_id": self.start_board.battle_id, "out_dir": str(self.out_dir), "provider": self.gateway.provider, "model": self.gateway.model,
                "harness": self.harness_name, "doctrine_path": self.doctrine_path, "lang": self.lang, "budget_usd": self.budget_usd,
                "opening_line": self.opening_line()}

    # ---- 每回合 ----
    def _bill(self, gw):
        def _on(usage, latency):
            e = self.meter.record(self.turn, gw.provider, gw.model, usage, latency, phase="aar")
            if self.ledger:
                self.ledger.add(self.start_board.battle_id, gw.provider, gw.model, e.cost_usd, usage)
        return _on

    def _judgeable(self) -> list[OverrideRecord]:
        """§9 判定時點：秒制板＝第一個 t ≥ 推翻時 t + 20 的板；回合制板＝下一拍（含之後補判）。"""
        out = []
        for rec in self.overrides.records:
            if rec.outcome is not None:
                continue
            t_over = self.override_t.get(id(rec))
            if self.board.time_unit == "second" and t_over is not None:
                if self.board.t >= t_over + JUDGE_DELAY_S:
                    out.append(rec)
            elif rec.turn + 1 <= self.turn:
                out.append(rec)
        return out

    def _judge_pending(self) -> list[dict]:
        outcomes = []
        for rec in self._judgeable():
            outcome = judge_outcome(self.board, rec, self.owner_before.get(id(rec)))
            self.overrides.set_outcome(rec, outcome, self.turn)
            self.override_outcomes.append(outcome)
            outcomes.append({"unit_id": rec.unit_id, "turn": rec.turn, "outcome": outcome,
                             "text": f"推翻後果：t{rec.turn} {rec.unit_id} {rec.player_order.get('task')} {rec.player_order.get('target')} → {outcome}"})
        return outcomes

    def _release_player_units(self) -> None:
        """放手：板上不再標 player 的單位（或已不在板上）就不算直轄了，下次接管又算一次推翻。"""
        by_id = {u.id: u for u in self.board.orbat}
        self.player_units = {uid for uid in self.player_units if uid in by_id and by_id[uid].controlled_by == "player"}

    def tick(self, board: dict, t: Optional[float] = None) -> dict:
        """一個決策節拍：回命令（已通過驗證器）與退回理由；順便判到期的推翻後果。"""
        if self.ended:
            raise ConflictError("這場已經結束，不能再 tick（先 /session/start 下一場）")
        self.board = board_from_dict(board)
        self.turn += 1
        save_board(self.board, self.out_dir / f"t{self.turn - 1}.json")   # 這拍開始前的板（戰例庫 snapshot_ref 用）
        self._release_player_units()
        outcomes = self._judge_pending()
        out: dict[str, Any] = {"turn": self.turn, "t": t, "outcomes": outcomes, "orders": [], "rejected": [], "assessment": None,
                               "usage": None, "cost_usd": 0.0, "cost_total_usd": round(self.meter.cost_usd, 6), "latency_s": 0.0,
                               "error": None, "budget_hit": self.budget_hit, "messages": []}
        if self.budget_hit:
            out["error"] = "已達預算上限，參謀長暫停，本回合無新命令"
            return out
        snapshot = self.board.compact()
        messages = build_messages(self.doctrine, snapshot, self.turn, self.lang, self.feedback)
        resp = self.gateway.issue_orders(messages)
        entry = self.meter.record(self.turn, self.gateway.provider, self.gateway.model, resp.usage, resp.latency_s)
        if self.ledger:
            self.ledger.add(self.start_board.battle_id, self.gateway.provider, self.gateway.model, entry.cost_usd, resp.usage)
        with (self.out_dir / "llm_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": self.turn, "provider": self.gateway.provider, "model": self.gateway.model, "attempts": resp.attempts,
                                "error": resp.error, "raw": resp.raw, "usage": resp.usage.__dict__,
                                "prompt_chars": sum(len(m["content"]) for m in messages)}, ensure_ascii=False) + "\n")
        accepted, rejected = [], []
        if resp.orders is not None:
            accepted, rejected = validate_orders(self.board, resp.orders.sim_orders())
            out["assessment"] = resp.orders.assessment
        else:
            out["error"] = resp.error or "參謀長無回應"
        self.feedback = [r.line() for r in rejected]
        if resp.orders is None:
            self.feedback.append("Your previous reply could not be parsed. Reply with ONLY the JSON object: no prose, no code fences.")
        self.chief_orders_total += len(accepted)
        for o in accepted:
            self.last_orders[o.unit_id] = (self.turn, o.model_dump())
        out["orders"] = [o.model_dump() for o in accepted]
        out["rejected"] = [r.line() for r in rejected]
        out["usage"] = resp.usage.__dict__
        out["cost_usd"] = entry.cost_usd
        out["latency_s"] = resp.latency_s
        out["cost_total_usd"] = round(self.meter.cost_usd, 6)
        if self.budget_usd is not None:
            if self.meter.cost_usd >= self.budget_usd:
                self.budget_hit = True
                out["messages"].append(f"本場費用 ${self.meter.cost_usd:.4f} 已達預算 ${self.budget_usd:.2f}，下回合起參謀長暫停")
            elif not self.warned_80 and self.meter.cost_usd >= 0.8 * self.budget_usd:
                self.warned_80 = True
                out["messages"].append(f"提醒：本場費用 ${self.meter.cost_usd:.4f} 已達預算 80%")
        out["budget_hit"] = self.budget_hit
        return out

    def _ai_order_for(self, unit_id: str, ai_order: Optional[dict]) -> Optional[dict]:
        """被推翻的參謀長命令：明示的 > 本單位或任一上級最近的令（連令拆到排，取最近一拍）> 板上的 task > None。同 play.py。"""
        if ai_order is not None:
            return dict(ai_order)
        by_id = {u.id: u for u in self.board.orbat}
        best: Optional[tuple[int, dict]] = None
        uid, seen = unit_id, set()
        while uid and uid not in seen:
            seen.add(uid)
            hit = self.last_orders.get(uid)
            if hit and (best is None or hit[0] > best[0]):
                best = hit
            u = by_id.get(uid)
            uid = u.parent if u else None
        if best:
            return best[1]
        u = by_id.get(unit_id)
        return {"task": u.task.type, "target": u.task.target} if u and u.task else None

    def override(self, unit_id: str, player_order: dict, board: Optional[dict] = None, ai_order: Optional[dict] = None,
                 t: Optional[float] = None) -> dict:
        """總司令推翻／接管：先驗命令（同 play.py 的 player_order_problem），記到 overrides.jsonl；一個決策間隔後判後果。
        已直轄單位再改令不算推翻（§9）：以上一次收到的板的 controlled_by 與本場直轄清單判斷。
        推翻秒＝t（引擎給的）＞附帶板的 t ＞ 上一拍板的 t；不帶 t 也不帶板時判定會退化成「下一拍」。"""
        if self.ended:
            raise ConflictError("這場已經結束，不能再推翻")
        if t is not None and not isinstance(t, (int, float)):
            raise BoardError("t 要是數字（遊戲秒）")
        task, target = player_order.get("task"), player_order.get("target")
        if task not in TASK_CHOICES:
            raise BoardError(f"任務 {task!r} 不合法（可用：{'、'.join(TASK_CHOICES)}）")
        if not isinstance(target, str) or not target.strip():
            raise BoardError("目標 target 不能是空的（分區 id 如 C3；support 給友軍單位 id）")
        prev_board = self.board
        if board is not None:
            self.board = board_from_dict(board)
        try:
            unit = self.board.unit(unit_id)
        except KeyError:
            raise BoardError(f"單位 {unit_id} 不在戰情板上") from None
        problem = player_order_problem(self.board, Order(unit_id=unit_id, task=task, target=target.strip(), issuer="player"))
        if problem:
            raise BoardError(problem)
        clean = {"task": task, "target": target.strip()}
        try:
            prev_ctrl = prev_board.unit(unit_id).controlled_by
        except KeyError:
            prev_ctrl = None
        counted = prev_ctrl != "player" and unit_id not in self.player_units
        self.player_units.add(unit_id)
        ai = self._ai_order_for(unit_id, ai_order)
        turn = max(self.turn, 1)
        base = {"turn": turn, "unit_id": unit_id, "ai_order": ai, "player_order": clean}
        if not counted:
            return {**base, "recorded": len(self.overrides.records), "counted": False, "override_rate": self.override_rate(),
                    "message": "已直轄單位改令，不算推翻（§9）"}
        t_at = float(t) if t is not None else (float(self.board.t) if self.board.time_unit == "second" else None)
        rec = OverrideRecord(turn=turn, unit_id=unit_id, ai_order=ai, player_order=clean,
                             snapshot_ref=str(self.out_dir / f"t{turn - 1}.json"), strength_at=round(unit.strength, 4), t_at=t_at)
        self.overrides.add(rec)
        sector = target_sector(self.board, clean)
        self.owner_before[id(rec)] = self.board.map.sectors[sector].owner if sector and sector in self.board.map.sectors else None
        self.override_t[id(rec)] = t_at
        return {**base, "recorded": len(self.overrides.records), "counted": True, "override_rate": self.override_rate()}

    def override_rate(self) -> str:
        return f"{len(self.overrides.records)}/{self.chief_orders_total}"

    # ---- 戰後 ----
    def _end_payload(self) -> dict:
        unjudged = sum(1 for r in self.overrides.records if r.outcome is None)
        rnd = min(self.discussion_round, MAX_DISCUSSION_ROUNDS)
        return {"card": card_dict(self.card), "summary": self.summary, "unjudged": unjudged, "quick_replies": quick_replies(self.card, self.lang, rnd)}

    def end(self, board: dict, result: dict) -> dict:
        """會戰結束：戰報卡（離線）。之後可 aar_line → discuss → propose → adopt／skip。重複呼叫回同一張卡。"""
        if self.ended:
            return self._end_payload()
        try:
            res = EndResult.model_validate(result)
        except ValidationError as err:
            raise BoardError(f"result 不合法：{_validation_text(err)}") from None
        final_board = board_from_dict(board)         # 驗完才改狀態；卡片全部算好才一次設 ended（中途例外不留半套）
        result_obj = BattleResult(battle_id=res.battle_id or self.start_board.battle_id, turns_played=res.turns_played if res.turns_played is not None else self.turn,
                                  end_reason=res.end_reason, winner=res.winner, score_us=res.score_us, score_enemy=res.score_enemy,
                                  strength_us=res.strength_us, strength_enemy=res.strength_enemy)
        prev_board = self.board
        self.board = final_board                      # 判後果要用最終板
        judged_now = self._judgeable()
        try:
            outcomes_before = len(self.override_outcomes)
            self._judge_pending()                    # 到期的推翻用最終板判（最後一拍才推翻的留「未判定」，§9）
            play_result = SimpleNamespace(battle=result_obj, meter=self.meter, override_outcomes=self.override_outcomes,
                                          chief_orders_total=self.chief_orders_total, override_rate=self.override_rate())
            battle_ns = SimpleNamespace(board=final_board, out_dir=self.out_dir)
            start_us = {o.id for o in self.start_board.objectives if o.owner == "us"}
            end_us = {o.id for o in final_board.objectives if o.owner == "us"}
            badges = award(result_obj.winner, self.override_outcomes, len(self.overrides.records), self.meter.cost_usd, start_us, end_us,
                           local_model=self.gateway.model.startswith(("ollama", "fake")))
            card = build_card_from(play_result, battle_ns, self.overrides.records, badges, self.gateway)
            card.hint = objective_hint(self.start_board.objectives, final_board.objectives, result_obj.winner, self.lang)
            summary = card_summary_text(card)
        except Exception:
            self.board = prev_board
            del self.override_outcomes[outcomes_before:]
            for rec in judged_now:                   # 剛判的也退回未判定（overrides.jsonl 一起復原）
                rec.outcome, rec.judged_turn = None, None
            if judged_now:
                self.overrides._write()
            raise
        # 最終板：t<拍數>.json（拍數不動）；還沒 tick 就結束 → final.json，別把開局板 t0.json 蓋掉
        save_board(final_board, self.out_dir / (f"t{self.turn}.json" if self.turn > 0 else "final.json"))
        self.result, self.card, self.summary, self.ended = result_obj, card, summary, True
        save_aar(self.out_dir / "aar.json", self.summary, [], None, False, None, card=card_dict(self.card), duration_s=0.0, skipped=True)
        return self._end_payload()

    def _require_card(self) -> None:
        if self.card is None:
            raise BoardError("會戰還沒結束（先呼叫 end）")

    def _require_open(self) -> None:
        self._require_card()
        if self.aar_closed:
            raise ConflictError("戰後流程已結束（已採納或已跳過）")

    def _start_clock(self) -> None:
        """「戰後 < 2 分鐘」從玩家開始互動算（參謀長那句話的延遲不算進去），同 play.py。"""
        if self.aar_started is None:
            self.aar_started = time.perf_counter()

    def aar_line(self) -> dict:
        self._require_card()
        line = chief_line(self.gateway, self.card, self.doctrine, self.lang, on_usage=self._bill(self.gateway))
        if line:
            self.card.chief_line = line
        self._start_clock()
        return {"chief_line": line, "cost_usd": self._aar_cost()}

    def discuss(self, text: Optional[str] = None, index: Optional[int] = None) -> dict:
        """一回合討論：text 或快速回覆編號（1～3）。最多三回合；回覆截到兩句。"""
        self._require_open()
        self._start_clock()
        if self.discussion_round > MAX_DISCUSSION_ROUNDS:
            return {"done": True, "round": self.discussion_round - 1, "reply": None, "next_quick": [], "cost_usd": self._aar_cost()}
        options = quick_replies(self.card, self.lang, self.discussion_round)
        if index is not None:
            if not (1 <= int(index) <= len(options)):
                raise BoardError(f"快速回覆編號要在 1～{len(options)}")
            text = options[int(index) - 1]
        if not text or not str(text).strip():
            raise BoardError("討論內容是空的")
        self.transcript.append({"role": "user", "content": str(text).strip()})
        system = discussion_system_prompt(self.card, self.doctrine, self.lang)
        resp = self.gateway.chat([{"role": "system", "content": system}] + self.transcript)
        self._bill(self.gateway)(resp.usage, resp.latency_s)
        reply = first_sentences(resp.text, 2) if not resp.error else f"（參謀長無回應：{resp.error}）"
        self.transcript.append({"role": "assistant", "content": reply})
        self.discussion_round += 1
        done = self.discussion_round > MAX_DISCUSSION_ROUNDS
        return {"reply": reply, "round": self.discussion_round - 1, "done": done,
                "next_quick": [] if done else quick_replies(self.card, self.lang, self.discussion_round), "cost_usd": self._aar_cost()}

    def propose(self) -> dict:
        self._require_open()
        self._start_clock()
        resp = propose_diff(self.aar_gateway, self.doctrine, self.summary, self.transcript, self.lang)
        self._bill(self.aar_gateway)(resp.usage, resp.latency_s)
        if resp.parsed is None:
            self.diff = None
            return {"error": f"準則更新失敗：{resp.error}", "diff": None, "provider": self.aar_gateway.provider, "model": self.aar_gateway.model,
                    "cost_usd": self._aar_cost()}
        self.diff = resp.parsed
        d = self.diff.model_dump()
        d["empty"] = not self.diff.add and not self.diff.remove
        return {"diff": d, "error": None, "provider": self.aar_gateway.provider, "model": self.aar_gateway.model, "cost_usd": self._aar_cost()}

    def adopt(self) -> dict:
        """套用 diff → 回歸（退步自動回滾）→ aar.json → 戰例進戰例庫。只能做一次。"""
        self._require_open()
        if self.diff is None:
            raise BoardError("還沒有準則提案（先呼叫 propose）")
        messages: list[str] = []
        report = None
        adopted = bool(self.diff.add or self.diff.remove)
        if adopted:
            new_text, report = apply_diff(self.store.load(), self.diff)
            self.store.save(new_text)
            messages.append(f"準則已更新：新增 {report['added']}、刪除 {report['removed']}"
                            + (f"、因超過上限淘汰 {report['trimmed']}" if report.get("trimmed") else "") + f"（{report['chars']}/2000 字）")
            if report.get("ignored_removes"):
                messages.append(f"略過 {len(report['ignored_removes'])} 條找不到或太短的刪除：{'；'.join(report['ignored_removes'])}")
            if self.evals_dir:
                from .play import regression_check_core
                regressed = regression_check_core(self.gateway, self.store, self.evals_dir, self.lang, self._bill(self.gateway),
                                                  lambda text, style=None: messages.append(text))
                if regressed:
                    report["rolled_back"] = True
        else:
            messages.append("沒有變更。")
        self._finish_aar(adopted, report, skipped=False)
        return {"adopted": adopted, "rolled_back": bool(report and report.get("rolled_back")), "report": report, "messages": messages,
                "duration_s": self._aar_duration(), "cost_usd": self._aar_cost(), "doctrine": self.store.load()}

    def skip(self) -> dict:
        self._require_open()
        self._finish_aar(False, None, skipped=True)
        return {"skipped": True, "duration_s": self._aar_duration()}

    def undo(self) -> dict:
        ok = self.store.undo()
        return {"undone": ok, "doctrine": self.store.load() if ok else None, "message": "已還原上一版準則" if ok else "沒有上一版可還原"}

    def _finish_aar(self, adopted: bool, report: Optional[dict], skipped: bool) -> None:
        save_aar(self.out_dir / "aar.json", self.summary, self.transcript, self.diff, adopted, report, card=card_dict(self.card),
                 duration_s=self._aar_duration(), skipped=skipped)
        self._write_cases()     # 這場的推翻進戰例庫（§12）——回歸之後才寫
        self.aar_closed = True

    def _write_cases(self) -> None:
        if self.evals_dir and self.overrides.records:
            from .evals import build_cases_from_battle, save_cases
            save_cases(build_cases_from_battle(self.out_dir), Path(self.evals_dir) / "cases.jsonl")

    def close(self) -> None:
        """會話被換掉／服務退出前：出了卡卻沒走到採納或跳過（玩家直接關遊戲、開下一場）→ 戰例仍進戰例庫，同 play.py 一定寫。"""
        if self.ended and self.card is not None and not self.aar_closed:
            self._write_cases()
            self.aar_closed = True

    def _aar_duration(self) -> float:
        return round(time.perf_counter() - self.aar_started, 1) if self.aar_started else 0.0

    def _aar_cost(self) -> float:
        return round(sum(e.cost_usd for e in self.meter.entries if e.phase == "aar"), 6)

    # ---- 狀態與設定 ----
    def status(self) -> dict:
        tot = self.ledger.totals() if self.ledger else {"today": 0.0, "month": 0.0}
        return {"battle_id": self.start_board.battle_id, "provider": self.gateway.provider, "model": self.gateway.model, "lang": self.lang,
                "turn": self.turn, "cost_usd": round(self.meter.cost_usd, 6), "prompt_tokens": self.meter.prompt_tokens,
                "completion_tokens": self.meter.completion_tokens, "estimated": self.meter.estimated, "today_usd": round(tot["today"], 6),
                "month_usd": round(tot["month"], 6), "budget_usd": self.budget_usd, "budget_hit": self.budget_hit,
                "overrides": len(self.overrides.records), "chief_orders_total": self.chief_orders_total, "override_rate": self.override_rate(),
                "player_units": sorted(self.player_units), "ended": self.ended, "aar_closed": self.aar_closed, "out_dir": str(self.out_dir)}

    def _settings_payload(self, error: Optional[str] = None) -> dict:
        return {"error": error, "provider": self.gateway.provider, "model": self.gateway.model, "lang": self.lang, "budget_usd": self.budget_usd,
                "effort": self.cfg.effort, "aar_provider": self.aar_gateway.provider, "aar_model": self.aar_gateway.model}

    def settings(self, provider: Optional[str] = None, model: Optional[str] = None, lang: Optional[str] = None,
                 budget_usd: Optional[float] = None, effort: Optional[str] = None, aar_provider: Optional[str] = None,
                 aar_model: Optional[str] = None) -> dict:
        """換供應商／模型（重建閘道）、戰後閘道、語言、預算、思考深度；哪一段失敗就保留那段原設定並回 error。
        不會失敗的（語言、預算）先套用，閘道失敗不會把同一請求的語言／預算丟掉。"""
        if lang:
            self.lang = lang
        if budget_usd is not None:
            self.budget_usd = float(budget_usd) if budget_usd >= 0 else None
            self.budget_hit = self.budget_usd is not None and self.meter.cost_usd >= self.budget_usd
        if provider or model or effort:
            try:
                gw = make_gateway(provider or self.cfg.provider, model or (self.cfg.model if not provider else None), effort=effort or self.cfg.effort)
            except GATEWAY_ERRORS as err:
                return self._settings_payload(f"閘道設定失敗：{err}")
            self.gateway = gw
            self.cfg.provider, self.cfg.model, self.cfg.effort = gw.provider, gw.model, effort or self.cfg.effort
        if aar_provider or aar_model or provider or model or effort:
            old = (self.cfg.aar_provider, self.cfg.aar_model)
            if aar_provider or aar_model:
                self.cfg.aar_provider, self.cfg.aar_model = aar_provider or self.cfg.aar_provider, aar_model
            try:
                self.aar_gateway = self._make_aar_gateway()
            except GATEWAY_ERRORS as err:
                self.cfg.aar_provider, self.cfg.aar_model = old
                return self._settings_payload(f"戰後閘道設定失敗：{err}")
        return self._settings_payload()
