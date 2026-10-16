"""plan_inventory: Monte Carlo order sizing with FIFO expiry (spec §5.1)."""

from __future__ import annotations

import datetime
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from decision.distribution import QuantileDistribution, sample_demand
from decision.text import pct, vnd
from decision.types import (
    FRESH_MAX_SHELF_DAYS,
    Constraints,
    ForecastQuantiles,
    InventoryPlan,
    PlanLine,
    SkuEconomics,
    StockLot,
)

MAX_GRID_POINTS = 200
COVER_QUANTILE = 0.995  # largest order considered = this quantile of horizon demand

PLAN_SPECS: tuple[tuple[str, str, float | None], ...] = (
    ("safe", "An toàn", 0.85),
    ("balanced", "Cân bằng", None),
    ("lean", "Tiết kiệm", 0.50),
)
# Service targets of the trade-off frontier the owner slides along (same grid as the FRN protocol §3).
FRONTIER_TARGETS: tuple[float, ...] = (0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 0.98)

ASSUMPTIONS_VI = [
    "Phân bố nhu cầu dựng từ P10/P50/P90 bằng hàm phân vị tuyến tính từng đoạn với đuôi mũ; "
    "nhu cầu các ngày được coi là độc lập.",
    "Hàng bán theo FIFO theo hạn dùng; phần chưa bán bị bỏ vào cuối ngày hết hạn.",
    "Chi phí hàng bỏ = giá vốn − giá thanh lý; chi phí hết hàng = biên lợi nhuận + phạt mất khách.",
    "Hàng mới về đầu ngày đầu tiên của kỳ; số lượng làm tròn theo bội số MOQ của nhà cung cấp.",
    "Mức nhập lớn nhất được xét là phân vị rất cao của tổng nhu cầu trong kỳ.",
]


def inventory_assumptions_vi(constraints: Constraints) -> list[str]:
    """ASSUMPTIONS_VI plus the overnight carry cost actually used by ``constraints``."""
    holding = pct(100 * constraints.holding_cost_rate_per_day)
    fresh = constraints.fresh_carry_cost_rate_per_day
    if fresh is None:
        carry = f"Hàng còn hạn tồn qua đêm chịu chi phí lưu kho {holding} giá vốn mỗi ngày."
    else:
        carry = (
            f"Hàng tươi (hạn dùng ≤ {FRESH_MAX_SHELF_DAYS} ngày) còn tồn qua đêm chịu chi phí "
            f"{pct(100 * fresh)} giá vốn mỗi ngày, đại diện cho rủi ro phải bỏ (giá trị chọn trên mô phỏng "
            f"30 ngày, docs/experiments/sim30-results.md); hàng khác chịu chi phí lưu kho {holding} giá vốn "
            "mỗi ngày."
        )
    return [*ASSUMPTIONS_VI[:4], carry, *ASSUMPTIONS_VI[4:]]


@dataclass(frozen=True)
class SkuCurve:
    """Simulated outcome for each candidate order quantity of one SKU (arrays indexed by candidate)."""

    sku: SkuEconomics
    store_id: str
    qty: np.ndarray
    expected_cost: np.ndarray
    service_level: np.ndarray
    waste_units: np.ndarray
    shortage_units: np.ndarray
    available_units: np.ndarray
    demand_units: float
    stock_cold_units: float
    carried_units: np.ndarray  # unexpired units left after the horizon


def critical_ratio(sku: SkuEconomics, stockout_penalty_vnd: float) -> float:
    under = sku.unit_price - sku.unit_cost + stockout_penalty_vnd
    over = sku.unit_cost - sku.salvage_price
    return under / (under + over)


def _candidate_quantities(demand: np.ndarray, moq: int) -> np.ndarray:
    cap = math.ceil(float(np.quantile(demand.sum(axis=1), COVER_QUANTILE)))
    packs = math.ceil(cap / moq) + 1
    step = max(1, math.ceil(packs / MAX_GRID_POINTS))
    return np.arange(0, packs + step, step, dtype=np.int64) * moq


def simulate_fifo(
    qty: np.ndarray,
    new_lot_expiry: int,
    lots: Sequence[tuple[int, int]],
    demand: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Simulate FIFO selling for every candidate quantity and every demand path.

    qty: (C,) candidate order sizes arriving at the start of day 0.
    new_lot_expiry: index of the last sellable day of the new lot.
    lots: existing (last sellable day index, units) pairs.
    demand: (N, H) integer demand per path and day.
    Returns (waste, shortage, carried_unit_days, available), each (C, N): units discarded at the end of
    their expiry day, units short, sum over days of unexpired units left at day end, units on hand at start.
    """
    n_paths, horizon = demand.shape
    shape = (qty.size, n_paths)
    # Oldest expiry first; existing stock before the new lot on equal expiry (it was received earlier).
    ordered = sorted([(exp, 0, float(q)) for exp, q in lots] + [(new_lot_expiry, 1, -1.0)])
    stock = [
        (exp, np.broadcast_to(qty[:, None], shape).astype(float) if q < 0 else np.full(shape, q))
        for exp, _, q in ordered
    ]
    available = sum((s for _, s in stock), np.zeros(shape))
    waste = np.zeros(shape)
    shortage = np.zeros(shape)
    carried = np.zeros(shape)
    for day in range(horizon):
        remaining = np.broadcast_to(demand[:, day][None, :].astype(float), shape).copy()
        for exp, lot in stock:
            if exp < day:
                continue
            sold = np.minimum(lot, remaining)
            lot -= sold
            remaining -= sold
        shortage += remaining
        for exp, lot in stock:
            if exp == day:
                waste += lot
                lot[:] = 0.0
            elif exp > day:
                carried += lot
    return waste, shortage, carried, available


def _sku_curve(
    store_id: str,
    sku: SkuEconomics,
    rows: Sequence[ForecastQuantiles],
    lots: Sequence[StockLot],
    day0: datetime.date,
    constraints: Constraints,
    n_sims: int,
    rng: np.random.Generator,
) -> SkuCurve:
    demand = np.stack(
        [sample_demand(QuantileDistribution(r.p10, r.p50, r.p90), rng, n_sims) for r in rows], axis=1
    )
    qty = _candidate_quantities(demand, sku.moq)
    lot_pairs = [((lot.expires_on - day0).days, lot.qty) for lot in lots]
    waste, shortage, carried, available = simulate_fifo(qty, sku.shelf_life_days - 1, lot_pairs, demand)
    under = sku.unit_price - sku.unit_cost + constraints.stockout_penalty_vnd
    over = sku.unit_cost - sku.salvage_price
    fresh_rate = constraints.fresh_carry_cost_rate_per_day
    is_fresh = fresh_rate is not None and sku.shelf_life_days <= FRESH_MAX_SHELF_DAYS
    holding = (fresh_rate if is_fresh else constraints.holding_cost_rate_per_day) * sku.unit_cost
    cost = over * waste + under * shortage + holding * carried
    stock_units = sum(lot.qty for lot in lots)
    return SkuCurve(
        sku=sku,
        store_id=store_id,
        qty=qty,
        expected_cost=cost.mean(axis=1),
        service_level=(shortage == 0).mean(axis=1),
        waste_units=waste.mean(axis=1),
        shortage_units=shortage.mean(axis=1),
        available_units=available.mean(axis=1),
        demand_units=float(demand.sum(axis=1).mean()),
        stock_cold_units=stock_units * sku.cold_storage_units,
        carried_units=carried.mean(axis=1),
    )


def _service_index(curve: SkuCurve, target: float) -> tuple[int, bool]:
    """Smallest candidate reaching `target`; if unreachable, smallest one reaching the best level."""
    hits = np.nonzero(curve.service_level >= target - 1e-12)[0]
    if hits.size:
        return int(hits[0]), True
    return int(np.argmax(curve.service_level)), False


def quantity_for_service(
    store_id: str,
    sku: SkuEconomics,
    rows: Sequence[ForecastQuantiles],
    lots: Sequence[StockLot],
    target: float,
    *,
    n_sims: int = 2000,
    seed: int = 0,
) -> tuple[int, float]:
    """(order quantity, achieved service) of the smallest order reaching P(no stockout) ≥ ``target`` over the
    rows' horizon, picked from the same Monte Carlo curve as the "An toàn" / "Tiết kiệm" plans. Prices and
    cost rates do not affect this choice, so it also serves data without prices (FreshRetailNet)."""
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    day0 = min(r.date for r in rows)
    curve = _sku_curve(store_id, sku, rows, lots, day0, Constraints(), n_sims, rng)
    i, _ = _service_index(curve, target)
    return int(curve.qty[i]), float(curve.service_level[i])


def _apply_constraints(
    idx: dict[str, int], curves: Mapping[str, SkuCurve], constraints: Constraints
) -> tuple[dict[str, int], list[str], list[str]]:
    """Remove order steps with the lowest marginal value per unit of the binding resource until feasible."""
    idx = dict(idx)
    bound: list[str] = []
    reduced: list[str] = []
    cold_free = None
    if constraints.cold_storage_capacity is not None:
        cold_free = constraints.cold_storage_capacity - sum(c.stock_cold_units for c in curves.values())

    def spend() -> float:
        return sum(float(curves[s].qty[i]) * curves[s].sku.unit_cost for s, i in idx.items())

    def cold() -> float:
        return sum(float(curves[s].qty[i]) * curves[s].sku.cold_storage_units for s, i in idx.items())

    while True:
        if constraints.budget_vnd is not None and spend() > constraints.budget_vnd + 1e-9:
            resource, per_unit = "budget", (lambda c: c.sku.unit_cost)
        elif cold_free is not None and cold() > cold_free + 1e-9:
            resource, per_unit = "cold", (lambda c: c.sku.cold_storage_units)
        else:
            break
        if resource not in bound:
            bound.append(resource)
        best: tuple[float, str] | None = None
        for sku_id, i in sorted(idx.items()):
            curve = curves[sku_id]
            freed = (float(curve.qty[i]) - float(curve.qty[i - 1])) * per_unit(curve) if i > 0 else 0.0
            if freed <= 0:
                continue
            score = (curve.expected_cost[i - 1] - curve.expected_cost[i]) / freed
            if best is None or score < best[0]:
                best = (score, sku_id)
        if best is None:
            break
        idx[best[1]] -= 1
        if best[1] not in reduced:
            reduced.append(best[1])
    return idx, bound, reduced


def _build_plan(
    name: str,
    label: str,
    target: float | None,
    idx: Mapping[str, int],
    curves: Mapping[str, SkuCurve],
    bound: Sequence[str],
    reduced: Sequence[str],
    unreachable: Sequence[str],
    assumptions_vi: Sequence[str],
) -> InventoryPlan:
    lines: list[PlanLine] = []
    waste = shortage = available = demand = loss = weighted_service = leftover = 0.0
    for sku_id in sorted(idx):
        c, i = curves[sku_id], idx[sku_id]
        q = int(c.qty[i])
        lines.append(
            PlanLine(
                store_id=c.store_id,
                sku_id=sku_id,
                qty=q,
                cost_vnd=round(q * c.sku.unit_cost),
                service_level_pct=round(100 * float(c.service_level[i]), 1),
                expected_waste_units=round(float(c.waste_units[i]), 1),
                expected_shortage_units=round(float(c.shortage_units[i]), 1),
            )
        )
        waste += float(c.waste_units[i])
        shortage += float(c.shortage_units[i])
        available += float(c.available_units[i])
        demand += c.demand_units
        loss += float(c.expected_cost[i])
        leftover += float(c.carried_units[i])
        weighted_service += c.demand_units * float(c.service_level[i])
    total = sum(line.cost_vnd for line in lines)
    waste_pct = round(100 * waste / available, 1) if available > 0 else 0.0
    stockout_pct = round(100 * shortage / demand, 1) if demand > 0 else 0.0
    service_pct = round(100 * weighted_service / demand, 1) if demand > 0 else 100.0
    target_pct = None if target is None else round(100 * target, 1)

    why = {
        "safe": f"nhắm mức phục vụ khoảng {pct(target_pct or 0)} để hạn chế hết hàng",
        "balanced": "chọn số lượng có chi phí kỳ vọng (hàng bỏ + hết hàng) thấp nhất, tức tỷ lệ tới hạn",
        "lean": f"nhắm mức trung vị (mức phục vụ {pct(target_pct or 0)}) để giảm vốn và hàng bỏ",
    }.get(name, f"nhắm mức phục vụ {pct(target_pct or 0)} do bạn chọn trên đường đánh đổi")
    n_items = sum(1 for line in lines if line.qty > 0)
    text = (
        f"Phương án {label}: {why}; nhập {n_items} mặt hàng, tổng {vnd(total)}, "
        f"dự kiến bỏ {pct(waste_pct)}, hết hàng {pct(stockout_pct)}, "
        f"xác suất không hết hàng {pct(service_pct)}."
    )
    if unreachable:
        text += (
            f" Mức phục vụ mục tiêu không đạt được với một lần nhập cho "
            f"{', '.join(curves[s].sku.name for s in unreachable)} (hạn dùng ngắn hơn kỳ kế hoạch)."
        )
    if bound:
        names = {"budget": "ngân sách", "cold": "sức chứa kho lạnh"}
        sku_names = ", ".join(curves[s].sku.name for s in reduced)
        text += (
            f" Ràng buộc {' và '.join(names[b] for b in bound)} bị chạm nên đã giảm "
            f"{sku_names} (mặt hàng có giá trị biên thấp nhất trên mỗi đơn vị tài nguyên)."
        )
    return InventoryPlan(
        name=name,
        label_vi=label,
        lines=lines,
        total_cost_vnd=total,
        items_ordered=n_items,
        expected_loss_vnd=round(loss),
        expected_waste_pct=waste_pct,
        expected_stockout_pct=stockout_pct,
        service_level_pct=service_pct,
        target_service_pct=target_pct,
        constrained=bool(bound),
        rationale_vi=text,
        assumptions_vi=list(assumptions_vi),
        expected_leftover_units=round(leftover, 1),
    )


def plan_inventory(
    forecasts: Sequence[ForecastQuantiles],
    stock: Sequence[StockLot],
    skus: Mapping[str, SkuEconomics],
    constraints: Constraints,
    *,
    horizon_days: int = 1,
    n_sims: int = 2000,
    seed: int = 0,
) -> list[InventoryPlan]:
    """Return the three plans "An toàn", "Cân bằng", "Tiết kiệm" for one store.

    The order arrives at the start of the first forecast day and covers `horizon_days` days.
    Per SKU: safe ≥ balanced ≥ lean in quantity, before and after constraints.
    """
    return plan_inventory_with_frontier(
        forecasts, stock, skus, constraints, horizon_days=horizon_days, n_sims=n_sims, seed=seed, targets=()
    )[0]


def plan_inventory_with_frontier(
    forecasts: Sequence[ForecastQuantiles],
    stock: Sequence[StockLot],
    skus: Mapping[str, SkuEconomics],
    constraints: Constraints,
    *,
    horizon_days: int = 1,
    n_sims: int = 2000,
    seed: int = 0,
    targets: Sequence[float] = FRONTIER_TARGETS,
) -> tuple[list[InventoryPlan], list[InventoryPlan]]:
    """(the three plans, one plan per service target): the frontier the owner slides along. Both come from
    the same Monte Carlo curves, so a target plan and a named plan at the same service level agree."""
    curves = _store_curves(forecasts, stock, skus, constraints, horizon_days, n_sims, seed)
    assumptions_vi = inventory_assumptions_vi(constraints)
    plans = _three_plans(curves, constraints, assumptions_vi)
    return plans, [_target_plan(t, curves, constraints, assumptions_vi) for t in targets]


def _target_plan(
    target: float, curves: Mapping[str, SkuCurve], constraints: Constraints, assumptions_vi: Sequence[str]
) -> InventoryPlan:
    raw, unreachable = {}, []
    for sku_id, curve in curves.items():
        raw[sku_id], reached = _service_index(curve, target)
        if not reached:
            unreachable.append(sku_id)
    idx, bound, reduced = _apply_constraints(raw, curves, constraints)
    level = round(100 * target)
    name, label = f"target_{level}", f"Mức phục vụ {level}%"
    return _build_plan(name, label, target, idx, curves, bound, reduced, unreachable, assumptions_vi)


def _store_curves(
    forecasts: Sequence[ForecastQuantiles],
    stock: Sequence[StockLot],
    skus: Mapping[str, SkuEconomics],
    constraints: Constraints,
    horizon_days: int,
    n_sims: int,
    seed: int,
) -> dict[str, SkuCurve]:
    if horizon_days < 1:
        raise ValueError("horizon_days must be >= 1")
    if not forecasts:
        raise ValueError("forecasts must not be empty")
    store_ids = {f.store_id for f in forecasts}
    if len(store_ids) != 1:
        raise ValueError(f"plan_inventory plans one store at a time, got {sorted(store_ids)}")
    store_id = next(iter(store_ids))

    by_sku: dict[str, list[ForecastQuantiles]] = defaultdict(list)
    for f in forecasts:
        by_sku[f.sku_id].append(f)
    day0 = min(f.date for f in forecasts)
    sku_ids = sorted(by_sku)
    seeds = np.random.SeedSequence(seed).spawn(len(sku_ids))

    curves: dict[str, SkuCurve] = {}
    for sku_id, ss in zip(sku_ids, seeds, strict=True):
        if sku_id not in skus:
            raise ValueError(f"missing economics for SKU {sku_id}")
        sku = skus[sku_id]
        if sku.moq < 1 or sku.shelf_life_days < 1:
            raise ValueError(f"SKU {sku_id}: moq and shelf_life_days must be >= 1")
        rows = sorted(by_sku[sku_id], key=lambda r: r.date)[:horizon_days]
        expected_days = [day0 + datetime.timedelta(days=k) for k in range(horizon_days)]
        if [r.date for r in rows] != expected_days:
            raise ValueError(f"SKU {sku_id}: need one forecast per day for {horizon_days} consecutive days")
        lots = [
            lot
            for lot in stock
            if lot.store_id == store_id and lot.sku_id == sku_id and lot.expires_on >= day0 and lot.qty > 0
        ]
        rng = np.random.default_rng(ss)
        curves[sku_id] = _sku_curve(store_id, sku, rows, lots, day0, constraints, n_sims, rng)
    return curves


def _three_plans(
    curves: Mapping[str, SkuCurve], constraints: Constraints, assumptions_vi: Sequence[str]
) -> list[InventoryPlan]:
    raw: dict[str, dict[str, int]] = {}
    unreachable: dict[str, list[str]] = {}
    for name, _, target in PLAN_SPECS:
        unreachable[name] = []
        if target is None:
            raw[name] = {s: int(np.argmin(c.expected_cost)) for s, c in curves.items()}
            continue
        raw[name] = {}
        for s, c in curves.items():
            raw[name][s], reached = _service_index(c, target)
            if not reached:
                unreachable[name].append(s)
    raw["safe"] = {s: max(raw["safe"][s], raw["balanced"][s]) for s in curves}
    raw["lean"] = {s: min(raw["lean"][s], raw["balanced"][s]) for s in curves}

    final: dict[str, tuple[dict[str, int], list[str], list[str]]] = {
        name: _apply_constraints(raw[name], curves, constraints) for name, _, _ in PLAN_SPECS
    }
    # Keep safe >= balanced >= lean per SKU after scaling (lowering a quantity never breaks a constraint).
    safe_idx = final["safe"][0]
    bal_idx = {s: min(i, safe_idx[s]) for s, i in final["balanced"][0].items()}
    lean_idx = {s: min(i, bal_idx[s]) for s, i in final["lean"][0].items()}
    adjusted = {"safe": safe_idx, "balanced": bal_idx, "lean": lean_idx}
    return [
        _build_plan(
            name,
            label,
            target,
            adjusted[name],
            curves,
            final[name][1],
            final[name][2],
            unreachable[name],
            assumptions_vi,
        )
        for name, label, target in PLAN_SPECS
    ]
