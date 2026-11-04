"""參謀長服務的核心（施工單 16，ADR-0015 D23）：把 play.py 的每回合流程與戰後流程拆成不靠終端機的方法。

引擎（Godot）每 20 秒送整份戰情板（Board v0.2）過來，這裡做：壓縮快照 → 閘道 → 驗證器 → 計費 → 推翻後果判定；
戰後：戰報卡 → 一句話 → 討論 → 準則 diff → 採納（回歸退步自動回滾）→ 戰例進戰例庫。
所有狀態都在 ChiefSession 裡；每場一個 battles/<id>-<時間>/ 資料夾（usage.jsonl、llm_log.jsonl、overrides.jsonl、t<n>.json、aar.json）。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from .badges import award
from .board import Board, BoardError, board_from_dict, save_board
from .discussion import quick_replies, system_prompt as discussion_system_prompt
from .doctrine import DoctrineStore, apply_diff, propose_diff, save_aar
from .gateway import make_gateway
from .meter import Ledger, PriceTable, UsageMeter
from .override import OverrideLog, OverrideRecord, judge_outcome, target_sector
from .prompts import build_messages, load_doctrine, use_template
from .report import build_card_from, card_dict, card_summary_text, chief_line, first_sentences, objective_hint
from .sim import BattleResult
from .validator import validate_orders

MAX_DISCUSSION_ROUNDS = 3


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
        self.turn = 0
        self.feedback: list[str] = []
        self.chief_orders_total = 0
        self.override_outcomes: list[str] = []
        self.last_orders: dict[str, dict] = {}      # unit_id -> 參謀長最近一次對它的令（推翻記錄用）
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
            return self.cfg.doctrine, None, "custom"
        if self.cfg.harness in ("", "none", "-", "off"):
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

    def tick(self, board: dict, t: Optional[float] = None) -> dict:
        """一個決策節拍：回命令（已通過驗證器）與退回理由；順便判上一拍推翻的後果。"""
        if self.ended:
            return {"error": "這場已經結束"}
        self.board = board_from_dict(board)
        self.turn += 1
        save_board(self.board, self.out_dir / f"t{self.turn - 1}.json")   # 這拍開始前的板（戰例庫 snapshot_ref 用）
        outcomes = []
        for rec in self.overrides.pending(self.turn):   # 上一拍的推翻，這拍判後果（§9）
            outcome = judge_outcome(self.board, rec, self.owner_before.get(id(rec)))
            self.overrides.set_outcome(rec, outcome, self.turn)
            self.override_outcomes.append(outcome)
            outcomes.append({"unit_id": rec.unit_id, "turn": rec.turn, "outcome": outcome,
                             "text": f"推翻後果：t{rec.turn} {rec.unit_id} {rec.player_order['task']} {rec.player_order['target']} → {outcome}"})
        out: dict[str, Any] = {"turn": self.turn, "t": t, "outcomes": outcomes, "orders": [], "rejected": [], "assessment": None,
                               "usage": None, "cost_usd": 0.0, "latency_s": 0.0, "error": None, "budget_hit": self.budget_hit, "messages": []}
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
            self.last_orders[o.unit_id] = o.model_dump()
        out["orders"] = [o.model_dump() for o in accepted]
        out["rejected"] = [r.line() for r in rejected]
        out["usage"] = resp.usage.__dict__
        out["cost_usd"] = entry.cost_usd
        out["latency_s"] = resp.latency_s
        out["cost_total_usd"] = self.meter.cost_usd
        if self.budget_usd is not None:
            if self.meter.cost_usd >= self.budget_usd:
                self.budget_hit = True
                out["messages"].append(f"本場費用 ${self.meter.cost_usd:.4f} 已達預算 ${self.budget_usd:.2f}，下回合起參謀長暫停")
            elif not self.warned_80 and self.meter.cost_usd >= 0.8 * self.budget_usd:
                self.warned_80 = True
                out["messages"].append(f"提醒：本場費用 ${self.meter.cost_usd:.4f} 已達預算 80%")
        out["budget_hit"] = self.budget_hit
        return out

    def override(self, unit_id: str, player_order: dict, board: Optional[dict] = None, ai_order: Optional[dict] = None) -> dict:
        """總司令推翻／接管：記錄到 overrides.jsonl；下一拍判後果。ai_order 省略時用參謀長最近一次對它的令。"""
        if board is not None:
            self.board = board_from_dict(board)
        unit = self.board.unit(unit_id) if any(u.id == unit_id for u in self.board.orbat) else None
        if unit is None:
            raise BoardError(f"單位 {unit_id} 不在戰情板上")
        ai = ai_order if ai_order is not None else self.last_orders.get(unit_id)
        rec = OverrideRecord(turn=max(self.turn, 1), unit_id=unit_id, ai_order=ai, player_order=dict(player_order),
                             snapshot_ref=str(self.out_dir / f"t{max(self.turn, 1) - 1}.json"), strength_at=round(unit.strength, 4))
        self.overrides.add(rec)
        sector = target_sector(self.board, player_order)
        self.owner_before[id(rec)] = self.board.map.sectors[sector].owner if sector and sector in self.board.map.sectors else None
        return {"recorded": len(self.overrides.records), "turn": rec.turn, "unit_id": unit_id, "ai_order": ai, "player_order": rec.player_order,
                "override_rate": self.override_rate()}

    def override_rate(self) -> str:
        return f"{len(self.overrides.records)}/{self.chief_orders_total}"

    # ---- 戰後 ----
    def end(self, board: dict, result: dict) -> dict:
        """會戰結束：戰報卡（離線）。之後可 aar_line → discuss → propose → adopt／skip。"""
        if self.ended:
            return {"card": card_dict(self.card), "summary": self.summary}
        self.board = board_from_dict(board)
        self.turn += 1
        save_board(self.board, self.out_dir / f"t{self.turn - 1}.json")
        self.result = BattleResult(battle_id=str(result.get("battle_id", self.start_board.battle_id)), turns_played=int(result.get("turns_played", self.turn)),
                                   end_reason=result.get("end_reason", "turns"), winner=result["winner"], score_us=int(result["score_us"]),
                                   score_enemy=int(result["score_enemy"]), strength_us=float(result.get("strength_us", 0.0)),
                                   strength_enemy=float(result.get("strength_enemy", 0.0)))
        self.ended = True
        play_result = SimpleNamespace(battle=self.result, meter=self.meter, override_outcomes=self.override_outcomes,
                                      chief_orders_total=self.chief_orders_total, override_rate=self.override_rate())
        battle_ns = SimpleNamespace(board=self.board, out_dir=self.out_dir)
        start_us = {o.id for o in self.start_board.objectives if o.owner == "us"}
        end_us = {o.id for o in self.board.objectives if o.owner == "us"}
        badges = award(self.result.winner, self.override_outcomes, len(self.overrides.records), self.meter.cost_usd, start_us, end_us,
                       local_model=self.gateway.model.startswith(("ollama", "fake")))
        self.card = build_card_from(play_result, battle_ns, self.overrides.records, badges, self.gateway)
        self.card.hint = objective_hint(self.start_board.objectives, self.board.objectives, self.result.winner, self.lang)
        self.summary = card_summary_text(self.card)
        self.aar_started = time.perf_counter()
        save_aar(self.out_dir / "aar.json", self.summary, [], None, False, None, card=card_dict(self.card), duration_s=0.0, skipped=True)
        unjudged = sum(1 for r in self.overrides.records if r.outcome is None)
        return {"card": card_dict(self.card), "summary": self.summary, "unjudged": unjudged, "quick_replies": quick_replies(self.card, self.lang, 1)}

    def _require_card(self) -> None:
        if self.card is None:
            raise BoardError("會戰還沒結束（先呼叫 end）")

    def aar_line(self) -> dict:
        self._require_card()
        line = chief_line(self.gateway, self.card, self.doctrine, self.lang, on_usage=self._bill(self.gateway))
        if line:
            self.card.chief_line = line
        return {"chief_line": line, "cost_usd": self._aar_cost()}

    def discuss(self, text: Optional[str] = None, index: Optional[int] = None) -> dict:
        """一回合討論：text 或快速回覆編號（1～3）。最多三回合；回覆截到兩句。"""
        self._require_card()
        if self.discussion_round > MAX_DISCUSSION_ROUNDS:
            return {"done": True, "round": self.discussion_round - 1, "reply": None, "next_quick": []}
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
        self._require_card()
        resp = propose_diff(self.aar_gateway, self.doctrine, self.summary, self.transcript, self.lang)
        self._bill(self.aar_gateway)(resp.usage, resp.latency_s)
        if resp.parsed is None:
            self.diff = None
            return {"error": f"準則更新失敗：{resp.error}", "diff": None}
        self.diff = resp.parsed
        d = self.diff.model_dump()
        d["empty"] = not self.diff.add and not self.diff.remove
        return {"diff": d, "provider": self.aar_gateway.provider, "model": self.aar_gateway.model, "cost_usd": self._aar_cost()}

    def adopt(self) -> dict:
        """套用 diff → 回歸（退步自動回滾）→ aar.json → 戰例進戰例庫。"""
        self._require_card()
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
        self._require_card()
        self._finish_aar(False, None, skipped=True)
        return {"skipped": True, "duration_s": self._aar_duration()}

    def undo(self) -> dict:
        ok = self.store.undo()
        return {"undone": ok, "doctrine": self.store.load() if ok else None, "message": "已還原上一版準則" if ok else "沒有上一版可還原"}

    def _finish_aar(self, adopted: bool, report: Optional[dict], skipped: bool) -> None:
        save_aar(self.out_dir / "aar.json", self.summary, self.transcript, self.diff, adopted, report, card=card_dict(self.card),
                 duration_s=self._aar_duration(), skipped=skipped)
        if self.evals_dir and self.overrides.records:   # 這場的推翻進戰例庫（§12）——回歸之後才寫
            from .evals import build_cases_from_battle, save_cases
            save_cases(build_cases_from_battle(self.out_dir), Path(self.evals_dir) / "cases.jsonl")

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
                "ended": self.ended, "out_dir": str(self.out_dir)}

    def settings(self, provider: Optional[str] = None, model: Optional[str] = None, lang: Optional[str] = None,
                 budget_usd: Optional[float] = None, effort: Optional[str] = None, aar_provider: Optional[str] = None,
                 aar_model: Optional[str] = None) -> dict:
        """換供應商／模型（重建閘道）、語言、預算、思考深度；失敗就保留原設定並回錯誤。"""
        if provider or model or effort:
            try:
                self.gateway = make_gateway(provider or self.cfg.provider, model or (self.cfg.model if not provider else None), effort=effort or self.cfg.effort)
            except (ValueError, NotImplementedError, ImportError) as err:
                return {"error": f"閘道設定失敗：{err}", "provider": self.gateway.provider, "model": self.gateway.model}
            self.cfg.provider, self.cfg.model, self.cfg.effort = self.gateway.provider, self.gateway.model, effort or self.cfg.effort
            if aar_provider or aar_model:
                self.cfg.aar_provider, self.cfg.aar_model = aar_provider, aar_model
            self.aar_gateway = self._make_aar_gateway()
        if lang:
            self.lang = lang
        if budget_usd is not None:
            self.budget_usd = float(budget_usd) if budget_usd >= 0 else None
            self.budget_hit = self.budget_usd is not None and self.meter.cost_usd >= self.budget_usd
        return {"provider": self.gateway.provider, "model": self.gateway.model, "lang": self.lang, "budget_usd": self.budget_usd,
                "effort": self.cfg.effort, "aar_model": self.aar_gateway.model}
