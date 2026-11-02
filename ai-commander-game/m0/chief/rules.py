"""戰鬥模型 v1 的規則資料表（施工單 08，ADR-0013）：載入、檢查、查詢、產生給 LLM 的說明。

真相來源是 rules/<era>.json；程式只做查表與算式（docs/10-sim-rules.md §4 v1）。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from .board import BoardError

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
DEFAULT_ERA = "ww2_1944"
Weather = Literal["clear", "rain", "snow", "fog"]
TimeOfDay = Literal["day", "night"]
UNIT_TYPES = ("infantry", "mg", "mortar", "at", "tank", "recon", "engineer")
TERRAINS = ("open", "hill", "forest", "town", "river")


class UnitStats(BaseModel):
    zh: str = ""
    fire_soft: float = Field(ge=0, le=5)
    fire_hard: float = Field(ge=0, le=5)
    armor: float = Field(ge=0, le=1)
    speed: int = Field(ge=1, le=3)
    sight: int = Field(ge=0, le=5)
    cost: int = Field(ge=1, le=100)
    indirect: bool = False


class TerrainStats(BaseModel):
    zh: str = ""
    cover: float = Field(ge=0, le=0.9)
    armor_passable: bool = True
    engineer_bridges: bool = False


class WeatherStats(BaseModel):
    zh: str = ""
    sight: int = Field(ge=-9, le=2)
    fire_mult: float = Field(gt=0, le=1.5)
    cover_bonus: float = Field(ge=0, le=0.5)
    armor_mobility: float = Field(gt=0, le=1)
    all_mobility: float = Field(gt=0, le=1)


class TimeStats(BaseModel):
    zh: str = ""
    sight: int = Field(ge=-9, le=2)
    fire_mult: float = Field(gt=0, le=1.5)
    cover_bonus: float = Field(ge=0, le=0.5)


class Template(BaseModel):
    zh: str = ""
    units: list[str] = Field(min_length=1, max_length=12)


class Rules(BaseModel):
    era: str
    name: str = ""
    note: str = ""
    K: float = Field(0.25, gt=0, le=1)
    cover_cap: float = Field(0.8, ge=0, le=0.95)
    budget: int = Field(100, ge=10, le=1000)
    units: dict[str, UnitStats]
    aliases: dict[str, str] = Field(default_factory=dict)
    terrain: dict[str, TerrainStats]
    weather: dict[str, WeatherStats]
    time: dict[str, TimeStats]
    engineer: dict[str, float] = Field(default_factory=lambda: {"hold_cover_bonus": 0.1})
    templates: dict[str, Template] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _complete(self) -> "Rules":
        missing = [u for u in UNIT_TYPES if u not in self.units]
        if missing:
            raise ValueError(f"兵種表缺少：{', '.join(missing)}")
        missing = [t for t in TERRAINS if t not in self.terrain]
        if missing:
            raise ValueError(f"地形表缺少：{', '.join(missing)}")
        for w in ("clear", "rain", "snow", "fog"):
            if w not in self.weather:
                raise ValueError(f"天氣表缺少：{w}")
        for t in ("day", "night"):
            if t not in self.time:
                raise ValueError(f"時段表缺少：{t}")
        for a, target in self.aliases.items():
            if target not in self.units:
                raise ValueError(f"別名 {a} 指向不存在的兵種 {target}")
        for name, tpl in self.templates.items():
            bad = [u for u in tpl.units if self.resolve_type(u) not in self.units]
            if bad:
                raise ValueError(f"範本 {name} 含不存在的兵種：{', '.join(bad)}")
            if self.template_cost(name) > self.budget:
                raise ValueError(f"範本 {name} 的點數 {self.template_cost(name)} 超過預算 {self.budget}")
        return self

    # ---- 查詢 ----
    def resolve_type(self, unit_type: str) -> str:
        return self.aliases.get(unit_type, unit_type)

    def unit(self, unit_type: str) -> UnitStats:
        t = self.resolve_type(unit_type)
        if t not in self.units:
            raise BoardError(f"兵種「{unit_type}」不在 {self.era} 規則表內。可用：{', '.join(self.units)}")
        return self.units[t]

    def template_cost(self, name: str) -> int:
        return sum(self.unit(u).cost for u in self.templates[name].units)

    def effective_fire(self, attacker_type: str, target_type: str) -> float:
        """混合火力：fire_soft × (1 − 目標裝甲) + fire_hard × 目標裝甲。"""
        a, t = self.unit(attacker_type), self.unit(target_type)
        return a.fire_soft * (1 - t.armor) + a.fire_hard * t.armor

    def effective_cover(self, terrain: str, weather: str, time_of_day: str, sector_cover: float | None = None,
                        engineer_holding: bool = False) -> float:
        base = sector_cover if sector_cover is not None else self.terrain[terrain].cover
        c = base + self.weather[weather].cover_bonus + self.time[time_of_day].cover_bonus
        if engineer_holding:
            c += self.engineer.get("hold_cover_bonus", 0.0)
        return min(round(c, 4), self.cover_cap)

    def fire_mult(self, weather: str, time_of_day: str) -> float:
        return round(self.weather[weather].fire_mult * self.time[time_of_day].fire_mult, 4)

    def sight(self, unit_type: str, weather: str, time_of_day: str) -> int:
        return max(0, self.unit(unit_type).sight + self.weather[weather].sight + self.time[time_of_day].sight)

    def mobility(self, unit_type: str, weather: str) -> float:
        w = self.weather[weather]
        m = w.all_mobility
        if self.unit(unit_type).armor >= 0.5:
            m = min(m, w.armor_mobility)
        return m

    def can_enter(self, unit_type: str, terrain: str, engineer_present: bool = False) -> bool:
        t = self.terrain[terrain]
        if self.unit(unit_type).armor >= 0.5 and not t.armor_passable:
            return bool(t.engineer_bridges and engineer_present)
        return True

    # ---- 給 LLM 的精簡說明（放進系統提示）----
    def prompt_text(self) -> str:
        rows = [f"- {k}: soft {v.fire_soft}, hard {v.fire_hard}, armor {v.armor}, speed {v.speed}, sight {v.sight}, cost {v.cost}{', indirect fire: also hits adjacent sectors where friendly units are fighting, and is not hit back from there' if v.indirect else ''}"
                for k, v in self.units.items()]
        terr = [f"{k}: cover {v.cover}{'' if v.armor_passable else ', tanks cannot enter' + (' unless an engineer is there' if v.engineer_bridges else '')}" for k, v in self.terrain.items()]
        wx = [f"{k}: fire x{v.fire_mult}, cover +{v.cover_bonus}, sight {v.sight:+d}, tank mobility x{v.armor_mobility}, all mobility x{v.all_mobility}" for k, v in self.weather.items()]
        tm = [f"{k}: fire x{v.fire_mult}, cover +{v.cover_bonus}, sight {v.sight:+d}" for k, v in self.time.items()]
        return ("## Combat model (" + self.name + ")\n"
                "Damage from attacker to target = strength x (soft x (1-target armor) + hard x target armor) x (1 - cover) x K x weather/time fire multiplier. "
                f"K={self.K}; cover is capped at {self.cover_cap}. Units below 30% strength rout. Mobility < 1 means moving only on even turns.\n"
                "Unit types:\n" + "\n".join(rows) + "\nTerrain: " + "; ".join(terr) + "\nWeather: " + "; ".join(wx) + "\nTime: " + "; ".join(tm))


def _humanize(err: ValidationError) -> str:
    out = []
    for e in err.errors():
        loc = ".".join(str(x) for x in e["loc"]) or "（整體）"
        msg = e["msg"]
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        out.append(f"- {loc}：{msg}")
    return "\n".join(out)


@lru_cache(maxsize=8)
def load_rules(era: str = DEFAULT_ERA, rules_dir: str | None = None) -> Rules:
    d = Path(rules_dir) if rules_dir else RULES_DIR
    p = d / f"{era}.json"
    if not p.exists():
        available = ", ".join(sorted(x.stem for x in d.glob("*.json"))) or "（無）"
        raise BoardError(f"找不到世代規則檔「{era}」（{p}）。可用：{available}")
    try:
        return Rules.model_validate(json.loads(p.read_text(encoding="utf-8-sig")))
    except json.JSONDecodeError as err:
        raise BoardError(f"{p} 不是合法的 JSON（第 {err.lineno} 行附近）") from None
    except ValidationError as err:
        raise BoardError(f"規則檔 {p} 有問題：\n" + _humanize(err)) from None
