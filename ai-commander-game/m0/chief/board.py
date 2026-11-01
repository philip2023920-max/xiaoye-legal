"""AI 戰情板（Board）：所有層共用的資料合約。

引擎往裡寫、LLM 從裡讀、玩家側欄看它、戰報卡回放它。
格式說明見 docs/09-board-schema.md。改這個檔案等於改合約，要連文件與測試一起改。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator

SCHEMA_VERSION = "0.1"

# ---- 列舉（用 Literal 讓 JSON 直接對得上，不必轉 Enum）----
Echelon = Literal["squad", "platoon", "company", "battalion", "brigade", "army_group"]
ECHELON_RANK: dict[str, int] = {
    "squad": 0, "platoon": 1, "company": 2, "battalion": 3, "brigade": 4, "army_group": 5,
}
ECHELON_ZH: dict[str, str] = {
    "squad": "班", "platoon": "排", "company": "連", "battalion": "營", "brigade": "旅", "army_group": "軍團",
}
Terrain = Literal["open", "hill", "forest", "town", "river"]
Owner = Literal["us", "enemy", "none"]
UnitType = Literal["infantry", "mg", "armor", "mixed"]
UnitState = Literal["idle", "moving", "engaged", "routed", "destroyed"]
TaskType = Literal["seize", "hold", "flank", "withdraw", "support", "reserve"]
Controller = Literal["ai", "player"]
Scale = Literal["skirmish", "battle", "grand"]
Phase = Literal["early", "mid", "late"]
TimeUnit = Literal["turn", "second"]

COL_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class BoardError(ValueError):
    """載入或驗證戰情板失敗時丟出，訊息是人話（繁中），直接印給老闆看。"""


class Task(BaseModel):
    """任務式命令：LLM 與玩家都只能下這種令，細節由編制 AI 執行。"""
    type: TaskType
    target: str = Field(description="分區 id（如 B2）；support 時可為友軍單位 id")


class Sector(BaseModel):
    id: str
    terrain: Terrain = "open"
    owner: Owner = "none"
    contested: bool = False
    cover: float = Field(0.2, ge=0.0, le=1.0, description="掩蔽度，影響戰損")
    objective: Optional[str] = Field(None, description="此分區的目標 id（若有）")


class MapGrid(BaseModel):
    cols: int = Field(ge=1, le=26)
    rows: int = Field(ge=1, le=99)
    sectors: dict[str, Sector]

    def expected_ids(self) -> list[str]:
        return [f"{COL_LETTERS[c]}{r}" for r in range(1, self.rows + 1) for c in range(self.cols)]

    @model_validator(mode="after")
    def _check_grid(self) -> "MapGrid":
        expected = set(self.expected_ids())
        got = set(self.sectors)
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        if missing:
            raise ValueError(f"地圖 {self.cols}x{self.rows} 缺少分區：{', '.join(missing)}")
        if extra:
            raise ValueError(f"地圖上有不存在於格線的分區：{', '.join(extra)}")
        for sid, sec in self.sectors.items():
            if sec.id != sid:
                raise ValueError(f"分區鍵「{sid}」與內容的 id「{sec.id}」不一致")
        return self


class Unit(BaseModel):
    """友軍部隊樹的一個節點。children 不存檔，由 parent 反推。"""
    id: str
    name: str
    echelon: Echelon
    type: UnitType = "infantry"
    parent: Optional[str] = None
    strength: float = Field(1.0, ge=0.0, le=1.0, description="戰力 0～1")
    state: UnitState = "idle"
    sector: str
    task: Optional[Task] = None
    controlled_by: Controller = "ai"


class Contact(BaseModel):
    """已知敵情：只記「看過什麼」，不是敵方真實狀態。"""
    id: str
    echelon: Echelon
    type: UnitType = "infantry"
    sector: str
    strength_est: float = Field(1.0, ge=0.0, le=1.0)
    last_seen: int = Field(description="最後目擊的 t")
    confidence: float = Field(0.5, ge=0.0, le=1.0)


class Objective(BaseModel):
    id: str
    sector: str
    value: int = Field(ge=1)
    owner: Owner = "none"


class Event(BaseModel):
    t: int
    kind: str = Field(description="routed / seized / contact / order / override / info …")
    text: str
    unit: Optional[str] = None
    sector: Optional[str] = None


class Fog(BaseModel):
    visible_sectors: list[str] = Field(default_factory=list)


class Board(BaseModel):
    schema_version: str = SCHEMA_VERSION
    battle_id: str
    t: int = Field(ge=0)
    time_unit: TimeUnit = "turn"
    phase: Phase = "early"
    scale: Scale = "battle"
    map: MapGrid
    orbat: list[Unit] = Field(default_factory=list, description="友軍部隊樹（扁平列表，parent 連結）")
    enemy_known: list[Contact] = Field(default_factory=list)
    objectives: list[Objective] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    fog: Fog = Field(default_factory=Fog)
    overrides_this_battle: int = Field(0, ge=0)

    # ---- 一致性檢查：把「半對」的戰局檔擋在門外 ----
    @model_validator(mode="after")
    def _check_links(self) -> "Board":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"戰情板版本「{self.schema_version}」不是目前支援的「{SCHEMA_VERSION}」，請用工具轉換或改用新範例")
        sectors = self.map.sectors
        dup = sorted(i for i, n in Counter(u.id for u in self.orbat).items() if n > 1)
        if dup:
            raise ValueError(f"部隊 id 重複：{', '.join(dup)}")
        clash = sorted(u.id for u in self.orbat if u.id in sectors)
        if clash:
            raise ValueError(f"部隊 id 不可與分區 id 同名：{', '.join(clash)}")
        by_id = {u.id: u for u in self.orbat}
        for u in self.orbat:
            if u.sector not in sectors:
                raise ValueError(f"部隊 {u.id} 所在分區「{u.sector}」不在地圖上")
            if u.parent is not None:
                if u.parent == u.id:
                    raise ValueError(f"部隊 {u.id} 的 parent 不能是自己")
                p = by_id.get(u.parent)
                if p is None:
                    raise ValueError(f"部隊 {u.id} 的 parent「{u.parent}」不存在")
                if ECHELON_RANK[p.echelon] <= ECHELON_RANK[u.echelon]:
                    raise ValueError(
                        f"部隊 {u.id}（{ECHELON_ZH[u.echelon]}）的上級 {p.id} 是 {ECHELON_ZH[p.echelon]}，層級必須更高"
                    )
            if u.task is not None:
                tgt = u.task.target
                if u.task.type == "support":
                    if tgt not in by_id:
                        raise ValueError(f"部隊 {u.id} 的 support 目標「{tgt}」必須是友軍單位 id")
                    if tgt == u.id:
                        raise ValueError(f"部隊 {u.id} 不能 support 自己")
                elif tgt not in sectors:
                    raise ValueError(f"部隊 {u.id} 的任務 {u.task.type} 目標「{tgt}」必須是分區 id")
        dup_c = sorted(i for i, n in Counter(c.id for c in self.enemy_known).items() if n > 1)
        if dup_c:
            raise ValueError(f"敵情 id 重複：{', '.join(dup_c)}")
        for c in self.enemy_known:
            if c.sector not in sectors:
                raise ValueError(f"敵情 {c.id} 所在分區「{c.sector}」不在地圖上")
        dup_o = sorted(i for i, n in Counter(o.id for o in self.objectives).items() if n > 1)
        if dup_o:
            raise ValueError(f"目標 id 重複：{', '.join(dup_o)}")
        obj_ids = {o.id for o in self.objectives}
        for o in self.objectives:
            if o.sector not in sectors:
                raise ValueError(f"目標 {o.id} 的分區「{o.sector}」不在地圖上")
            if sectors[o.sector].objective != o.id:
                marked = sectors[o.sector].objective
                raise ValueError(f"目標 {o.id} 在分區 {o.sector}，但該分區標記的目標是「{marked}」（兩邊必須一致）")
        for sid, sec in sectors.items():
            if sec.objective is not None and sec.objective not in obj_ids:
                raise ValueError(f"分區 {sid} 標記了目標「{sec.objective}」，但目標表裡沒有")
        for v in self.fog.visible_sectors:
            if v not in sectors:
                raise ValueError(f"迷霧的可見分區「{v}」不在地圖上")
        return self

    # ---- 查詢工具 ----
    def unit(self, unit_id: str) -> Unit:
        for u in self.orbat:
            if u.id == unit_id:
                return u
        raise KeyError(unit_id)

    def children(self, unit_id: str) -> list[Unit]:
        return [u for u in self.orbat if u.parent == unit_id]

    def roots(self) -> list[Unit]:
        return [u for u in self.orbat if u.parent is None]

    def units_in(self, sector_id: str) -> list[Unit]:
        """分區內的友軍（不含已殲滅；部隊樹仍保留殲滅單位以供回放）。"""
        return [u for u in self.orbat if u.sector == sector_id and u.state != "destroyed"]

    def contacts_in(self, sector_id: str) -> list[Contact]:
        return [c for c in self.enemy_known if c.sector == sector_id]

    # ---- 給 LLM 的壓縮版（英文鍵值，省 token）----
    def compact(self, max_events: int = 5) -> dict:
        sectors = {}
        for sid, s in self.map.sectors.items():
            parts = [s.terrain, s.owner]
            if s.objective:
                parts.append(s.objective)
            if s.contested:
                parts.append("contested")
            sectors[sid] = "/".join(parts)
        alive_ids = {u.id for u in self.orbat if u.state != "destroyed"}
        friendly = []
        for u in self.orbat:
            if u.state == "destroyed":
                continue
            row = {
                "id": u.id, "ech": u.echelon, "type": u.type, "str": round(u.strength, 2),
                "state": u.state, "sector": u.sector,
                "task": f"{u.task.type} {u.task.target}" if u.task else None,
            }
            if u.parent and u.parent in alive_ids:  # 上級已殲滅就不留懸空引用
                row["parent"] = u.parent
            if u.controlled_by == "player":
                row["ctrl"] = "player"
            friendly.append(row)
        enemy = [
            {"id": c.id, "ech": c.echelon, "type": c.type, "sector": c.sector,
             "str": round(c.strength_est, 2), "seen": c.last_seen, "conf": round(c.confidence, 2)}
            for c in self.enemy_known
        ]
        return {
            "t": self.t, "unit": self.time_unit, "phase": self.phase, "scale": self.scale,
            "map": {"size": f"{self.map.cols}x{self.map.rows}", "sectors": sectors},
            "visible": self.fog.visible_sectors or "all",  # 空列表＝全圖可見，講明白給 LLM
            "friendly": friendly,
            "enemy": enemy,
            "objectives": [{"id": o.id, "sector": o.sector, "value": o.value, "owner": o.owner} for o in self.objectives],
            "events": [f"t{e.t} {e.text}" for e in self.events[-max_events:]],
            "overrides": self.overrides_this_battle,
        }

    def compact_json(self, max_events: int = 5) -> str:
        return json.dumps(self.compact(max_events), ensure_ascii=False, separators=(",", ":"))


def estimate_tokens(text: str) -> int:
    """粗估 token：ASCII 每 4 字元算 1 個，非 ASCII（中文等）每字算 1 個。
    只用於離線檢查預算；正式計量以供應商回傳的 usage 為準。"""
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return ascii_chars // 4 + (len(text) - ascii_chars)


_PYDANTIC_ZH = {
    "missing": "缺少這個欄位",
    "literal_error": "值不在允許的選項內（允許：{expected}）",
    "greater_than_equal": "必須 ≥ {ge}",
    "less_than_equal": "必須 ≤ {le}",
    "int_parsing": "必須是整數",
    "int_type": "必須是整數",
    "float_parsing": "必須是數字",
    "float_type": "必須是數字",
    "string_type": "必須是文字",
    "bool_type": "必須是 true/false",
    "list_type": "必須是列表",
    "dict_type": "必須是物件（鍵值表）",
    "model_type": "必須是物件（鍵值表）",
    "extra_forbidden": "多了不認識的欄位",
}


def _humanize(err: ValidationError) -> str:
    lines = []
    for e in err.errors():
        loc = ".".join(str(x) for x in e["loc"]) or "（整體）"
        msg = e["msg"]
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        else:
            template = _PYDANTIC_ZH.get(e.get("type", ""))
            if template:
                try:
                    msg = template.format(**(e.get("ctx") or {}))
                except (KeyError, IndexError):
                    msg = template
        lines.append(f"- {loc}：{msg}")
    return "\n".join(lines)


def board_from_dict(data: dict) -> Board:
    try:
        return Board.model_validate(data)
    except ValidationError as err:
        raise BoardError("戰情板內容有問題：\n" + _humanize(err)) from None


def load_board(path: str | Path) -> Board:
    p = Path(path)
    if not p.exists():
        raise BoardError(f"找不到戰情板檔案：{p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))  # 容忍記事本／Out-File 的 BOM
    except json.JSONDecodeError as err:
        raise BoardError(f"{p} 不是合法的 JSON（第 {err.lineno} 行附近）") from None
    return board_from_dict(data)


def save_board(board: Board, path: str | Path) -> None:
    Path(path).write_text(board.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
