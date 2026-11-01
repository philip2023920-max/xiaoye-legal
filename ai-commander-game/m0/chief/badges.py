"""徽章（施工單 06）：全部離線判定，不花 token。規則：docs/10-sim-rules.md §11。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Badge:
    id: str
    name: str
    why: str


def award(winner: str, outcomes: list[str], overrides: int, cost_usd: float,
          objectives_start_us: set[str], objectives_end_us: set[str]) -> list[Badge]:
    out: list[Badge] = []
    if outcomes.count("👍") >= 2:
        out.append(Badge("decisive", "果斷總司令", "至少 2 次推翻的後果是 👍"))
    if overrides == 0 and winner == "us":
        out.append(Badge("hands_off", "放手型", "一次都沒推翻就打贏"))
    if winner == "us" and cost_usd < 0.01:
        out.append(Badge("thrifty_winner", "省錢贏家", "打贏且本場費用低於 $0.01"))
    if objectives_start_us and objectives_start_us <= objectives_end_us:
        out.append(Badge("ground_holder", "守土有責", "開局擁有的目標全部守住"))
    return out
