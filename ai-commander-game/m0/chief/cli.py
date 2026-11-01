"""CHIEF 指令列入口：uv run chief <子命令>。每張施工單加自己的子命令。"""
from __future__ import annotations

import argparse
import sys

from rich.console import Console

from . import __version__
from .board import BoardError, estimate_tokens, load_board
from .render import render_board


def cmd_show(args: argparse.Namespace) -> int:
    console = Console()
    try:
        board = load_board(args.path)
    except BoardError as err:
        console.print(f"[red]{err}[/]")
        return 1
    if args.compact:
        text = board.compact_json()
        console.print(text, highlight=False, soft_wrap=True)
        console.print(f"[dim]壓縮版約 {estimate_tokens(text)} token（離線粗估：ASCII 4 字元=1，非 ASCII 1 字=1）[/]")
        return 0
    render_board(board, console)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="chief", description="AI 參謀長 RTS — M0 文字版沙盤")
    p.add_argument("--version", action="version", version=f"chief {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="顯示一份戰情板")
    s.add_argument("path", help="戰情板 JSON 路徑，例如 samples/board_t0.json")
    s.add_argument("--compact", action="store_true", help="改印給 LLM 的壓縮版與 token 粗估")
    s.set_defaults(func=cmd_show)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
