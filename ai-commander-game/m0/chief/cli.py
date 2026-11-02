"""CHIEF 指令列入口：uv run chief <子命令>。每張施工單加自己的子命令。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

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
    from .harness import load_harness
    from .prompts import use_template
    evals_dir = None
    doctrine_path = args.doctrine
    if args.doctrine != "harness/default/doctrine.md" and args.harness == "default":
        args.harness = ""   # 老闆明確指定 --doctrine 時，不要被預設的參謀長包蓋掉
    if args.harness:
        try:
            h = load_harness(args.harness)
        except BoardError as err:
            err_console.print(f"[red]{err}[/]")
            return 1
        doctrine_path = str(h.doctrine_path)
        use_template(h.prompt_path)
        evals_dir = h.evals_dir
    doctrine = load_doctrine(doctrine_path)
    aar_gateway = None
    if args.skip_aar:
        pass
    elif args.aar_model or args.aar_provider:
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
    if not args.out:
        args.out = str(Path("battles") / f"{board.battle_id}-{time_tag()}")   # 每場自己的資料夾，不互相覆蓋
    commander = None
    if getattr(args, "commander", None):
        from .commander import SimCommander
        try:
            commander = SimCommander.from_file(args.commander)
        except BoardError as err:
            err_console.print(f"[red]{err}[/]")
            return 1
    run_play(gateway, board, enemy, doctrine, lang=args.lang, seed=args.seed, out_dir=args.out, commander=commander,
             prices=prices, console=console, verbose=args.verbose, quiet=args.quiet,
             budget_usd=args.budget, ledger=ledger, auto=args.auto,
             doctrine_path=doctrine_path, aar_gateway=aar_gateway, skip_aar=args.skip_aar, evals_dir=evals_dir)
    return 0


def cmd_harness(args: argparse.Namespace) -> int:
    from .harness import HARNESS_ROOT, export_harness, import_harness, load_harness
    console, err = Console(), Console(stderr=True)
    try:
        if args.action == "list":
            for p in sorted(HARNESS_ROOT.glob("*/")):
                if (p / "manifest.json").exists():
                    h = load_harness(p.name)
                    console.print(f"{h.name}  v{h.manifest.version}  {h.manifest.author or '-'}  準則 {len(h.doctrine_path.read_text(encoding='utf-8-sig'))} 字")
            return 0
        if args.action == "export":
            out = export_harness(args.name, args.out or f"{args.name}.chief.zip")
            console.print(f"已匯出：{out}（不含金鑰）")
            return 0
        if args.action == "import":
            h = import_harness(args.file, rename=args.rename, overwrite=args.overwrite)
            console.print(f"已匯入參謀長包「{h.name}」到 {h.dir}")
            return 0
    except BoardError as e:
        err.print(f"[red]{e}[/]")
        return 1
    return 2


def cmd_evals(args: argparse.Namespace) -> int:
    from .evals import build_cases_from_battle, compare, load_cases, load_result, run_evals, save_cases, save_result
    from .harness import load_harness
    from .doctrine import DoctrineStore
    from .prompts import use_template
    console, err = Console(), Console(stderr=True)
    try:
        h = load_harness(args.harness)
    except BoardError as e:
        err.print(f"[red]{e}[/]")
        return 1
    cases_path = h.evals_dir / "cases.jsonl"
    if args.action == "build":
        total = 0
        for d in sorted(Path(args.battles).glob("*/")):
            cases = build_cases_from_battle(d)
            if cases:
                total = save_cases(cases, cases_path)
        console.print(f"戰例庫現有 {total} 筆（{cases_path}）")
        return 0
    if args.action == "run":
        cases = load_cases(cases_path)
        if not cases:
            console.print("[yellow]戰例庫是空的：先打幾場並推翻參謀長，或執行 chief evals build。[/]")
            return 1
        from .gateway import make_gateway
        use_template(h.prompt_path)
        store = DoctrineStore(h.doctrine_path)
        doctrine = store.load()
        if args.doctrine:
            doctrine = Path(args.doctrine).read_text(encoding="utf-8-sig")
        try:
            gw = make_gateway(args.provider, args.model, effort=args.effort)
        except (ValueError, NotImplementedError) as e:
            err.print(f"[red]{e}[/]")
            return 1
        res = run_evals(gw, cases, doctrine, h.name, args.lang)
        prev = load_result(h.evals_dir / "last.json")
        regressed, msg = compare(prev, res)
        console.print(f"[bold]{msg}[/]；退回率 {res.rejected_pct}%（{res.rejected_orders}/{res.total_orders}）")
        for d in res.details:
            console.print(f"  {'✅' if d['aligned'] else '❌'} {d['case']}：期望 {d['expected']}；參謀長 {', '.join(d['got']) or '（無）'}{('；' + d['error']) if d['error'] else ''}", markup=False)
        if regressed and args.rollback and not args.doctrine:   # 試水溫（--doctrine）不碰真準則
            if store.undo():
                console.print("[yellow]退步 → 已回滾準則到上一版。[/]")
        elif regressed and args.doctrine:
            console.print("[yellow]這是試水溫，真準則未變。[/]")
        elif not regressed and not args.doctrine:
            save_result(res, h.evals_dir / "last.json")
            console.print(f"[dim]已記錄為最新成績：{h.evals_dir / 'last.json'}[/]")
        return 2 if regressed else 0
    return 2


def cmd_stats(args: argparse.Namespace) -> int:
    from .acceptance import battle_stats, render_curve
    rows = battle_stats(args.battles)
    if not rows:
        Console().print("[yellow]還沒有任何戰鬥紀錄（battles/ 下沒有 aar.json）。[/]")
        return 1
    render_curve(rows[-args.last:], Console())
    return 0


def cmd_acceptance(args: argparse.Namespace) -> int:
    """連打 N 場（互動），每場之間照常戰後採納；最後印推翻率曲線。"""
    from .acceptance import battle_stats, render_curve
    console = Console()
    done = []
    for i in range(1, args.battles + 1):
        console.rule(f"驗收第 {i}/{args.battles} 場")
        ns = argparse.Namespace(**vars(args))
        ns.auto = False
        ns.out = str(Path("battles") / f"acceptance-{time_tag()}-{i}")
        rc = cmd_play(ns)
        if rc != 0:
            console.print(f"[red]第 {i} 場中止（exit {rc}）。[/]")
            break
        done.append(Path(ns.out).name)
    rows = [r for r in battle_stats("battles") if r["dir"] in done]
    if rows:
        render_curve(rows, console, title="M0 驗收：推翻率曲線")
    return 0


def time_tag() -> str:
    import time
    return time.strftime("%m%d-%H%M%S")


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
    y.add_argument("--harness", default="default", help="參謀長包名稱（harness/<名稱>/）；給空字串則只用 --doctrine")
    y.add_argument("--lang", default="zh-TW", choices=["zh-TW", "zh-CN", "en"])
    y.add_argument("--seed", type=int, default=None)
    y.add_argument("--prices", default=None, help="價格表 JSON（預設 chief/prices.json；覆寫 LiteLLM 內建表）")
    y.add_argument("--commander", default=None, help="模擬總司令風格檔（samples/commander_steady.json）：用規則代替真人推翻，全自動跑")
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
    hz = sub.add_parser("harness", help="參謀長包：list / export / import（施工單 07）")
    hz.add_argument("action", choices=["list", "export", "import"])
    hz.add_argument("name", nargs="?", default="default", help="export：包名稱")
    hz.add_argument("--file", default=None, help="import：zip 路徑")
    hz.add_argument("--out", default=None, help="export：輸出 zip 路徑")
    hz.add_argument("--rename", default=None, help="import：改名")
    hz.add_argument("--overwrite", action="store_true")
    hz.set_defaults(func=cmd_harness)
    ev = sub.add_parser("evals", help="戰例庫：build（從 battles/ 建）／run（回歸測試）（施工單 07）")
    ev.add_argument("action", choices=["build", "run"])
    ev.add_argument("--harness", default="default")
    ev.add_argument("--battles", default="battles")
    ev.add_argument("--provider", default="ollama"); ev.add_argument("--model", default=None); ev.add_argument("--effort", default=None)
    ev.add_argument("--lang", default="zh-TW", choices=["zh-TW", "zh-CN", "en"])
    ev.add_argument("--doctrine", default=None, help="用另一份準則跑（例如 samples/bad_doctrine.md），不記錄成績")
    ev.add_argument("--rollback", action="store_true", help="退步時自動回滾準則")
    ev.set_defaults(func=cmd_evals)
    st = sub.add_parser("stats", help="列出歷史戰鬥與推翻率曲線")
    st.add_argument("--battles", default="battles"); st.add_argument("--last", type=int, default=10)
    st.set_defaults(func=cmd_stats)
    ac = sub.add_parser("acceptance", help="M0 總驗收：連打 N 場（互動）並印曲線（施工單 07）")
    for a in y._actions:
        if a.dest not in ("help", "auto", "out") and a.option_strings:
            ac.add_argument(*a.option_strings, **{k: v for k, v in dict(default=a.default, help=a.help, type=a.type, choices=a.choices, action="store_true" if isinstance(a, argparse._StoreTrueAction) else None).items() if v is not None and not (k == "type" and a.type is None)})
    ac.add_argument("--battles", type=int, default=5)
    ac.set_defaults(func=cmd_acceptance, auto=False, out=None)
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
