"""CHIEF 指令列入口：uv run chief <子命令>。每張施工單加自己的子命令。"""
from __future__ import annotations

import argparse
import os
import sys

from rich.console import Console

from . import __version__
from .board import BoardError, estimate_tokens, load_board
from .render import events_panel, map_table, render_board
from .sim import Battle, load_script


def cmd_show(args: argparse.Namespace) -> int:
    console = Console()
    try:
        board = load_board(args.path)
    except BoardError as err:
        Console(stderr=True).print(f"[red]{err}[/]")
        return 1
    if args.compact:
        text = board.compact_json()
        console.print(text, highlight=False, soft_wrap=True)
        console.print(f"[dim]壓縮版約 {estimate_tokens(text)} token（離線粗估：ASCII 4 字元=1，非 ASCII 1 字=1）[/]")
        return 0
    render_board(board, console)
    return 0


def cmd_sim(args: argparse.Namespace) -> int:
    console = Console()
    err_console = Console(stderr=True)
    try:
        board = load_board(args.board)
        friendly = load_script(args.orders)
        enemy = load_script(args.enemy)
    except BoardError as err:
        err_console.print(f"[red]{err}[/]")
        return 1
    battle = Battle(board, enemy.units, seed=args.seed, variance=(not args.no_variance) if args.seed is not None else False, out_dir=args.out)

    def on_turn(b: Battle, report) -> None:
        if args.quiet:
            return
        console.rule(f"第 {report.t} 回合")
        if args.verbose:
            render_board(b.board, console)
        else:
            console.print(map_table(b.board, console))
            from rich.panel import Panel
            from rich.console import Group
            from rich.text import Text
            lines = [Text(f"[{e.kind}] {e.text}") for e in report.events] or [Text("（本回合無事件）", style="dim")]
            console.print(Panel(Group(*lines), title=f"第 {report.t} 回合事件", border_style="blue"))

    result = battle.run(friendly, enemy, on_turn=on_turn)
    if not args.quiet:
        console.rule("戰後")
        render_board(battle.board, console)
    console.print(f"[bold]{result.summary()}[/]")
    console.print(f"[dim]快照已存：{battle.out_dir}（共 {len(result.snapshots)} 回合）[/]")
    return 0


def cmd_play(args: argparse.Namespace) -> int:
    from .gateway import make_gateway
    from .meter import PriceTable
    from .play import run_play
    from .prompts import load_doctrine

    console = Console()
    err_console = Console(stderr=True)
    try:
        board = load_board(args.board)
        enemy = load_script(args.enemy)
        gateway = make_gateway(args.provider, args.model, effort=args.effort)
    except (BoardError, ValueError, NotImplementedError) as err:
        err_console.print(f"[red]{err}[/]")
        return 1
    doctrine = load_doctrine(args.doctrine)
    aar_gateway = None
    if args.aar_model or args.aar_provider:
        try:
            aar_gateway = make_gateway(args.aar_provider or args.provider, args.aar_model, effort=args.effort)
        except (ValueError, NotImplementedError) as err:
            err_console.print(f"[red]AAR 模型設定錯誤：{err}[/]")
            return 1
    elif args.provider == "anthropic":
        aar_gateway = make_gateway("anthropic", "claude-sonnet-5-5", effort=args.effort)   # 戰後檢討用中階模型（D3）
    from .meter import Ledger
    prices_path = args.prices or (os.path.join(os.path.dirname(__file__), "prices.json"))
    prices = PriceTable(prices_path)
    ledger = Ledger(args.ledger) if args.ledger else None
    run_play(gateway, board, enemy, doctrine, lang=args.lang, seed=args.seed, out_dir=args.out,
             prices=prices, console=console, verbose=args.verbose, quiet=args.quiet,
             budget_usd=args.budget, ledger=ledger, auto=args.auto,
             doctrine_path=args.doctrine, aar_gateway=aar_gateway, skip_aar=args.skip_aar)
    return 0


def cmd_doctrine(args: argparse.Namespace) -> int:
    from .doctrine import DoctrineStore
    console = Console()
    store = DoctrineStore(args.path)
    if args.action == "show":
        console.print(store.load(), markup=False)
        return 0
    if args.action == "undo":
        if store.undo():
            console.print("[green]已還原上一版準則。[/]")
            return 0
        console.print("[yellow]沒有可還原的版本。[/]")
        return 1
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="chief", description="AI 參謀長 RTS — M0 文字版沙盤")
    p.add_argument("--version", action="version", version=f"chief {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="顯示一份戰情板")
    s.add_argument("path", help="戰情板 JSON 路徑，例如 samples/board_t0.json")
    s.add_argument("--compact", action="store_true", help="改印給 LLM 的壓縮版與 token 粗估")
    s.set_defaults(func=cmd_show)
    m = sub.add_parser("sim", help="跑一場無 LLM 的劇本會戰（施工單 02）")
    m.add_argument("--board", default="samples/board_start.json", help="開局戰情板")
    m.add_argument("--orders", required=True, help="我方劇本，例如 samples/orders_scripted.json")
    m.add_argument("--enemy", default="samples/enemy_script.json", help="敵方劇本（含敵方初始部隊）")
    m.add_argument("--seed", type=int, default=None, help="隨機種子；給了才會有 ±10%% 傷害浮動")
    m.add_argument("--no-variance", action="store_true", help="即使給 seed 也不要浮動")
    m.add_argument("--out", default=None, help="快照輸出資料夾（預設 battles/<battle_id>）")
    m.add_argument("--quiet", action="store_true", help="只印結果")
    m.add_argument("--verbose", action="store_true", help="每回合印完整戰情板")
    m.set_defaults(func=cmd_sim)
    y = sub.add_parser("play", help="讓參謀長（LLM）指揮一場會戰（施工單 03）")
    y.add_argument("--provider", default="ollama", help="ollama / openai / deepseek / openrouter / anthropic（04）/ fake")
    y.add_argument("--model", default=None, help="模型名稱，例如 qwen2.5:3b（ollama）或 claude-haiku-5-5（anthropic）")
    y.add_argument("--auto", action="store_true", help="全自動：參謀長的命令直接執行（03）；不加則為互動推翻（05）")
    y.add_argument("--board", default="samples/board_start.json")
    y.add_argument("--enemy", default="samples/enemy_script.json")
    y.add_argument("--doctrine", default="harness/default/doctrine.md")
    y.add_argument("--lang", default="zh-TW", choices=["zh-TW", "zh-CN", "en"])
    y.add_argument("--seed", type=int, default=None)
    y.add_argument("--prices", default=None, help="價格表 JSON（預設 chief/prices.json；覆寫 LiteLLM 內建表）")
    y.add_argument("--skip-aar", action="store_true", help="戰後不出戰報卡與討論")
    y.add_argument("--aar-provider", default=None, help="戰後檢討用的供應商（預設同參謀長）")
    y.add_argument("--aar-model", default=None, help="戰後檢討用的模型（anthropic 預設 claude-sonnet-5-5）")
    y.add_argument("--effort", default=None, choices=["low", "medium", "high"], help="Anthropic 思考深度（預設 medium；下命令可試 low 省錢）")
    y.add_argument("--budget", type=float, default=None, help="本場預算（美元）：到 80%% 提醒，到 100%% 參謀長暫停")
    y.add_argument("--ledger", default="battles/ledger.jsonl", help="跨場帳本路徑（算今天／本月）；給空字串停用")
    y.add_argument("--out", default=None)
    y.add_argument("--quiet", action="store_true")
    y.add_argument("--verbose", action="store_true")
    y.set_defaults(func=cmd_play)
    d = sub.add_parser("doctrine", help="看或還原作戰準則（施工單 06）")
    d.add_argument("action", choices=["show", "undo"])
    d.add_argument("--path", default="harness/default/doctrine.md")
    d.set_defaults(func=cmd_doctrine)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()  # 讀 .env（ANTHROPIC_API_KEY、OLLAMA_HOST…），金鑰不經聊天
    except Exception:  # noqa: BLE001
        pass
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
