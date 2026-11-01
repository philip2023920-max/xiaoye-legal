"""參謀長指揮一場會戰（施工單 03：--auto 自動打；05 加互動推翻）。

流程（每回合）：壓縮戰情板 → 閘道 → 驗證器 → 引擎 step → 顯示評估／命令／退回／token。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .board import Board, Event
from .gateway import Gateway
from .meter import PriceTable, UsageMeter
from .orders import Rejection
from .prompts import build_messages
from .render import TASK_ZH, map_table, render_board
from .sim import Battle, BattleResult, Script
from .validator import validate_orders


@dataclass
class PlayResult:
    battle: BattleResult
    meter: UsageMeter
    rejections: int = 0
    gateway_errors: int = 0
    turns: list[dict] = field(default_factory=list)


def run_play(
    gateway: Gateway,
    board: Board,
    enemy: Script,
    doctrine: str,
    lang: str = "zh-TW",
    seed: int | None = None,
    out_dir: str | Path | None = None,
    prices: PriceTable | None = None,
    console: Console | None = None,
    verbose: bool = False,
    quiet: bool = False,
) -> PlayResult:
    console = console or Console()
    battle = Battle(board, enemy.units, seed=seed, out_dir=out_dir)
    meter = UsageMeter(prices=prices, log_path=battle.out_dir / "usage.jsonl")
    result = PlayResult(battle=None, meter=meter)  # type: ignore[arg-type]
    feedback: list[str] = []

    while not battle.finished():
        t = battle.t + 1
        snapshot = battle.board.compact()
        messages = build_messages(doctrine, snapshot, t, lang, feedback)
        resp = gateway.issue_orders(messages)
        entry = meter.record(t, gateway.provider, gateway.model, resp.usage, resp.latency_s)
        accepted, rejected = [], []
        if resp.orders is not None:
            accepted, rejected = validate_orders(battle.board, resp.orders.orders)
        else:
            result.gateway_errors += 1
            battle.board.events.append(Event(t=t, kind="info", text=resp.error or "參謀長無回應"))
        for r in rejected:
            battle.board.events.append(Event(t=t, kind="info", text=f"驗證器退回：{r.line()}", unit=r.order.unit_id))
        result.rejections += len(rejected)
        feedback = [r.line() for r in rejected]
        report = battle.step(accepted, enemy.for_turn(t))
        result.turns.append({"t": t, "assessment": resp.orders.assessment if resp.orders else None,
                             "accepted": [o.model_dump() for o in accepted], "rejected": [r.line() for r in rejected],
                             "usage": entry.usage.__dict__, "cost": entry.cost_usd, "error": resp.error})
        if not quiet:
            _print_turn(console, battle, t, resp, accepted, rejected, entry, report, verbose, meter.cost_usd)

    result.battle = battle.result()
    if not quiet:
        console.rule("戰後")
        render_board(battle.board, console)
    console.print(f"[bold]{result.battle.summary()}[/]")
    console.print(f"參謀長：{gateway.provider} / {gateway.model}｜退回 {result.rejections} 條｜無回應 {result.gateway_errors} 回合")
    console.print(meter.summary())
    console.print(f"[dim]快照與 usage.jsonl 已存：{battle.out_dir}[/]")
    return result


def _print_turn(console, battle, t, resp, accepted, rejected: list[Rejection], entry, report, verbose, running_cost: float) -> None:
    console.rule(f"第 {t} 回合")
    if resp.orders is not None:
        console.print(Panel(Text(resp.orders.assessment), title="參謀長評估", border_style="cyan"))
    else:
        console.print(Panel(Text(resp.error or "無回應", style="red"), title="參謀長", border_style="red"))
    table = Table(box=box.SIMPLE, title="本回合命令")
    table.add_column("單位"); table.add_column("任務"); table.add_column("目標"); table.add_column("理由"); table.add_column("狀態")
    for o in accepted:
        table.add_row(o.unit_id, TASK_ZH.get(o.task, o.task), o.target, o.reason, Text("放行", style="green"))
    for r in rejected:
        table.add_row(r.order.unit_id, TASK_ZH.get(r.order.task, r.order.task), r.order.target, r.order.reason, Text(f"退回 {r.rule}：{r.reason}", style="red"))
    if accepted or rejected:
        console.print(table)
    if verbose:
        render_board(battle.board, console)
    else:
        console.print(map_table(battle.board, console))
    lines = [Text(f"[{e.kind}] {e.text}") for e in report.events] or [Text("（本回合無事件）", style="dim")]
    console.print(Panel(Group(*lines), title=f"第 {t} 回合事件", border_style="blue"))
    est = "（粗估）" if entry.usage.estimated else ""
    console.print(f"[dim]token 輸入 {entry.usage.prompt_tokens}／輸出 {entry.usage.completion_tokens}{est}｜"
                  f"${entry.cost_usd:.4f}｜{entry.latency_s:.1f}s｜嘗試 {resp.attempts} 次｜本場累計 ${running_cost:.4f}[/]")
