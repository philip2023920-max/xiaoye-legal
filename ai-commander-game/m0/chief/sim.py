"""M0 模擬會戰引擎（回合制、連級、無 LLM）。規則與數字全部來自 docs/10-sim-rules.md 與 rules/<era>.json（戰鬥模型 v1）。

用法（程式）：
    battle = Battle(board, enemy_units, seed=7)
    result = battle.run(friendly_script, enemy_script)
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from .board import Board, BoardError, Contact, Event, Task, TaskType, TimeOfDay, Unit, Weather, save_board
from .formation_ai import decide_move, split_company_task
from .grid import distance, neighbors
from .rules import Rules, load_rules

# ---- 狀態門檻與結束條件（§5、§7）----
ROUT_THRESHOLD = 0.30
DESTROY_THRESHOLD = 0.05
MAX_TURNS = 10
END_STRENGTH_RATIO = 0.30

Side = Literal["us", "enemy"]
OTHER: dict[str, str] = {"us": "enemy", "enemy": "us"}
WEATHER_ZH = {"clear": "晴", "rain": "雨", "snow": "雪", "fog": "霧"}
TIME_ZH = {"day": "日間", "night": "夜間"}


class Order(BaseModel):
    """一條任務式命令。LLM（03）、玩家（05）、劇本（02）都用這個格式。issuer 決定連令能否拆給直轄排。"""
    unit_id: str
    task: TaskType
    target: str
    reason: str = ""
    issuer: Literal["ai", "player"] = "ai"


class Script(BaseModel):
    """照回合排好的命令：{"1": [...], "3": [...]}。enemy 劇本另含敵方初始部隊與天氣／時段變化。"""
    units: list[Unit] = Field(default_factory=list)
    orders: dict[str, list[Order]] = Field(default_factory=dict)
    weather_changes: dict[str, Weather] = Field(default_factory=dict, description="回合 → 天氣（clear/rain/snow/fog）")
    time_changes: dict[str, TimeOfDay] = Field(default_factory=dict, description="回合 → 時段（day/night）")

    def for_turn(self, t: int) -> list[Order]:
        return self.orders.get(str(t), [])


def load_script(path: str | Path) -> Script:
    p = Path(path)
    if not p.exists():
        raise BoardError(f"找不到劇本檔案：{p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        for u in data.get("units", []):
            if u.get("type") == "armor":
                u["type"] = "tank"
        return Script.model_validate(data)
    except json.JSONDecodeError as err:
        raise BoardError(f"{p} 不是合法的 JSON（第 {err.lineno} 行附近）") from None
    except ValidationError as err:
        raise BoardError(f"劇本 {p} 格式有問題：{err.errors()[0]['msg']}") from None


@dataclass
class TurnReport:
    t: int
    events: list[Event] = field(default_factory=list)
    moves: dict[str, str] = field(default_factory=dict)      # unit_id -> 新分區
    damage: dict[str, float] = field(default_factory=dict)   # unit_id -> 本回合受損


@dataclass
class BattleResult:
    battle_id: str
    turns_played: int
    end_reason: Literal["turns", "strength", "quit"]
    winner: Literal["us", "enemy", "draw"]
    score_us: int
    score_enemy: int
    strength_us: float
    strength_enemy: float
    snapshots: list[Path] = field(default_factory=list)

    def summary(self) -> str:
        w = {"us": "我方勝", "enemy": "敵方勝", "draw": "平手"}[self.winner]
        why = {"turns": "10 回合打完", "strength": "一方戰力低於初始 30%", "quit": "總司令提前結束"}[self.end_reason]
        return (f"結果：{w}（{why}，共 {self.turns_played} 回合）｜據點分 我 {self.score_us} : 敵 {self.score_enemy}"
                f"｜剩餘總戰力 我 {self.strength_us:.2f} : 敵 {self.strength_enemy:.2f}")


def _fires(u: Unit) -> bool:
    return u.state not in ("routed", "destroyed") and not (u.task is not None and u.task.type == "withdraw")


def resolve_sector_combat(
    us: list[Unit], enemy: list[Unit], rules: Rules, cover_us: float, cover_en: float, fire_mult: float = 1.0,
    rng: random.Random | None = None, support_us: list[Unit] | None = None, support_en: list[Unit] | None = None,
) -> dict[str, float]:
    """同一分區的交戰解算（§4 v1）。回傳每個單位本回合受到的傷害（尚未扣除）。

    對每個目標 t：Σ_攻方 a.strength × 混合火力(a→t) × share(t) × (1 − 守方掩蔽) × K × 天氣時段倍率，
    share(t)＝t 戰力 ÷ 該側所有未殲滅目標戰力。support_*：相鄰分區的間接火力單位（迫砲），只打不被打。
    撤退中與潰散的單位不開火但會被打；rng 給定時每筆傷害乘以 0.9～1.1 的亂數。
    """
    def damage_to(targets: list[Unit], attackers: list[Unit], cover: float) -> dict[str, float]:
        alive = [t for t in targets if t.state != "destroyed"]
        pool = sum(t.strength for t in alive)
        shooters = [a for a in attackers if _fires(a)]
        out: dict[str, float] = {}
        if pool <= 0 or not shooters:
            return out
        for t in alive:
            share = t.strength / pool
            total = sum(a.strength * rules.effective_fire(a.type, t.type) for a in shooters)
            dmg = total * share * (1.0 - cover) * rules.K * fire_mult
            if dmg <= 0:
                continue
            if rng is not None:
                dmg *= rng.uniform(0.9, 1.1)
            out[t.id] = dmg
        return out

    result = damage_to(enemy, us + list(support_us or []), cover_en)
    result.update(damage_to(us, enemy + list(support_en or []), cover_us))
    return result


class Battle:
    def __init__(
        self,
        board: Board,
        enemy_units: list[Unit],
        seed: int | None = None,
        variance: bool | None = None,
        out_dir: str | Path | None = None,
        rules: Rules | None = None,
    ) -> None:
        self.board = board.model_copy(deep=True)
        self.enemy = [u.model_copy(deep=True) for u in enemy_units]
        self.rules = rules or load_rules(self.board.era)
        for side in ("us", "enemy"):
            for u in self.leaves(side):
                if self.rules.resolve_type(u.type) not in self.rules.units:
                    raise BoardError(f"{'我方' if side == 'us' else '敵方'}單位 {u.id} 的兵種「{u.type}」不在 {self.rules.era} 規則表內"
                                     f"（mixed 只能用在有子排的連）。可用：{', '.join(self.rules.units)}")
        self.rng = random.Random(seed) if seed is not None else None
        self.variance = variance if variance is not None else (seed is not None)
        self.out_dir = Path(out_dir) if out_dir is not None else Path("battles") / board.battle_id
        self.t = self.board.t
        self.start_t = self.board.t
        self.initial = {"us": self.total_strength("us"), "enemy": self.total_strength("enemy")}
        self.snapshots: list[Path] = []
        self.end_reason: Optional[str] = None
        self.out_dir.mkdir(parents=True, exist_ok=True)
        save_board(self.board, self.out_dir / f"t{self.start_t}.json")  # 開局快照（推翻紀錄的 snapshot_ref 用）

    # ---- 查詢 ----
    def units(self, side: str) -> list[Unit]:
        return self.board.orbat if side == "us" else self.enemy

    def leaves(self, side: str) -> list[Unit]:
        us = self.units(side)
        parents = {u.parent for u in us if u.parent}
        return [u for u in us if u.id not in parents]

    def total_strength(self, side: str) -> float:
        return sum(u.strength for u in self.leaves(side) if u.state != "destroyed")

    def own_sectors(self, side: str) -> list[str]:
        return [sid for sid, s in self.board.map.sectors.items() if s.owner == side]

    def _by_id(self, side: str) -> dict[str, Unit]:
        return {u.id: u for u in self.units(side)}

    def engineer_in(self, side: str, sector_id: str, holding_only: bool = False) -> bool:
        """本方有非潰散工兵排在該格；holding_only 時還要任務是 hold 該格（路過不算）。"""
        for u in self.leaves(side):
            if u.sector == sector_id and self.rules.resolve_type(u.type) == "engineer" and u.state not in ("routed", "destroyed"):
                if not holding_only or (u.task is not None and u.task.type == "hold" and u.task.target == sector_id):
                    return True
        return False

    def engineer_sectors(self, side: str) -> set[str]:
        return {u.sector for u in self.leaves(side)
                if self.rules.resolve_type(u.type) == "engineer" and u.state not in ("routed", "destroyed")}

    def cover_for(self, side: str, sector_id: str) -> float:
        s = self.board.map.sectors[sector_id]
        return self.rules.effective_cover(s.terrain, self.board.weather, self.board.time_of_day, s.cover,
                                          engineer_holding=self.engineer_in(side, sector_id, holding_only=True))

    def blocked_sectors(self, side: str, unit: Unit, engineer_sectors: set[str] | None = None) -> set[str]:
        """這個單位進不去的分區（戰車 vs 森林／河川；河川有本方工兵在場就能過）。
        engineer_sectors 給定時以它為準（回合開始的工兵位置，結果不隨單位 id 順序變）。"""
        eng = engineer_sectors if engineer_sectors is not None else self.engineer_sectors(side)
        out: set[str] = set()
        for sid, s in self.board.map.sectors.items():
            if not self.rules.can_enter(unit.type, s.terrain, engineer_present=(sid in eng)):
                out.add(sid)
        return out

    # ---- 回合 ----
    def set_conditions(self, weather: str | None, time_of_day: str | None, report: TurnReport) -> None:
        if weather and weather not in self.rules.weather:
            raise BoardError(f"天氣「{weather}」不在 {self.rules.era} 規則表內。可用：{', '.join(self.rules.weather)}")
        if time_of_day and time_of_day not in self.rules.time:
            raise BoardError(f"時段「{time_of_day}」不在 {self.rules.era} 規則表內。可用：{', '.join(self.rules.time)}")
        if weather and weather != self.board.weather:
            self.board.weather = weather  # type: ignore[assignment]
            report.events.append(Event(t=self.t, kind="weather", text=f"天氣轉{WEATHER_ZH.get(weather, weather)}"))
        if time_of_day and time_of_day != self.board.time_of_day:
            self.board.time_of_day = time_of_day  # type: ignore[assignment]
            report.events.append(Event(t=self.t, kind="weather", text=f"進入{TIME_ZH.get(time_of_day, time_of_day)}"))

    def order_problem(self, side: str, o: Order) -> str | None:
        """引擎自己的最後防線（驗證器 V1/V3 的子集）：壞令不准進引擎，否則快照會寫壞。"""
        by_id = self._by_id(side)
        u = by_id.get(o.unit_id)
        if u is None or u.state == "destroyed":
            return f"單位 {o.unit_id} 不存在或已殲滅"
        if o.task == "support":
            b = by_id.get(o.target)
            if b is None or b.state == "destroyed" or o.target == o.unit_id:
                return f"support 目標 {o.target} 不是存活的其他友軍"
        elif o.target not in self.board.map.sectors:
            return f"任務 {o.task} 的目標「{o.target}」不是分區 id"
        return None

    def apply_orders(self, side: str, orders: list[Order], report: TurnReport) -> None:
        """同一回合：連的命令拆給子排，但「本回合有自己命令的排」以自己的為準（§3）。"""
        by_id = self._by_id(side)
        who = "參謀長" if side == "us" else "敵軍"
        valid = [o for o in orders if self.order_problem(side, o) is None]
        for o in orders:
            problem = self.order_problem(side, o)
            if problem:
                report.events.append(Event(t=self.t, kind="info", text=f"{who}的命令被引擎退回：{problem}"))
        explicit = {o.unit_id for o in valid}

        def has_children(uid: str) -> bool:
            return any(c.parent == uid for c in self.units(side))
        for o in sorted(valid, key=lambda x: 0 if has_children(x.unit_id) else 1):
            u = by_id[o.unit_id]
            task = Task(type=o.task, target=o.target)
            children = [c for c in self.units(side) if c.parent == u.id]
            if children:
                for cid, ct in split_company_task(u, children, task, include_player=(o.issuer == "player")).items():
                    if cid in explicit:
                        continue  # 這個排本回合有自己的命令，連令不覆蓋
                    by_id[cid].task = ct  # 參謀長的連令不碰直轄排；玩家的連令可以
                u.task = task
            else:
                u.task = task
            if side == "us":
                task_zh = {"seize": "奪取", "hold": "固守", "flank": "側翼包抄", "withdraw": "撤往", "support": "支援", "reserve": "預備於"}[o.task]
                report.events.append(Event(t=self.t, kind="order", text=f"{who}令 {u.name} {task_zh} {o.target}", unit=u.id, sector=o.target if o.target in self.board.map.sectors else None))

    def movement(self, report: TurnReport) -> None:
        grid = self.board.map
        for side in ("us", "enemy"):
            own = self.own_sectors(side)
            by_id = self._by_id(side)
            leaves = self.leaves(side)
            eng = self.engineer_sectors(side)                      # 回合開始的工兵位置，過河判定以此為準（§2）
            hostile = {e.sector for e in self.leaves(OTHER[side]) if e.state != "destroyed"}
            for u in sorted(leaves, key=lambda x: x.id):
                if u.state not in ("routed", "destroyed"):
                    u.state = "idle"  # 每回合先歸零，交戰階段再標 engaged
                if u.state == "destroyed":
                    continue
                mobility = self.rules.mobility(u.type, self.board.weather)
                if mobility < 1.0 and self.t % 2 == 1:
                    continue  # 機動力減半：只在偶數回合移動（§2 v1）
                steps = 1 if u.state == "routed" else self.rules.unit(u.type).speed   # 潰散只退 1 格（§2）
                avoid = self.blocked_sectors(side, u, eng)
                moved = False
                for _ in range(steps):
                    dest = decide_move(u, grid, leaves, own, by_id, avoid=avoid)
                    if not dest or dest == u.sector or dest in avoid:
                        break
                    u.sector = dest
                    moved = True
                    if dest in hostile:
                        break  # 進到有敵軍的格子就停下（多格移動不穿越敵軍，§2）
                if moved:
                    report.moves[u.id] = u.sector
                    if u.state not in ("routed", "destroyed"):
                        # 到達任務目標那回合就算「到位」→ idle；還在路上 → moving（§5）
                        arrived = u.task is not None and u.task.type != "support" and u.sector == u.task.target
                        u.state = "idle" if arrived else "moving"

    def combat(self, report: TurnReport) -> None:
        sectors = {u.sector for u in self.leaves("us")} | {u.sector for u in self.leaves("enemy")}
        all_units = {u.id: u for u in self.leaves("us")} | {u.id: u for u in self.leaves("enemy")}
        damages: dict[str, float] = {}
        fire_mult = self.rules.fire_mult(self.board.weather, self.board.time_of_day)
        for sid in sorted(sectors):
            us_all = [u for u in self.leaves("us") if u.sector == sid and u.state != "destroyed"]
            en_all = [u for u in self.leaves("enemy") if u.sector == sid and u.state != "destroyed"]
            us_active = [u for u in us_all if u.state != "routed"]
            en_active = [u for u in en_all if u.state != "routed"]
            if not us_active or not en_active:
                continue  # 要有雙方「能戰鬥」的單位才交火；潰散單位只會被打
            adj = set(neighbors(self.board.map, sid))
            sup_us = [u for u in self.leaves("us") if u.sector in adj and self.rules.unit(u.type).indirect and _fires(u)]
            sup_en = [u for u in self.leaves("enemy") if u.sector in adj and self.rules.unit(u.type).indirect and _fires(u)]
            dmg = resolve_sector_combat(us_all, en_all, self.rules, self.cover_for("us", sid), self.cover_for("enemy", sid), fire_mult,
                                        self.rng if self.variance else None, sup_us, sup_en)
            for uid, d in dmg.items():
                damages[uid] = damages.get(uid, 0.0) + d
            for u in us_active + en_active:
                u.state = "engaged"
        for uid, d in damages.items():
            u = all_units[uid]
            u.strength = max(0.0, round(u.strength - d, 4))
            report.damage[uid] = round(d, 4)

    def transitions(self, report: TurnReport) -> None:
        for side in ("us", "enemy"):
            for u in self.leaves(side):
                if u.state == "destroyed":
                    continue
                if u.strength <= DESTROY_THRESHOLD:
                    u.state = "destroyed"
                    u.task = None
                    report.events.append(Event(t=self.t, kind="destroyed", text=f"{'我方' if side == 'us' else '敵方'} {u.name} 在 {u.sector} 被殲滅", unit=u.id, sector=u.sector))
                elif u.strength < ROUT_THRESHOLD and u.state != "routed":
                    u.state = "routed"
                    u.task = None
                    report.events.append(Event(t=self.t, kind="routed", text=f"{'我方' if side == 'us' else '敵方'} {u.name} 在 {u.sector} 潰散", unit=u.id, sector=u.sector))

    def ownership(self, report: TurnReport) -> None:
        for sid, s in self.board.map.sectors.items():
            us_here = any(u.sector == sid and u.state not in ("routed", "destroyed") for u in self.leaves("us"))
            en_here = any(u.sector == sid and u.state not in ("routed", "destroyed") for u in self.leaves("enemy"))
            before = s.owner
            if us_here and en_here:
                s.contested = True
            elif us_here:
                s.owner, s.contested = "us", False
            elif en_here:
                s.owner, s.contested = "enemy", False
            else:
                s.contested = False
            if s.owner != before:
                report.events.append(Event(t=self.t, kind="seized", text=f"{'我方' if s.owner == 'us' else '敵方'}取得 {sid}{'（目標 ' + s.objective + '）' if s.objective else ''}", sector=sid))
        for o in self.board.objectives:
            o.owner = self.board.map.sectors[o.sector].owner

    def visible_sectors(self) -> set[str]:
        """視距（§2 v1）：每個未殲滅友軍排以 rules.sight 的曼哈頓距離看得見；0＝只看自己那格。"""
        visible: set[str] = set()
        for u in self.leaves("us"):
            if u.state == "destroyed":
                continue
            sight = self.rules.sight(u.type, self.board.weather, self.board.time_of_day)
            for sid in self.board.map.sectors:
                if distance(u.sector, sid) <= sight:
                    visible.add(sid)
        return visible

    def intelligence(self, report: TurnReport) -> None:
        visible = self.visible_sectors()
        self.board.fog.visible_sectors = sorted(visible)
        known = {c.id: c for c in self.board.enemy_known}
        for e in self.leaves("enemy"):
            if e.state == "destroyed":
                if e.sector in visible and e.id in known:
                    del known[e.id]  # 親眼看到被殲滅，從敵情拿掉
                continue
            if e.sector not in visible:
                continue
            new = e.id not in known
            known[e.id] = Contact(id=e.id, echelon=e.echelon, type=e.type, sector=e.sector,
                                  strength_est=round(e.strength, 2), last_seen=self.t, confidence=0.9)
            if new:
                report.events.append(Event(t=self.t, kind="contact", text=f"在 {e.sector} 發現敵 {e.name}", unit=e.id, sector=e.sector))
        self.board.enemy_known = list(known.values())

    def aggregate(self) -> None:
        """連級節點：戰力＝子排平均，分區＝最強存活子排，狀態由子排推。"""
        for side in ("us", "enemy"):
            units = self.units(side)
            for u in units:
                kids = [c for c in units if c.parent == u.id]
                if not kids:
                    continue
                u.strength = round(sum(c.strength for c in kids) / len(kids), 4)
                alive = [c for c in kids if c.state != "destroyed"]
                if not alive:
                    u.state = "destroyed"
                elif all(c.state == "routed" for c in alive):
                    u.state = "routed"
                elif any(c.state == "engaged" for c in alive):
                    u.state = "engaged"
                elif any(c.state == "moving" for c in alive):
                    u.state = "moving"
                else:
                    u.state = "idle"
                if alive:
                    u.sector = max(alive, key=lambda c: (c.strength, c.id)).sector

    def step(self, friendly_orders: list[Order], enemy_orders: list[Order], weather: str | None = None, time_of_day: str | None = None) -> TurnReport:
        self.t += 1
        self.board.t = self.t
        self.board.phase = "early" if self.t <= 3 else ("mid" if self.t <= 7 else "late")
        report = TurnReport(t=self.t)
        self.set_conditions(weather, time_of_day, report)
        self.apply_orders("us", friendly_orders, report)
        self.apply_orders("enemy", enemy_orders, report)
        self.movement(report)
        self.combat(report)
        self.transitions(report)
        self.ownership(report)
        self.intelligence(report)
        self.aggregate()
        self.board.events.extend(report.events)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"t{self.t}.json"
        save_board(self.board, path)
        self.snapshots.append(path)
        # 結束判定：戰力崩潰優先於回合數（§7）
        for side in ("us", "enemy"):
            if self.initial[side] > 0 and self.total_strength(side) < END_STRENGTH_RATIO * self.initial[side]:
                self.end_reason = "strength"
        if self.end_reason is None and self.t >= MAX_TURNS:
            self.end_reason = "turns"
        return report

    def finished(self) -> bool:
        return self.end_reason is not None

    def scores(self) -> tuple[int, int]:
        su = sum(o.value for o in self.board.objectives if o.owner == "us")
        se = sum(o.value for o in self.board.objectives if o.owner == "enemy")
        return su, se

    def result(self) -> BattleResult:
        su, se = self.scores()
        stu, ste = self.total_strength("us"), self.total_strength("enemy")
        if su != se:
            winner = "us" if su > se else "enemy"
        elif abs(stu - ste) > 1e-9:
            winner = "us" if stu > ste else "enemy"
        else:
            winner = "draw"
        return BattleResult(
            battle_id=self.board.battle_id, turns_played=self.t - self.start_t, end_reason=self.end_reason or "turns",
            winner=winner, score_us=su, score_enemy=se, strength_us=round(stu, 3), strength_enemy=round(ste, 3),
            snapshots=list(self.snapshots),
        )

    def run(self, friendly: Script, enemy: Script, on_turn=None) -> BattleResult:
        while not self.finished():
            t = self.t + 1
            report = self.step(friendly.for_turn(t), enemy.for_turn(t), enemy.weather_changes.get(str(t)), enemy.time_changes.get(str(t)))
            if on_turn:
                on_turn(self, report)
        return self.result()
