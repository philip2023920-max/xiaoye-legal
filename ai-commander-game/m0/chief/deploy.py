"""部署階段（施工單 08，D11）：點數預算內配部隊，或選一種範本；也可請參謀長建議。

規則見 docs/10-sim-rules.md §13。所有數字來自 rules/<era>.json（unit.cost、budget、templates）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .board import Board, BoardError, Unit
from .grid import distance
from .rules import Rules, load_rules


@dataclass
class DeployPlan:
    era: str
    units: list[str]                 # 已解析的兵種名（armor → tank）
    cost: int
    budget: int
    template: str | None = None
    note: str = ""
    placement: dict[str, str] = field(default_factory=dict)   # unit_id → 分區（apply 後填）

    @property
    def remaining(self) -> int:
        return self.budget - self.cost


def plan_from_template(rules: Rules, name: str) -> DeployPlan:
    if name not in rules.templates:
        raise BoardError(f"沒有範本「{name}」。可用：{', '.join(rules.templates)}")
    units = [rules.resolve_type(u) for u in rules.templates[name].units]
    return DeployPlan(era=rules.era, units=units, cost=rules.template_cost(name), budget=rules.budget, template=name)


def plan_from_list(rules: Rules, types: list[str]) -> DeployPlan:
    """自選配比：逗號清單（例如 infantry,infantry,tank）。超過預算或兵種名不對就退回，訊息是人話。"""
    clean = [t.strip().lower() for t in types if t.strip()]
    if not clean:
        raise BoardError("部隊清單是空的")
    bad = [t for t in clean if rules.resolve_type(t) not in rules.units]
    if bad:
        raise BoardError(f"不認識的兵種：{', '.join(bad)}。可用：{', '.join(rules.units)}")
    units = [rules.resolve_type(t) for t in clean]
    cost = sum(rules.unit(u).cost for u in units)
    if cost > rules.budget:
        raise BoardError(f"點數 {cost} 超過預算 {rules.budget}（超出 {cost - rules.budget}）")
    if len(units) > 12:
        raise BoardError(f"最多 12 個排（目前 {len(units)}）")
    return DeployPlan(era=rules.era, units=units, cost=cost, budget=rules.budget)


def deployment_sectors(board: Board, side: str = "us") -> list[str]:
    """可部署的分區：本方擁有的分區，先放有目標的、再放離「非本方目標」最近的，同距依 id。"""
    own = [sid for sid, s in board.map.sectors.items() if s.owner == side]
    if not own:
        raise BoardError(f"地圖上沒有 {side} 擁有的分區，無法部署")
    goals = [o.sector for o in board.objectives if o.owner != side]

    def key(sid: str) -> tuple:
        s = board.map.sectors[sid]
        near = min((distance(sid, g) for g in goals), default=0)
        return (0 if s.objective else 1, near, sid)
    return sorted(own, key=key)


def apply_plan(board: Board, plan: DeployPlan, rules: Rules | None = None, company_id: str = "co-A", company_name: str = "A 連") -> Board:
    """把計畫放上戰情板：一個連（容器）＋ N 個排，輪流放進可部署分區；原本的友軍部隊整個換掉。"""
    rules = rules or load_rules(plan.era)
    sectors = deployment_sectors(board)
    orbat: list[dict] = []
    placement: dict[str, str] = {}
    for i, typ in enumerate(plan.units, 1):
        uid = f"plt-A{i}"
        sector = sectors[(i - 1) % len(sectors)]
        placement[uid] = sector
        orbat.append({"id": uid, "name": f"A{i} {rules.unit(typ).zh or typ}", "echelon": "platoon", "type": typ,
                      "parent": company_id, "strength": 1.0, "state": "idle", "sector": sector, "cost": rules.unit(typ).cost})
    orbat.insert(0, {"id": company_id, "name": company_name, "echelon": "company", "type": "mixed", "parent": None,
                     "strength": 1.0, "state": "idle", "sector": placement["plt-A1"], "cost": plan.cost})
    data = board.model_dump(mode="json")
    data["orbat"] = orbat
    data["era"] = plan.era
    new = Board.model_validate(data)
    plan.placement = placement
    return new


def plan_lines(plan: DeployPlan, rules: Rules) -> list[str]:
    """給終端機看的清單：每個排一行＋點數小結。"""
    out = []
    for i, typ in enumerate(plan.units, 1):
        u = rules.unit(typ)
        where = plan.placement.get(f"plt-A{i}", "")
        out.append(f"plt-A{i:<2} {u.zh or typ:<6} {typ:<9} {u.cost:>3} 點" + (f"  → {where}" if where else ""))
    head = f"範本：{rules.templates[plan.template].zh}（{plan.template}）" if plan.template else "自選配比"
    out.append(f"{head}｜共 {len(plan.units)} 個排｜點數 {plan.cost}/{plan.budget}（剩 {plan.remaining}）")
    return out


# ---- 參謀長建議配比（可選，走閘道 chat，照常計費）----
def suggest_prompt(board: Board, rules: Rules, lang: str = "zh-TW") -> list[dict]:
    from .prompts import LANG_NAME
    tpls = "; ".join(f"{k} ({v.zh}): {', '.join(v.units)} = {rules.template_cost(k)} pts" for k, v in rules.templates.items())
    terrain = ", ".join(f"{sid}:{s.terrain}{'/' + s.objective if s.objective else ''}" for sid, s in board.map.sectors.items() if s.objective or s.terrain != "open")
    enemy = ", ".join(f"{c.type}@{c.sector}" for c in board.enemy_known) or "unknown"
    return [
        {"role": "system", "content": f"You are the chief of staff of a {rules.name} battle. Pick ONE deployment template for our side. "
                                      f"Answer in {LANG_NAME.get(lang, lang)}: first line = the template id exactly as given, second line = one sentence why."},
        {"role": "user", "content": f"Templates: {tpls}. Budget {rules.budget}. Weather {board.weather}, {board.time_of_day}. "
                                    f"Notable terrain/objectives: {terrain}. Known enemy: {enemy}. Which template?"},
    ]


def parse_suggestion(text: str, rules: Rules) -> str | None:
    """回覆裡第一個出現的範本 id（整字比對，不分大小寫）。"""
    for m in re.finditer(r"[A-Za-z_]+", text or ""):
        if m.group(0).lower() in rules.templates:
            return m.group(0).lower()
    return None
