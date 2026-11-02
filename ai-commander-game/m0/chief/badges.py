"""徽章（施工單 06）：全部離線判定，不花 token。規則：docs/10-sim-rules.md §11。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Badge:
    id: str
    name: str
    why: str


def award(winner: str, outcomes: list[str], overrides: int, cost_usd: float,
          objectives_start_us: set[str], objectives_end_us: set[str], local_model: bool = False) -> list[Badge]:
    """規則見 docs/10-sim-rules.md §11。敗局不頒守土；省錢贏家只給雲端模型（本地模型另給「本地派」）。"""
    out: list[Badge] = []
    if outcomes.count("👍") >= 2:
        out.append(Badge("decisive", "果斷總司令", "至少 2 次推翻的後果是 👍"))
    if overrides == 0 and winner == "us":
        out.append(Badge("hands_off", "放手型", "一次都沒推翻就打贏"))
    if winner == "us" and not local_model and cost_usd < 0.01:
        out.append(Badge("thrifty_winner", "省錢贏家", "用雲端模型打贏且本場費用低於 $0.01"))
    if winner == "us" and local_model:
        out.append(Badge("local_hero", "本地派", "用本地模型打贏，零費用"))
    if winner == "us" and objectives_start_us and objectives_start_us <= objectives_end_us:
        out.append(Badge("ground_holder", "守土有責", "獲勝且開局擁有的目標全部守住"))
    return out
