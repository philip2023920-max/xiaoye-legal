"""Token 計量與費用估算（F13）。價格優先序：prices.json 覆寫 > LiteLLM 內建表 > 0（本地模型）。

畫面一律標「估算值，以供應商帳單為準」。
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

PER_MILLION = 1_000_000


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    estimated: bool = False  # True：供應商沒回 usage，用字元÷4 粗估


@dataclass
class Price:
    """每百萬 token 的美元價。"""
    input_per_m: float = 0.0
    output_per_m: float = 0.0
    cache_read_per_m: float = 0.0
    cache_write_per_m: float = 0.0
    source: str = "none"


class PriceTable:
    def __init__(self, overrides_path: str | Path | None = None) -> None:
        self.overrides: dict[str, dict] = {}
        self.updated_at: Optional[str] = None
        if overrides_path and Path(overrides_path).exists():
            data = json.loads(Path(overrides_path).read_text(encoding="utf-8-sig"))
            self.updated_at = data.get("updated_at")
            self.overrides = data.get("models", {})

    def lookup(self, model: str) -> Price:
        key = model
        if key in self.overrides:
            o = self.overrides[key]
            return Price(o.get("input_per_m", 0.0), o.get("output_per_m", 0.0),
                         o.get("cache_read_per_m", 0.0), o.get("cache_write_per_m", 0.0), "prices.json")
        if model.startswith("ollama/") or model.startswith("ollama_chat/"):
            return Price(source="local")
        try:
            import litellm  # 重用 LiteLLM 內建價格表（ADR-0011）
            table = litellm.model_cost
            entry = table.get(model) or table.get(model.split("/", 1)[-1])
        except Exception:  # noqa: BLE001 - 沒裝或載入失敗就視為無價格
            entry = None
        if not entry:
            return Price(source="unknown")
        return Price(
            input_per_m=float(entry.get("input_cost_per_token", 0.0)) * PER_MILLION,
            output_per_m=float(entry.get("output_cost_per_token", 0.0)) * PER_MILLION,
            cache_read_per_m=float(entry.get("cache_read_input_token_cost", 0.0)) * PER_MILLION,
            cache_write_per_m=float(entry.get("cache_creation_input_token_cost", 0.0)) * PER_MILLION,
            source="litellm",
        )

    def cost(self, model: str, usage: Usage) -> float:
        p = self.lookup(model)
        return (usage.prompt_tokens * p.input_per_m + usage.completion_tokens * p.output_per_m
                + usage.cache_read_tokens * p.cache_read_per_m + usage.cache_write_tokens * p.cache_write_per_m) / PER_MILLION


@dataclass
class Entry:
    turn: int
    provider: str
    model: str
    usage: Usage
    latency_s: float
    cost_usd: float
    at: float = field(default_factory=time.time)


class Ledger:
    """跨場帳本（battles/ledger.jsonl）：每次呼叫一行，用來算「今天／本月」累計。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def add(self, battle_id: str, provider: str, model: str, cost_usd: float, usage: Usage, at: float | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {"at": at if at is not None else time.time(), "battle_id": battle_id, "provider": provider, "model": model,
               "cost_usd": round(cost_usd, 6), "prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def totals(self, now: float | None = None) -> dict[str, float]:
        now = now if now is not None else time.time()
        lt = time.localtime(now)
        day_start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        month_start = time.mktime((lt.tm_year, lt.tm_mon, 1, 0, 0, 0, 0, 0, -1))
        today = month = 0.0
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("at", 0) >= month_start:
                    month += row.get("cost_usd", 0.0)
                if row.get("at", 0) >= day_start:
                    today += row.get("cost_usd", 0.0)
        return {"today": round(today, 6), "month": round(month, 6)}


class UsageMeter:
    def __init__(self, prices: PriceTable | None = None, log_path: str | Path | None = None) -> None:
        self.prices = prices or PriceTable()
        self.log_path = Path(log_path) if log_path else None
        self.entries: list[Entry] = []

    def record(self, turn: int, provider: str, model: str, usage: Usage, latency_s: float) -> Entry:
        e = Entry(turn=turn, provider=provider, model=model, usage=usage, latency_s=round(latency_s, 3),
                  cost_usd=round(self.prices.cost(model, usage), 6))
        self.entries.append(e)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
        return e

    @property
    def prompt_tokens(self) -> int:
        return sum(e.usage.prompt_tokens for e in self.entries)

    @property
    def completion_tokens(self) -> int:
        return sum(e.usage.completion_tokens for e in self.entries)

    @property
    def cost_usd(self) -> float:
        return round(sum(e.cost_usd for e in self.entries), 6)

    @property
    def estimated(self) -> bool:
        return any(e.usage.estimated for e in self.entries)

    def summary(self) -> str:
        est = "（含粗估）" if self.estimated else ""
        return (f"本場 token：輸入 {self.prompt_tokens:,}／輸出 {self.completion_tokens:,}{est}，"
                f"費用約 ${self.cost_usd:.4f}（估算值，以供應商帳單為準）")
