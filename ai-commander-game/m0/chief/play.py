"""參謀長指揮一場會戰（施工單 03：--auto 自動打；05 加互動推翻）。

流程（每回合）：壓縮戰情板 → 閘道 → 驗證器 → 引擎 step → 顯示評估／命令／退回／token。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .board import Board, Event
from .gateway import Gateway
from .meter import Ledger, PriceTable, UsageMeter
from .orders import Rejection
from .override import OverrideLog, OverrideRecord, TASK_CHOICES, judge_outcome, player_order_problem, target_sector
from .prompts import build_messages
from .render import TASK_ZH, map_table, render_board
from .sim import Battle, BattleResult, Order, Script
from .validator import validate_orders

HELP = "Enter＝全部採納｜數字＝改那條命令並接管該單位｜+ 單位id＝接管並下令｜- 單位id＝放手還給參謀長｜? 說明｜q＝結束戰鬥"


@dataclass
class PlayResult:
    battle: BattleResult
    meter: UsageMeter
    rejections: int = 0
    gateway_errors: int = 0
    turns: list[dict] = field(default_factory=list)
    budget_hit: bool = False
    overrides: int = 0
    chief_orders_total: int = 0
    override_outcomes: list[str] = field(default_factory=list)

    @property
    def override_rate(self) -> str:
        return f"{self.overrides}/{self.chief_orders_total}"


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
    budget_usd: float | None = None,
    ledger: Ledger | None = None,
    auto: bool = True,
    input_fn=input,
) -> PlayResult:
    console = console or Console()
    battle = Battle(board, enemy.units, seed=seed, out_dir=out_dir)
    meter = UsageMeter(prices=prices, log_path=battle.out_dir / "usage.jsonl")
    result = PlayResult(battle=None, meter=meter)  # type: ignore[arg-type]
    feedback: list[str] = []
    llm_log = battle.out_dir / "llm_log.jsonl"
    warned_80 = False
    overrides = OverrideLog(battle.out_dir / "overrides.jsonl")
    owner_cache: dict[int, str] = {}   # id(record) -> 推翻當下目標分區的擁有者
    quit_requested = False

    while not battle.finished():
        t = battle.t + 1
        snapshot = battle.board.compact()
        accepted, rejected = [], []
        if result.budget_hit:
            resp = None
            battle.board.events.append(Event(t=t, kind="info", text="已達預算上限，參謀長暫停，本回合無新命令"))
        else:
            messages = build_messages(doctrine, snapshot, t, lang, feedback)
            resp = gateway.issue_orders(messages)
            entry = meter.record(t, gateway.provider, gateway.model, resp.usage, resp.latency_s)
            if ledger:
                ledger.add(battle.board.battle_id, gateway.provider, gateway.model, entry.cost_usd, resp.usage)
            battle.out_dir.mkdir(parents=True, exist_ok=True)
            with llm_log.open("a", encoding="utf-8") as f:   # 原始回覆留底，除錯用（不含金鑰）
                f.write(json.dumps({"t": t, "provider": gateway.provider, "model": gateway.model, "attempts": resp.attempts,
                                    "error": resp.error, "raw": resp.raw, "usage": resp.usage.__dict__,
                                    "prompt_chars": sum(len(m["content"]) for m in messages)}, ensure_ascii=False) + "\n")
            if resp.orders is not None:
                accepted, rejected = validate_orders(battle.board, resp.orders.sim_orders())
            else:
                result.gateway_errors += 1
                battle.board.events.append(Event(t=t, kind="info", text=resp.error or "參謀長無回應"))
            if budget_usd is not None:
                if meter.cost_usd >= budget_usd:
                    result.budget_hit = True
                    battle.board.events.append(Event(t=t, kind="info", text=f"本場費用 ${meter.cost_usd:.4f} 已達預算 ${budget_usd:.2f}，下回合起參謀長暫停"))
                elif not warned_80 and meter.cost_usd >= 0.8 * budget_usd:
                    warned_80 = True
                    battle.board.events.append(Event(t=t, kind="info", text=f"提醒：本場費用 ${meter.cost_usd:.4f} 已達預算 80%"))
        for r in rejected:
            battle.board.events.append(Event(t=t, kind="info", text=f"驗證器退回：{r.line()}", unit=r.order.unit_id))
        result.rejections += len(rejected)
        result.chief_orders_total += len(accepted)
        feedback = [r.line() for r in rejected]
        if resp is not None and resp.orders is None:
            feedback.append("Your previous reply could not be parsed. Reply with ONLY the JSON object: no prose, no code fences.")
        if not auto:
            if not quiet:
                _show_proposal(console, battle, t, resp, accepted, rejected)
            accepted, quit_requested = _commander_turn(console, battle, t, accepted, overrides, owner_cache, result, input_fn)
            if quit_requested:
                battle.end_reason = "quit"
                break
        report = battle.step(accepted, enemy.for_turn(t))
        for rec in overrides.pending(battle.t):    # 上一回合的推翻，這回合結束判後果（§9）
            outcome = judge_outcome(battle.board, rec, owner_cache.get(id(rec)))
            overrides.set_outcome(rec, outcome, battle.t)
            result.override_outcomes.append(outcome)
            battle.board.events.append(Event(t=battle.t, kind="override", text=f"推翻後果：t{rec.turn} {rec.unit_id} {rec.player_order['task']} {rec.player_order['target']} → {outcome}", unit=rec.unit_id))
        result.turns.append({"t": t, "assessment": resp.orders.assessment if (resp and resp.orders) else None,
                             "accepted": [o.model_dump() for o in accepted], "rejected": [r.line() for r in rejected],
                             "usage": resp.usage.__dict__ if resp else None, "cost": entry.cost_usd if resp else 0.0,
                             "error": resp.error if resp else "budget"})
        if not quiet and resp is not None:
            _print_turn(console, battle, t, resp, accepted, rejected, entry, report, verbose, meter.cost_usd, ledger, show_orders=auto)

    result.battle = battle.result()
    result.overrides = len(overrides.records)
    if not quiet:
        console.rule("戰後")
        render_board(battle.board, console)
    console.print(f"[bold]{result.battle.summary()}[/]")
    console.print(f"參謀長：{gateway.provider} / {gateway.model}｜退回 {result.rejections} 條｜無回應 {result.gateway_errors} 回合")
    if not auto:
        good = result.override_outcomes.count("👍"); bad = result.override_outcomes.count("👎")
        console.print(f"[bold]推翻率：{result.override_rate}[/]（推翻次數／參謀長放行命令數）｜後果 👍{good} 👎{bad} ➖{len(result.override_outcomes) - good - bad}")
    rejected_lines = [f"t{tr['t']} {line}" for tr in result.turns for line in tr["rejected"]]
    if rejected_lines:
        console.print(Panel(Group(*[Text(l) for l in rejected_lines[:10]]), title="退回摘要（最多 10 條）", border_style="red"))
    errors = [f"t{tr['t']} {tr['error']}" for tr in result.turns if tr.get("error") and tr["error"] != "budget"]
    if errors:
        console.print(Panel(Group(*[Text(e) for e in errors[:5]]), title="無回應原因（最多 5 條）", border_style="red"))
    console.print(meter.summary())
    if ledger:
        tot = ledger.totals()
        console.print(f"累計：今天 ${tot['today']:.4f}｜本月 ${tot['month']:.4f}（估算值）")
    if result.budget_hit:
        console.print("[yellow]本場已達預算上限，參謀長中途暫停。[/]")
    console.print(f"[dim]快照、usage.jsonl、llm_log.jsonl 已存：{battle.out_dir}[/]")
    return result


def _orders_table(accepted, rejected: list[Rejection], numbered: bool = False) -> Table:
    table = Table(box=box.SIMPLE, title="本回合命令")
    if numbered:
        table.add_column("#", justify="right")
    table.add_column("單位"); table.add_column("任務"); table.add_column("目標"); table.add_column("理由"); table.add_column("狀態")
    for i, o in enumerate(accepted, 1):   # 模型回的字串一律包 Text()，避免 [/x] 之類被當 Rich 標記
        row = [Text(o.unit_id), Text(TASK_ZH.get(o.task, o.task)), Text(o.target), Text(o.reason), Text("放行", style="green")]
        table.add_row(*([Text(str(i))] + row if numbered else row))
    for r in rejected:
        row = [Text(r.order.unit_id), Text(TASK_ZH.get(r.order.task, r.order.task)), Text(r.order.target), Text(r.order.reason), Text(f"退回 {r.rule}：{r.reason}", style="red")]
        table.add_row(*([Text("")] + row if numbered else row))
    return table


def _show_proposal(console, battle, t, resp, accepted, rejected) -> None:
    console.rule(f"第 {t} 回合：參謀長提案")
    console.print(map_table(battle.board, console))
    if resp is not None and resp.orders is not None:
        console.print(Panel(Text(resp.orders.assessment), title="參謀長評估", border_style="cyan"))
    elif resp is not None:
        console.print(Panel(Text(resp.error or "無回應", style="red"), title="參謀長", border_style="red"))
    console.print(_orders_table(accepted, rejected, numbered=True))
    mine = [u for u in battle.board.orbat if u.controlled_by == "player" and u.state != "destroyed"]
    if mine:
        lines = [Text(f"{u.id}（{u.name}）戰力{int(round(u.strength*100))}% @{u.sector}" + (f" ➜ {TASK_ZH[u.task.type]} {u.task.target}" if u.task else "")) for u in mine]
        console.print(Panel(Group(*lines), title="總司令直轄部隊（任務延續，+ 可改令，- 放手）", border_style="yellow"))


def _ask_order(console, battle, unit_id: str, input_fn) -> Order | None:
    """問任務與目標；回 None 表示取消。"""
    console.print("任務：" + "｜".join(f"{i+1}={TASK_ZH[tk]}({tk})" for i, tk in enumerate(TASK_CHOICES)))
    raw = (input_fn("任務編號或名稱（Enter 取消）> ") or "").strip().lower()
    if not raw:
        return None
    task = TASK_CHOICES[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= 6 else raw
    if task not in TASK_CHOICES:
        console.print("[red]不認識的任務[/]")
        return None
    tgt = (input_fn("目標（分區如 C3；support 填友軍單位 id）> ") or "").strip()
    if not tgt:
        return None
    tgt = tgt.upper() if len(tgt) <= 3 and tgt[0].isalpha() and tgt[1:].isdigit() else tgt
    order = Order(unit_id=unit_id, task=task, target=tgt, reason="總司令命令")
    problem = player_order_problem(battle.board, order)
    if problem:
        console.print(f"[red]{problem}[/]")
        return None
    return order


def _commander_turn(console, battle, t, accepted: list[Order], overrides: OverrideLog, owner_cache: dict, result, input_fn):
    """互動：Enter 採納；數字改令；+/- 接管／放手；q 結束。回傳（最終命令清單, 是否結束）。"""
    orders = list(accepted)
    player_orders: dict[str, Order] = {}
    snapshot_ref = str(battle.out_dir / f"t{battle.t}.json")

    def take_over(unit_id: str, ai_order: Order | None) -> None:
        new = _ask_order(console, battle, unit_id, input_fn)
        if new is None:
            return
        u = battle.board.unit(unit_id)
        was_ai = u.controlled_by == "ai"
        u.controlled_by = "player"
        player_orders[unit_id] = new
        if was_ai:   # 從參謀長手上接過來才算一次推翻
            rec = OverrideRecord(turn=t, unit_id=unit_id, ai_order=ai_order.model_dump() if ai_order else (u.task.model_dump() if u.task else None),
                                 player_order=new.model_dump(), snapshot_ref=snapshot_ref, strength_at=u.strength)
            sector = target_sector(battle.board, rec.player_order)
            owner_cache[id(rec)] = battle.board.map.sectors[sector].owner if sector else None
            overrides.add(rec)
            battle.board.overrides_this_battle += 1
            battle.board.events.append(Event(t=t, kind="override", text=f"總司令接管 {u.name}，改為 {TASK_ZH[new.task]} {new.target}", unit=unit_id))
        console.print(f"[yellow]{u.name} 已直轄：{TASK_ZH[new.task]} {new.target}[/]")

    while True:
        raw = (input_fn(f"總司令（{HELP}）> ") or "").strip()
        if raw == "":
            break
        if raw.lower() == "q":
            return [], True
        if raw == "?":
            console.print(HELP)
            continue
        if raw.isdigit():
            n = int(raw)
            if not (1 <= n <= len(orders)):
                console.print("[red]沒有這個編號[/]")
                continue
            ai_order = orders[n - 1]
            take_over(ai_order.unit_id, ai_order)
            if ai_order.unit_id in player_orders:
                orders = [o for o in orders if o.unit_id != ai_order.unit_id]
            continue
        if raw.startswith("+"):
            unit_id = raw[1:].strip()
            try:
                battle.board.unit(unit_id)
            except KeyError:
                console.print(f"[red]單位 {unit_id} 不存在[/]")
                continue
            ai_order = next((o for o in orders if o.unit_id == unit_id), None)
            take_over(unit_id, ai_order)
            if unit_id in player_orders:
                orders = [o for o in orders if o.unit_id != unit_id]
            continue
        if raw.startswith("-"):
            unit_id = raw[1:].strip()
            try:
                u = battle.board.unit(unit_id)
            except KeyError:
                console.print(f"[red]單位 {unit_id} 不存在[/]")
                continue
            u.controlled_by = "ai"
            player_orders.pop(unit_id, None)
            battle.board.events.append(Event(t=t, kind="info", text=f"總司令放手 {u.name}，交回參謀長", unit=unit_id))
            console.print(f"[green]{u.name} 已交回參謀長[/]")
            continue
        console.print("[red]看不懂，輸入 ? 看說明[/]")
    return orders + list(player_orders.values()), False


def _print_turn(console, battle, t, resp, accepted, rejected: list[Rejection], entry, report, verbose, running_cost: float, ledger=None, show_orders: bool = True) -> None:
    console.rule(f"第 {t} 回合")
    if show_orders:
        if resp.orders is not None:
            console.print(Panel(Text(resp.orders.assessment), title="參謀長評估", border_style="cyan"))
        else:
            console.print(Panel(Text(resp.error or "無回應", style="red"), title="參謀長", border_style="red"))
        if accepted or rejected:
            console.print(_orders_table(accepted, rejected))
    if verbose:
        render_board(battle.board, console)
    else:
        console.print(map_table(battle.board, console))
    lines = [Text(f"[{e.kind}] {e.text}") for e in report.events] or [Text("（本回合無事件）", style="dim")]
    console.print(Panel(Group(*lines), title=f"第 {t} 回合事件", border_style="blue"))
    if resp.orders is None:
        return
    est = "（粗估）" if entry.usage.estimated else ""
    cache = f"｜快取讀 {entry.usage.cache_read_tokens}" if entry.usage.cache_read_tokens else ""
    hud = f"本場 ${running_cost:.4f}"
    if ledger:
        tot = ledger.totals()
        hud += f"｜今天 ${tot['today']:.4f}｜本月 ${tot['month']:.4f}"
    console.print(f"[dim]token 輸入 {entry.usage.prompt_tokens}／輸出 {entry.usage.completion_tokens}{est}{cache}｜"
                  f"${entry.cost_usd:.4f}｜{entry.latency_s:.1f}s｜嘗試 {resp.attempts} 次｜{hud}[/]")
