"""Daily FIFO inventory simulation of fresh SKUs under an ordering policy (pure, no I/O).

Day index 0 is the evening of ``SIM_AS_OF``; days ``1..n`` are simulated. For day ``d``:

1. morning — the order decided on the evening of ``d − 1`` arrives; its last sellable day is ``d + L − 1``;
2. demand is served FIFO by expiry (equal expiry: lot received earlier first); unmet demand is lost;
3. evening — lots whose last sellable day is ``d`` are discarded (waste); the policy observes the day's
   *sales* (censored by stock) and decides the next order.

Conservation per store × SKU: ``opening + received = sold + wasted + closing``.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

Key = tuple[str, str]  # (store_id, sku_id)


@dataclass
class Lot:
    expires: int  # last sellable day index
    received: int  # day index of receipt (<= 0 for opening stock)
    qty: int


@dataclass(frozen=True)
class SkuSpec:
    """What the simulator needs to know about a SKU (real prices; no penalty folded in)."""

    sku_id: str
    shelf_life_days: int
    moq: int
    unit_cost: float
    unit_price: float
    salvage_price: float


def serve_fifo(lots: list[Lot], demand: int) -> tuple[int, int]:
    """Sell ``demand`` units from ``lots`` (oldest expiry first). Mutates lots; returns (sold, lost)."""
    remaining = int(demand)
    for lot in sorted(lots, key=lambda x: (x.expires, x.received)):
        if remaining <= 0:
            break
        take = min(lot.qty, remaining)
        lot.qty -= take
        remaining -= take
    lots[:] = [lot for lot in lots if lot.qty > 0]
    return int(demand) - remaining, remaining


def discard_expired(lots: list[Lot], day: int) -> int:
    """Remove lots whose last sellable day is ``<= day``; return the discarded units."""
    wasted = sum(lot.qty for lot in lots if lot.expires <= day)
    lots[:] = [lot for lot in lots if lot.expires > day]
    return wasted


def round_to_moq(x: float, moq: int) -> int:
    """Nearest multiple of ``moq`` (half up), never negative."""
    if x <= 0:
        return 0
    return int(moq * math.floor(x / moq + 0.5))


@dataclass(frozen=True)
class DayContext:
    day: int  # decision evening index; the order arrives on day + 1
    date: dt.date  # calendar date of ``day``
    lots: Mapping[Key, Sequence[Lot]]  # stock after the evening discard (all lots expire > day)


class Policy(Protocol):
    name: str

    def order(self, ctx: DayContext) -> dict[Key, int]: ...

    def observe(self, day: int, date: dt.date, sales: Mapping[Key, int], extra: DayExtra) -> None: ...


@dataclass(frozen=True)
class DayExtra:
    """Realised day data that a POS would record next to the sales (used to append history)."""

    price: Mapping[Key, float]
    promo: Mapping[Key, int]
    rain_mm: float


class MeanSalesBaseline:
    """Order = mean of the last 7 recorded sales days, rounded to MOQ.

    ``net=True`` (exploratory variant) subtracts the units on hand."""

    def __init__(
        self, skus: Mapping[str, SkuSpec], history: Mapping[Key, Sequence[int]], *, net: bool = False
    ):
        self.name = "baseline_mean7_net" if net else "baseline_mean7"
        self.skus = skus
        self.net = net
        self.history: dict[Key, list[int]] = {k: list(v)[-7:] for k, v in history.items()}

    def mean7(self, key: Key) -> float:
        h = self.history.get(key, [])[-7:]
        return float(np.mean(h)) if h else 0.0

    def order(self, ctx: DayContext) -> dict[Key, int]:
        out: dict[Key, int] = {}
        for key in self.history:
            target = self.mean7(key)
            if self.net:
                target -= sum(lot.qty for lot in ctx.lots.get(key, ()))
            out[key] = round_to_moq(target, self.skus[key[1]].moq)
        return out

    def observe(self, day: int, date: dt.date, sales: Mapping[Key, int], extra: DayExtra) -> None:
        for key, units in sales.items():
            self.history.setdefault(key, []).append(int(units))
            self.history[key] = self.history[key][-7:]


@dataclass
class Ledger:
    """Totals per store × SKU (units and VND)."""

    opening: dict[Key, int] = field(default_factory=dict)
    received: dict[Key, int] = field(default_factory=dict)
    sold: dict[Key, int] = field(default_factory=dict)
    wasted: dict[Key, int] = field(default_factory=dict)
    lost: dict[Key, int] = field(default_factory=dict)
    demand: dict[Key, int] = field(default_factory=dict)
    closing: dict[Key, int] = field(default_factory=dict)
    lost_promo: dict[Key, int] = field(default_factory=dict)
    demand_promo: dict[Key, int] = field(default_factory=dict)
    revenue: dict[Key, float] = field(default_factory=dict)

    def add(self, name: str, key: Key, value: float) -> None:
        bucket = getattr(self, name)
        bucket[key] = bucket.get(key, 0) + value


def simulate_policy(
    policy: Policy,
    skus: Mapping[str, SkuSpec],
    opening: Mapping[Key, Sequence[Lot]],
    demand: Mapping[Key, Sequence[int]],
    price: Mapping[Key, Sequence[float]],
    promo: Mapping[Key, Sequence[int]],
    rain: Sequence[float],
    dates: Sequence[dt.date],
) -> Ledger:
    """Run ``len(dates)`` days. ``demand[key][i]`` is the demand of ``dates[i]`` (day index ``i + 1``);
    ``dates`` must be consecutive, starting the day after the decision evening 0."""
    n = len(dates)
    keys = sorted(demand)
    lots: dict[Key, list[Lot]] = {
        k: [Lot(x.expires, x.received, x.qty) for x in opening.get(k, ())] for k in keys
    }
    ledger = Ledger()
    for k in keys:
        ledger.opening[k] = sum(x.qty for x in lots[k])
    day0 = dates[0] - dt.timedelta(days=1)
    for i in range(n):
        d = i + 1
        orders = policy.order(DayContext(d - 1, day0 + dt.timedelta(days=d - 1), lots))
        for k in keys:
            q = int(orders.get(k, 0))
            if q < 0:
                raise ValueError(f"{policy.name}: negative order for {k}")
            if q:
                lots[k].append(Lot(d + skus[k[1]].shelf_life_days - 1, d, q))
            ledger.add("received", k, q)
        sales: dict[Key, int] = {}
        for k in keys:
            dem = int(demand[k][i])
            sold, lost = serve_fifo(lots[k], dem)
            sales[k] = sold
            ledger.add("sold", k, sold)
            ledger.add("lost", k, lost)
            ledger.add("demand", k, dem)
            ledger.add("revenue", k, sold * float(price[k][i]))
            if promo[k][i]:
                ledger.add("lost_promo", k, lost)
                ledger.add("demand_promo", k, dem)
            ledger.add("wasted", k, discard_expired(lots[k], d))
        extra = DayExtra(
            price={k: float(price[k][i]) for k in keys},
            promo={k: int(promo[k][i]) for k in keys},
            rain_mm=float(rain[i]),
        )
        policy.observe(d, dates[i], sales, extra)
    for k in keys:
        ledger.closing[k] = sum(x.qty for x in lots[k])
    return ledger


def ledger_metrics(
    ledger: Ledger, skus: Mapping[str, SkuSpec], stockout_penalty_ratio: float
) -> dict[str, float]:
    """Pooled (ratio of sums) metrics over every store × SKU of the ledger."""

    def tot(name: str) -> float:
        return float(sum(getattr(ledger, name).values()))

    opening, received, wasted = tot("opening"), tot("received"), tot("wasted")
    lost, dem = tot("lost"), tot("demand")
    purchase = sum(q * skus[k[1]].unit_cost for k, q in ledger.received.items())
    salvage = sum(q * skus[k[1]].salvage_price for k, q in ledger.wasted.items())
    stock_change = sum((ledger.closing[k] - ledger.opening[k]) * skus[k[1]].unit_cost for k in ledger.opening)
    revenue = tot("revenue")
    waste_cost = sum(q * (skus[k[1]].unit_cost - skus[k[1]].salvage_price) for k, q in ledger.wasted.items())
    short_cost = sum(
        q * (skus[k[1]].unit_price - skus[k[1]].unit_cost) * (1.0 + stockout_penalty_ratio)
        for k, q in ledger.lost.items()
    )
    return {
        "opening_units": opening,
        "received_units": received,
        "sold_units": tot("sold"),
        "wasted_units": wasted,
        "lost_units": lost,
        "demand_units": dem,
        "closing_units": tot("closing"),
        "lost_promo_units": tot("lost_promo"),
        "demand_promo_units": tot("demand_promo"),
        "waste_pct": 100.0 * wasted / (opening + received) if opening + received > 0 else 0.0,
        "waste_pct_of_received": 100.0 * wasted / received if received > 0 else 0.0,
        "stockout_pct": 100.0 * lost / dem if dem > 0 else 0.0,
        "revenue_vnd": revenue,
        "salvage_vnd": salvage,
        "purchase_vnd": purchase,
        "net_profit_vnd": revenue + salvage - purchase + stock_change,
        "cost_proxy_vnd": waste_cost + short_cost,
    }
