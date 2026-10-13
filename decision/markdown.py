"""suggest_markdown: time-slot discount schedule for fresh stock expiring today (spec §5.2)."""

from __future__ import annotations

import datetime
import math
from collections.abc import Mapping, Sequence

import numpy as np

from decision.text import units, vnd
from decision.types import MarkdownPlan, MarkdownSlot, SkuEconomics, StockLot

DISCOUNT_LEVELS: tuple[int, ...] = (0, 10, 20, 30, 50)
MAX_SLOTS = 24
SLOT = datetime.timedelta(hours=1)


def demand_multiplier(discount_pct: float, elasticity: float) -> float:
    """Constant-elasticity response: demand × (1 − d)^(−|ε|). The sign of ε is ignored (magnitude used)."""
    return (1.0 - discount_pct / 100.0) ** (-abs(elasticity))


def _poisson_pmf(mean: float, cap: int) -> np.ndarray:
    """P(D = k) for k < kmax and P(D >= kmax) at index kmax, kmax = min(cap, mean + 10·sqrt(mean) + 10)."""
    kmax = int(min(cap, math.ceil(mean + 10.0 * math.sqrt(mean) + 10.0)))
    if mean <= 0:
        pmf = np.zeros(kmax + 1)
        pmf[0] = 1.0
        return pmf
    k = np.arange(kmax)
    log_fact = np.concatenate([[0.0], np.cumsum(np.log(np.arange(1, max(kmax, 1))))])[:kmax]
    pmf = np.exp(k * math.log(mean) - mean - log_fact)
    return np.append(pmf, max(0.0, 1.0 - pmf.sum()))


def _sell(stock_dist: np.ndarray, demand_pmf: np.ndarray) -> tuple[np.ndarray, float]:
    """Distribution of stock after one slot of Poisson demand and the expected units sold."""
    kmax = demand_pmf.size - 1
    full = np.convolve(stock_dist, demand_pmf[::-1])
    after = full[kmax + 1 : kmax + stock_dist.size].copy()
    after = np.concatenate([[max(0.0, 1.0 - after.sum())], after])
    levels = np.arange(stock_dist.size)
    return after, float(stock_dist @ levels - after @ levels)


def suggest_markdown(
    stock: Sequence[StockLot],
    hourly_forecast: Mapping[datetime.datetime, float],
    sku: SkuEconomics,
    elasticity: float,
    *,
    now: datetime.datetime,
    discounts: Sequence[int] = DISCOUNT_LEVELS,
) -> MarkdownPlan:
    """Choose a non-decreasing discount per hourly slot until closing.

    hourly_forecast maps each slot start (hourly, up to closing) to the expected full-price units sold.
    Units at risk are the lots of `sku` that expire between today and the last slot's date. Hourly
    demand is Poisson with mean forecast × demand_multiplier(discount). The schedule maximises
    expected recovered revenue − (unit_cost − salvage_price) × expected wasted units; all
    non-decreasing schedules (prices only go down during the day) are enumerated exactly.
    """
    slots = sorted(t for t in hourly_forecast if t + SLOT > now)
    if not slots:
        raise ValueError("hourly_forecast has no slot at or after `now`")
    if len(slots) > MAX_SLOTS:
        raise ValueError(f"at most {MAX_SLOTS} hourly slots are supported")
    levels = sorted(set(discounts))
    if levels[0] != 0 or levels[-1] >= 100:
        raise ValueError("discounts must include 0 and stay below 100")

    lots = [
        lot
        for lot in stock
        if lot.sku_id == sku.sku_id and now.date() <= lot.expires_on <= slots[-1].date() and lot.qty > 0
    ]
    store_ids = {lot.store_id for lot in lots}
    if len(store_ids) > 1:
        raise ValueError(f"suggest_markdown handles one store at a time, got {sorted(store_ids)}")
    store_id = next(iter(store_ids)) if store_ids else ""
    at_risk = sum(lot.qty for lot in lots)
    waste_unit_cost = sku.unit_cost - sku.salvage_price
    base = [max(0.0, float(hourly_forecast[t])) for t in slots]

    pmfs = [
        [_poisson_pmf(b * demand_multiplier(d, elasticity), at_risk) for d in levels] for b in base
    ]
    start = np.zeros(at_risk + 1)
    start[at_risk] = 1.0

    best: dict[str, object] = {"value": -math.inf}

    def evaluate(choice: list[int]) -> tuple[float, float, list[float], float]:
        dist, revenue, sold = start, 0.0, []
        for t, li in enumerate(choice):
            dist, s = _sell(dist, pmfs[t][li])
            sold.append(s)
            revenue += s * sku.unit_price * (1 - levels[li] / 100.0)
        wasted = float(dist @ np.arange(dist.size))
        return revenue - waste_unit_cost * wasted, revenue, sold, wasted

    def search(t: int, min_level: int, dist: np.ndarray, revenue: float, prefix: list[int]) -> None:
        if t == len(slots):
            wasted = float(dist @ np.arange(dist.size))
            value = revenue - waste_unit_cost * wasted
            if value > best["value"] + 1e-6:
                best.update(value=value, choice=list(prefix))
            return
        for li in range(min_level, len(levels)):
            nxt, s = _sell(dist, pmfs[t][li])
            prefix.append(li)
            search(t + 1, li, nxt, revenue + s * sku.unit_price * (1 - levels[li] / 100.0), prefix)
            prefix.pop()

    search(0, 0, start, 0.0, [])
    choice: list[int] = best["choice"]  # type: ignore[assignment]
    _, revenue, sold, wasted = evaluate(choice)
    base_value, base_revenue, _, base_wasted = evaluate([0] * len(slots))

    schedule = [
        MarkdownSlot(
            start=t,
            discount_pct=levels[li],
            price_vnd=round(sku.unit_price * (1 - levels[li] / 100.0)),
            expected_units_sold=round(s, 1),
        )
        for t, li, s in zip(slots, choice, sold, strict=True)
    ]
    total_sold = round(sum(sold), 1)
    wasted_r = round(wasted, 1)
    revenue_r = round(revenue)
    waste_cost = round(waste_unit_cost * wasted)
    net = revenue_r - waste_cost
    base_net = round(base_value)
    gain = net - base_net

    steps = []
    for slot in schedule:
        if not steps or steps[-1][1] != slot.discount_pct:
            steps.append((slot.start, slot.discount_pct))
    if all(d == 0 for _, d in steps):
        plan_text = "Không cần giảm giá"
    else:
        plan_text = "Giảm giá " + ", ".join(f"{d}% từ {t:%H:%M}" for t, d in steps)
    rationale = (
        f"{plan_text} cho {at_risk} đơn vị {sku.name} sắp hết hạn: dự kiến bán {units(total_sold)}, "
        f"bỏ {units(wasted_r)} (không giảm giá: bỏ {units(round(base_wasted, 1))}), "
        f"thu về {vnd(revenue_r)}, lợi hơn không giảm giá {vnd(gain)}."
    )
    return MarkdownPlan(
        store_id=store_id,
        sku_id=sku.sku_id,
        units_at_risk=at_risk,
        schedule=schedule,
        expected_units_sold=total_sold,
        expected_units_wasted=wasted_r,
        recovered_revenue_vnd=revenue_r,
        waste_cost_vnd=waste_cost,
        net_value_vnd=net,
        baseline_units_wasted=round(base_wasted, 1),
        baseline_revenue_vnd=round(base_revenue),
        baseline_net_value_vnd=base_net,
        gain_vs_no_discount_vnd=gain,
        cash_gain_vnd=round(revenue - base_revenue - sku.salvage_price * (base_wasted - wasted)),
        elasticity=elasticity,
        rationale_vi=rationale,
    )
