"""CHIEF 指令列入口：uv run chief <子命令>。每張施工單加自己的子命令。"""
from __future__ import annotations

import argparse
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
    if not args.auto:
        err_console.print("[yellow]互動推翻模式在施工單 05；目前請加 --auto。[/]")
        return 2
    try:
        board = load_board(args.board)
        enemy = load_script(args.enemy)
        gateway = make_gateway(args.provider, args.model)
    except (BoardError, ValueError, NotImplementedError) as err:
        err_console.print(f"[red]{err}[/]")
        return 1
    doctrine = load_doctrine(args.doctrine)
    prices = PriceTable(args.prices) if args.prices else PriceTable()
    run_play(gateway, board, enemy, doctrine, lang=args.lang, seed=args.seed, out_dir=args.out,
             prices=prices, console=console, verbose=args.verbose, quiet=args.quiet)
    return 0


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
    y.add_argument("--prices", default=None, help="prices.json 覆寫價格表（04）")
    y.add_argument("--out", default=None)
    y.add_argument("--quiet", action="store_true")
    y.add_argument("--verbose", action="store_true")
    y.set_defaults(func=cmd_play)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
