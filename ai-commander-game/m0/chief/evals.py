"""戰例庫回歸（施工單 07）。規則：docs/10-sim-rules.md §12。

戰例＝玩家推翻當下的戰局（快照＋參謀長原令＋玩家改令）。回歸＝用「現在的準則」重問參謀長同一局，
看它會不會自己下出玩家當時要的命令（對齊率）。準則更新後對齊率退步超過 5 個百分點 → 回滾。
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .board import Board, BoardError, board_from_dict
from .orders import ChiefOrders
from .prompts import build_messages
from .validator import validate_orders

MAX_CASES = 10
REGRESSION_POINTS = 5.0


@dataclass
class EvalCase:
    id: str
    battle_id: str
    turn: int
    unit_id: str
    player_task: str
    player_target: str
    ai_task: str | None
    ai_target: str | None
    outcome: str | None
    board: dict                 # 推翻當下的完整戰情板（可重載）


@dataclass
class EvalResult:
    harness: str
    provider: str
    model: str
    cases: int
    aligned: int
    rejected_orders: int
    total_orders: int
    at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    details: list[dict] = field(default_factory=list)

    @property
    def aligned_pct(self) -> float:
        return round(100.0 * self.aligned / self.cases, 1) if self.cases else 0.0

    @property
    def rejected_pct(self) -> float:
        return round(100.0 * self.rejected_orders / self.total_orders, 1) if self.total_orders else 0.0


def build_cases_from_battle(battle_dir: str | Path) -> list[EvalCase]:
    """從 battles/<id>/overrides.jsonl 與快照組戰例；沒有推翻就沒有戰例。"""
    d = Path(battle_dir)
    ov = d / "overrides.jsonl"
    if not ov.exists():
        return []
    cases: list[EvalCase] = []
    for line in ov.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        snap = d / f"t{r['turn'] - 1}.json"
        if not snap.exists():
            continue
        board = json.loads(snap.read_text(encoding="utf-8-sig"))
        ai = r.get("ai_order") or {}
        cases.append(EvalCase(id=f"{d.name}-t{r['turn']}-{r['unit_id']}", battle_id=board.get("battle_id", d.name),
                              turn=r["turn"], unit_id=r["unit_id"], player_task=r["player_order"]["task"], player_target=r["player_order"]["target"],
                              ai_task=ai.get("task") or ai.get("type"), ai_target=ai.get("target"), outcome=r.get("outcome"), board=board))
    return cases


def save_cases(cases: list[EvalCase], path: str | Path, keep: int = MAX_CASES) -> int:
    """合併進戰例庫（同 id 覆蓋），只留最新 keep 筆。回傳總數。"""
    p = Path(path)
    existing: dict[str, dict] = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                c = json.loads(line)
                existing[c["id"]] = c
            except (json.JSONDecodeError, KeyError):
                continue
    for c in cases:
        existing[c.id] = asdict(c)
    rows = list(existing.values())[-keep:]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return len(rows)


def load_cases(path: str | Path) -> list[EvalCase]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(EvalCase(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def _aligned(orders: ChiefOrders | None, case: EvalCase, board: Board) -> tuple[bool, int, int]:
    """對齊＝參謀長這次對該單位（或它的上級）下的令，任務與目標都等於玩家當時的令。回傳（對齊, 退回數, 命令數）。"""
    if orders is None:
        return False, 0, 0
    accepted, rejected = validate_orders(board, orders.sim_orders())
    chain = {case.unit_id}
    cur = board.unit(case.unit_id) if any(u.id == case.unit_id for u in board.orbat) else None
    while cur is not None and cur.parent:
        chain.add(cur.parent)
        cur = board.unit(cur.parent)
    hit = any(o.unit_id in chain and o.task == case.player_task and o.target == case.player_target for o in accepted)
    return hit, len(rejected), len(accepted) + len(rejected)


def run_evals(gateway, cases: list[EvalCase], doctrine: str, harness_name: str, lang: str = "zh-TW", on_usage=None) -> EvalResult:
    res = EvalResult(harness=harness_name, provider=gateway.provider, model=gateway.model, cases=0, aligned=0, rejected_orders=0, total_orders=0)
    for c in cases:
        try:
            board = board_from_dict(c.board)
            board.unit(c.unit_id).controlled_by = "ai"     # 回歸時把單位還給參謀長，看它會不會自己下對
        except (BoardError, KeyError):
            continue
        resp = gateway.issue_orders(build_messages(doctrine, board.compact(), c.turn, lang))
        if on_usage:
            on_usage(resp.usage, resp.latency_s)
        ok, rej, tot = _aligned(resp.orders, c, board)
        res.cases += 1
        res.aligned += int(ok)
        res.rejected_orders += rej
        res.total_orders += tot
        res.details.append({"case": c.id, "aligned": ok, "expected": f"{c.player_task} {c.player_target}",
                            "got": [f"{o.unit_id} {o.task} {o.target}" for o in (resp.orders.sim_orders() if resp.orders else [])], "error": resp.error})
    return res


def compare(previous: dict | None, current: EvalResult) -> tuple[bool, str]:
    """回傳（是否退步, 說明）。退步＝對齊率比上一版低超過 5 個百分點。
    無法判定（本次 0 個戰例、或過半戰例參謀長無回應、或基準是別的模型）一律不算退步。"""
    errors = sum(1 for d in current.details if d.get("error"))
    if current.cases == 0 or (current.details and errors * 2 > len(current.details)):
        return False, f"無法判定：本次 {current.cases} 個戰例、{errors} 個無回應（不算退步，不更新基準）"
    if not previous or not previous.get("cases"):
        return False, f"對齊率 {current.aligned_pct}%（{current.aligned}/{current.cases}），無上一版可比，記為基準"
    if previous.get("model") and previous.get("model") != current.model:
        return False, f"對齊率 {current.aligned_pct}%；基準是 {previous.get('model')}，本次是 {current.model}，不同模型不判退步"
    prev_pct = round(100.0 * previous["aligned"] / previous["cases"], 1)
    delta = round(current.aligned_pct - prev_pct, 1)
    regressed = delta < -REGRESSION_POINTS
    return regressed, f"對齊率 {current.aligned_pct}%（基準 {previous.get('model', '?')} {prev_pct}%，{'+' if delta >= 0 else ''}{delta} 點）{'→ 退步' if regressed else ''}"


def save_result(res: EvalResult, path: str | Path, keep_prev: bool = True) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if keep_prev and p.exists():
        p.with_name("prev.json").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    p.write_text(json.dumps(asdict(res) | {"aligned_pct": res.aligned_pct, "rejected_pct": res.rejected_pct}, ensure_ascii=False, indent=2), encoding="utf-8")


def load_result(path: str | Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
