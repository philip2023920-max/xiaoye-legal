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

from .badges import award
from .board import Board, Event
from .discussion import run_discussion
from .doctrine import DoctrineStore, apply_diff, propose_diff, save_aar
from .gateway import Gateway
from .report import BattleCard, build_card_from, card_dict, chief_line, pick_moments, render_card, card_summary_text
from rich.markup import escape as _esc
from .meter import Ledger, PriceTable, UsageMeter
from .orders import Rejection
from .override import OverrideLog, OverrideRecord, TASK_CHOICES, judge_outcome, player_order_problem, subtree_ids, target_sector
from rich.markup import escape
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
    card: BattleCard | None = None

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
    input_fn=None,
    doctrine_path: str | Path | None = None,
    aar_gateway: Gateway | None = None,
    skip_aar: bool = False,
    evals_dir: str | Path | None = None,
    commander=None,
) -> PlayResult:
    console = console or Console()
    sim_state: dict = {}
    if commander is not None:                      # 模擬總司令：用規則代替真人按鍵（07b）
        from .commander import make_input_fn
        input_fn = make_input_fn(commander, sim_state)
        auto = False
    input_fn = input_fn or input   # 執行時才取 builtins.input（可被測試或 UI 替換）
    store = DoctrineStore(doctrine_path) if doctrine_path else None
    if store and not quiet:
        opening = store.opening_line()
        if opening:
            console.print(Panel(Text(f"參謀長：上次您採納了「{opening}」，這場我會照著做。"), title="開局", border_style="cyan"))
    start_board = board.model_copy(deep=True)
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
        feedback = [r.line() for r in rejected]
        if resp is not None and resp.orders is None:
            feedback.append("Your previous reply could not be parsed. Reply with ONLY the JSON object: no prose, no code fences.")
        if not auto:
            if not quiet:
                _show_proposal(console, battle, t, resp, accepted, rejected)
            sim_state.update(board=battle.board, t=t, accepted=accepted, fresh=True)
            chief_count = len(accepted)
            accepted, quit_requested = _commander_turn(console, battle, t, accepted, overrides, owner_cache, result, input_fn)
            if quit_requested:
                battle.end_reason = "quit"
                break
            result.chief_orders_total += chief_count
        else:
            result.chief_orders_total += len(accepted)
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
        unjudged = sum(1 for r in overrides.records if r.outcome is None)
        rate = result.override_rate if result.chief_orders_total else f"{result.overrides}/0（參謀長未下令）"
        console.print(f"[bold]推翻率：{rate}[/]（推翻次數／參謀長放行命令數）｜後果 👍{good} 👎{bad} ➖{len(result.override_outcomes) - good - bad}"
                      + (f"｜未判定 {unjudged}（最後一回合的推翻沒有下一回合可看）" if unjudged else ""))
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
    if not skip_aar:
        result.card = _aar_flow(console, gateway, aar_gateway or gateway, battle, start_board, result, overrides, doctrine, store, lang, auto, input_fn, meter, ledger,
                                evals_dir=evals_dir)
    if evals_dir and overrides.records:    # 這場的推翻進戰例庫（§12）——放在回歸之後，讓基準與本次用同一組戰例
        from .evals import build_cases_from_battle, save_cases
        n = save_cases(build_cases_from_battle(battle.out_dir), Path(evals_dir) / "cases.jsonl")
        console.print(f"[dim]戰例庫：本場新增 {len(overrides.records)} 筆，現有 {n} 筆（下次採納時用）[/]")
    return result


def _aar_flow(console, gateway, aar_gateway, battle, start_board, result, overrides, doctrine, store, lang, auto, input_fn, meter, ledger=None, evals_dir=None) -> BattleCard:
    """戰後：戰報卡（不花 token）→ 參謀長一句話 → 討論（最多三回合）→ 準則 diff 一鍵採納。
    自動模式只出卡（不呼叫 LLM）。戰後每次呼叫都計費（phase=aar）。"""
    def bill(gw):
        def _on(usage, latency):
            e = meter.record(battle.t, gw.provider, gw.model, usage, latency, phase="aar")
            if ledger:
                ledger.add(battle.board.battle_id, gw.provider, gw.model, e.cost_usd, usage)
        return _on

    start_us = {o.id for o in start_board.objectives if o.owner == "us"}
    end_us = {o.id for o in battle.board.objectives if o.owner == "us"}
    badges = award(result.battle.winner, result.override_outcomes, len(overrides.records), meter.cost_usd, start_us, end_us,
                   local_model=gateway.model.startswith(("ollama", "fake")))
    card = build_card_from(result, battle, overrides.records, badges, gateway)
    if not auto and store is not None:
        line = chief_line(gateway, card, doctrine, lang, on_usage=bill(gateway))
        if line:
            card.chief_line = line
    console.print(render_card(card))
    summary = card_summary_text(card)
    if auto or store is None:
        save_aar(battle.out_dir / "aar.json", summary, [], None, False, None, card=card_dict(card), duration_s=0.0, skipped=True)
        return card
    import time as _time
    t_start = _time.perf_counter()
    try:
        choice = (input_fn("戰後（Enter＝討論｜a＝直接採納｜s＝跳過）> ") or "").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = "s"
    if choice == "s":
        save_aar(battle.out_dir / "aar.json", summary, [], None, False, None, card=card_dict(card),
                 duration_s=round(_time.perf_counter() - t_start, 1), skipped=True)
        return card
    transcript = run_discussion(gateway, card, doctrine, lang, console, input_fn, on_usage=bill(gateway)) if choice != "a" else []
    resp = propose_diff(aar_gateway, doctrine, summary, transcript, lang)
    bill(aar_gateway)(resp.usage, resp.latency_s)
    if resp.parsed is None:
        console.print(Text(f"準則更新失敗：{resp.error}", style="red"))
        save_aar(battle.out_dir / "aar.json", summary, transcript, None, False, None, card=card_dict(card),
                 duration_s=round(_time.perf_counter() - t_start, 1), skipped=False)
        return card
    diff = resp.parsed
    lines = [Text(f"摘要：{diff.summary}")] + [Text(f"＋ [{l.section}] {l.text}", style="green") for l in diff.add] + [Text(f"－ {r}", style="red") for r in diff.remove]
    if not diff.add and not diff.remove:
        lines.append(Text("（參謀長認為這場不需要改準則）", style="dim"))
    console.print(Panel(Group(*lines), title=_esc(f"準則變更提案（{aar_gateway.provider}/{aar_gateway.model}）"), border_style="magenta"))
    try:
        ok = (input_fn("採納？（Enter＝採納｜n＝不採納）> ") or "").strip().lower() != "n"
    except (EOFError, KeyboardInterrupt):
        ok = False
    report = None
    if ok and (diff.add or diff.remove):
        new_text, report = apply_diff(store.load(), diff)
        store.save(new_text)
        console.print(Text(f"準則已更新：新增 {report['added']}、刪除 {report['removed']}" + (f"、因超過上限淘汰 {report['trimmed']}" if report['trimmed'] else "")
                           + f"（{report['chars']}/2000 字）。反悔可用 `chief doctrine undo`。", style="green"))
        if evals_dir:
            regressed = regression_check(console, gateway, store, Path(evals_dir), lang, bill(gateway))
            if regressed:
                report["rolled_back"] = True
    elif ok:
        console.print(Text("沒有變更。", style="dim"))
    else:
        console.print(Text("未採納。", style="yellow"))
    if report and report.get("ignored_removes"):
        console.print(Text(f"（略過 {len(report['ignored_removes'])} 條找不到或太短的刪除：{'；'.join(report['ignored_removes'])}）", style="dim"))
    console.print(Text(f"戰後流程費用：${sum(e.cost_usd for e in meter.entries if e.phase == 'aar'):.4f}（已計入帳本）", style="dim"))
    duration = round(_time.perf_counter() - t_start, 1)
    console.print(Text(f"戰後流程用時 {duration:.0f} 秒（目標 < 120 秒）", style="dim"))
    save_aar(battle.out_dir / "aar.json", summary, transcript, diff, bool(ok and (diff.add or diff.remove)), report, card=card_dict(card),
             duration_s=duration, skipped=False)
    return card


def regression_check(console, gateway, store, evals_dir: Path, lang: str, on_usage=None) -> bool:
    """採納後用戰例庫重問參謀長；對齊率退步超過 5 點就回滾準則。回傳是否回滾。"""
    from .evals import compare, load_cases, load_result, run_evals, save_result
    cases = load_cases(evals_dir / "cases.jsonl")
    if not cases:
        console.print(Text("戰例庫還是空的，略過回歸測試（這場的推翻會進戰例庫，下次採納就有得比）。", style="dim"))
        return False
    prev = load_result(evals_dir / "last.json")
    if not prev or prev.get("model") != gateway.model:
        # 沒有同模型的基準：先用「採納前」的準則跑一次當基準（多 ≤10 次呼叫，只在第一次）
        console.print(Text(f"沒有 {gateway.model} 的基準成績，先用上一版準則建立基準（{len(cases)} 個戰例）…", style="dim"))
        base_text = store.prev.read_text(encoding="utf-8") if store.prev.exists() else store.load()
        base = run_evals(gateway, cases, base_text, store.path.parent.name, lang, on_usage=on_usage)
        if base.cases:
            save_result(base, evals_dir / "last.json")
            prev = load_result(evals_dir / "last.json")
    console.print(Text(f"戰例庫回歸：用新準則重跑 {len(cases)} 個戰例…", style="dim"))
    res = run_evals(gateway, cases, store.load(), store.path.parent.name, lang, on_usage=on_usage)
    regressed, msg = compare(prev, res)
    console.print(Text(f"回歸結果：{msg}；退回率 {res.rejected_pct}%", style="red" if regressed else "green"))
    if regressed:
        if store.undo():
            console.print(Text("準則退步，已自動回滾到上一版（這次採納作廢）。", style="yellow"))
        else:
            console.print(Text("準則退步，但找不到上一版可回滾，請手動檢查準則。", style="red"))
        return True
    if "無法判定" not in msg:
        save_result(res, evals_dir / "last.json")
    return False


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
    raw = (_read(input_fn, "任務編號或名稱（Enter 取消）> ") or "").strip().lower()
    if not raw:
        return None
    task = TASK_CHOICES[int(raw) - 1] if raw.isdecimal() and 1 <= int(raw) <= 6 else raw
    if task not in TASK_CHOICES:
        console.print(Text("不認識的任務", style="red"))
        return None
    tgt = (_read(input_fn, "目標（分區如 C3；support 填友軍單位 id）> ") or "").strip()
    if not tgt:
        return None
    tgt = tgt.upper() if len(tgt) <= 3 and tgt[0].isalpha() and tgt[1:].isdecimal() else tgt
    order = Order(unit_id=unit_id, task=task, target=tgt, reason="總司令命令", issuer="player")
    problem = player_order_problem(battle.board, order)
    if problem:
        console.print(Text(problem, style="red"))   # 玩家輸入一律 Text()，不當 Rich 標記
        return None
    return order


class _Quit(Exception):
    """玩家按 Ctrl+C／Ctrl+D／Ctrl+Z：視同 q。"""


def _read(input_fn, prompt: str) -> str:
    try:
        return input_fn(prompt)
    except (EOFError, KeyboardInterrupt):
        raise _Quit() from None


def _commander_turn(console, battle, t, accepted: list[Order], overrides: OverrideLog, owner_cache: dict, result, input_fn):
    """互動：Enter 採納；數字改令；+/- 接管／放手；q 結束。回傳（最終命令清單, 是否結束）。"""
    orders = list(accepted)            # 編號固定＝畫面上的 #，被接管的用 replaced 標記，不位移
    replaced: set[int] = set()
    player_orders: dict[str, Order] = {}
    snapshot_ref = str(battle.out_dir / f"t{battle.t}.json")
    by_id = {u.id: u for u in battle.board.orbat}

    def chief_order_for(unit_id: str) -> Order | None:
        """參謀長本回合對這個單位或它任何上級的命令（上級的連令會拆到它身上）。"""
        chain, cur = [unit_id], by_id.get(unit_id)
        while cur is not None and cur.parent:
            chain.append(cur.parent)
            cur = by_id.get(cur.parent)
        for uid in chain:
            for i, o in enumerate(orders):
                if o.unit_id == uid and i not in replaced:
                    return o
        return None

    def take_over(unit_id: str) -> None:
        u = by_id[unit_id]
        ai_order = chief_order_for(unit_id)
        new = _ask_order(console, battle, unit_id, input_fn)
        if new is None:
            return
        was_ai = u.controlled_by == "ai"
        for uid in subtree_ids(battle.board, unit_id):      # 接管連＝連同所有下級一起直轄
            by_id[uid].controlled_by = "player"
        player_orders[unit_id] = new
        for i, o in enumerate(orders):                         # 參謀長對這棵子樹的命令全部作廢
            if o.unit_id in subtree_ids(battle.board, unit_id):
                replaced.add(i)
        if was_ai:   # 從參謀長手上接過來才算一次推翻
            rec = OverrideRecord(turn=t, unit_id=unit_id, ai_order=ai_order.model_dump() if ai_order else (u.task.model_dump() if u.task else None),
                                 player_order=new.model_dump(), snapshot_ref=snapshot_ref, strength_at=u.strength)
            sector = target_sector(battle.board, rec.player_order)
            owner_cache[id(rec)] = battle.board.map.sectors[sector].owner if sector else None
            overrides.add(rec)
            battle.board.overrides_this_battle += 1
            battle.board.events.append(Event(t=t, kind="override", text=f"總司令接管 {u.name}，改為 {TASK_ZH[new.task]} {new.target}", unit=unit_id))
        console.print(Text(f"{u.name} 已直轄：{TASK_ZH[new.task]} {new.target}", style="yellow"))

    try:
        while True:
            raw = (_read(input_fn, f"總司令（{HELP}）> ") or "").strip()
            if raw == "":
                break
            if raw.lower() == "q":
                return [], True
            if raw == "?":
                console.print(HELP)
                continue
            if raw.isdecimal():
                n = int(raw)
                if not (1 <= n <= len(orders)):
                    console.print(Text("沒有這個編號", style="red"))
                    continue
                if (n - 1) in replaced:
                    console.print(Text("這條已被你的命令取代", style="red"))
                    continue
                take_over(orders[n - 1].unit_id)
                continue
            if raw.startswith("+"):
                unit_id = raw[1:].strip()
                if unit_id not in by_id or by_id[unit_id].state == "destroyed":
                    console.print(Text(f"單位 {unit_id} 不存在或已殲滅（例如 +plt-A2）", style="red"))
                    continue
                take_over(unit_id)
                continue
            if raw.startswith("-"):
                unit_id = raw[1:].strip()
                if unit_id not in by_id:
                    console.print(Text(f"單位 {unit_id} 不存在", style="red"))
                    continue
                if by_id[unit_id].controlled_by != "player":
                    console.print(Text(f"單位 {unit_id} 本來就由參謀長指揮", style="yellow"))
                    continue
                for uid in subtree_ids(battle.board, unit_id):  # 放手連＝連同下級一起交回
                    by_id[uid].controlled_by = "ai"
                    player_orders.pop(uid, None)
                battle.board.events.append(Event(t=t, kind="info", text=f"總司令放手 {by_id[unit_id].name}，交回參謀長", unit=unit_id))
                console.print(Text(f"{by_id[unit_id].name} 已交回參謀長", style="green"))
                continue
            console.print(Text("看不懂，輸入 ? 看說明", style="red"))
    except _Quit:
        console.print(Text("（收到中斷，視同結束戰鬥）", style="yellow"))
        return [], True
    return [o for i, o in enumerate(orders) if i not in replaced] + list(player_orders.values()), False


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
