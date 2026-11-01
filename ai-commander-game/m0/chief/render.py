"""把戰情板畫到終端機：分區地圖、部隊樹、目標、事件。重用 Rich（Textual 相依）。"""
from __future__ import annotations

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .board import ECHELON_ZH, Board, Unit

TERRAIN_GLYPH = {"open": "·", "hill": "▲", "forest": "♣", "town": "■", "river": "≈"}
TERRAIN_ZH = {"open": "平地", "hill": "高地", "forest": "森林", "town": "城鎮", "river": "河川"}
OWNER_STYLE = {"us": "bold green", "enemy": "bold red", "none": "dim"}
STATE_ZH = {"idle": "待命", "moving": "移動", "engaged": "交戰", "routed": "潰散", "destroyed": "殲滅"}
TASK_ZH = {"seize": "奪取", "hold": "固守", "flank": "側翼", "withdraw": "撤退", "support": "支援", "reserve": "預備"}


def map_table(board: Board) -> Table:
    t = Table(box=box.SQUARE, show_lines=True, title=f"分區地圖 {board.map.cols}x{board.map.rows}（t={board.t}）", padding=(0, 1))
    t.add_column(" ", justify="right", style="dim")
    for c in range(board.map.cols):
        t.add_column(chr(ord("A") + c), justify="center", min_width=7)
    visible = set(board.fog.visible_sectors)
    for r in range(1, board.map.rows + 1):
        cells = []
        for c in range(board.map.cols):
            sid = f"{chr(ord('A') + c)}{r}"
            s = board.map.sectors[sid]
            head = Text(f"{TERRAIN_GLYPH[s.terrain]}", style=OWNER_STYLE[s.owner])
            if s.objective:
                head.append(f"★{s.objective}", style="bold yellow")
            if s.contested:
                head.append("!", style="bold magenta")
            us = len(board.units_in(sid))
            en = len(board.contacts_in(sid))
            foot = Text()
            if us:
                foot.append(f"我{us}", style="green")
            if en:
                foot.append(("  " if us else "") + f"敵{en}", style="red")
            if sid not in visible and visible:
                foot.append(" ?", style="dim")
            cells.append(Text.assemble(head, "\n", foot))
        t.add_row(str(r), *cells)
    t.caption = "▲高地 ♣森林 ■城鎮 ≈河川 ·平地｜綠=我方 紅=敵方｜★目標 !爭奪中 ?迷霧"
    return t


def _unit_label(u: Unit) -> Text:
    style = {"routed": "yellow", "destroyed": "dim strike", "engaged": "bold"}.get(u.state, "")
    label = Text(f"{u.name} ", style=style)
    label.append(f"[{ECHELON_ZH[u.echelon]}/{u.type}] ", style="cyan")
    label.append(f"戰力{int(round(u.strength * 100))}% ", style="green" if u.strength >= 0.5 else "red")
    label.append(f"{STATE_ZH[u.state]} @{u.sector}")
    if u.task:
        label.append(f" ➜ {TASK_ZH[u.task.type]} {u.task.target}", style="magenta")
    if u.controlled_by == "player":
        label.append(" ★直轄", style="bold yellow")
    return label


def orbat_tree(board: Board) -> Tree:
    tree = Tree(Text("友軍部隊樹", style="bold"))

    def add(parent_node: Tree, unit: Unit) -> None:
        node = parent_node.add(_unit_label(unit))
        for child in board.children(unit.id):
            add(node, child)

    for root in board.roots():
        add(tree, root)
    return tree


def objectives_table(board: Board) -> Table:
    t = Table(box=box.SIMPLE, title="目標")
    t.add_column("目標"); t.add_column("分區"); t.add_column("價值", justify="right"); t.add_column("擁有者")
    for o in board.objectives:
        t.add_row(o.id, o.sector, str(o.value), Text({"us": "我方", "enemy": "敵方", "none": "無"}[o.owner], style=OWNER_STYLE[o.owner]))
    return t


def enemy_table(board: Board) -> Table:
    t = Table(box=box.SIMPLE, title="已知敵情")
    t.add_column("編號"); t.add_column("層級"); t.add_column("兵種"); t.add_column("分區"); t.add_column("戰力估", justify="right"); t.add_column("最後目擊"); t.add_column("可信度", justify="right")
    for c in board.enemy_known:
        t.add_row(c.id, ECHELON_ZH[c.echelon], c.type, c.sector, f"{int(round(c.strength_est * 100))}%", f"t{c.last_seen}", f"{c.confidence:.1f}")
    return t


def events_panel(board: Board, n: int = 8) -> Panel:
    lines = [Text(f"t{e.t} [{e.kind}] {e.text}") for e in board.events[-n:]] or [Text("（尚無事件）", style="dim")]
    return Panel(Group(*lines), title=f"事件流（最近 {n} 筆）", border_style="blue")


def render_board(board: Board, console: Console | None = None) -> None:
    console = console or Console()
    header = f"[bold]{board.battle_id}[/]  t={board.t}{'回合' if board.time_unit == 'turn' else '秒'}  階段={board.phase}  規模={board.scale}  本場推翻={board.overrides_this_battle}"
    console.print(Panel(header, border_style="green"))
    console.print(map_table(board))
    console.print(Panel(orbat_tree(board), border_style="green"))
    console.print(Panel(Group(objectives_table(board), enemy_table(board)), border_style="red"))
    console.print(events_panel(board))
