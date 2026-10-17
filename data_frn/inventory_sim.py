"""One FreshRetailNet series under every policy variant of protocol frn-v1 §3 (no I/O).

Day ``i``: the order decided the evening before arrives in the morning and is sellable until ``i + L − 1``;
demand is served FIFO by expiry, unmet demand is lost, expired lots are discarded in the evening. The first
``WARMUP_DAYS`` days build stock and are not scored. Same lot mechanics as ``simulation.inventory``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

from decision.inventory import quantity_for_service
from decision.types import ForecastQuantiles, SkuEconomics, StockLot
from simulation.inventory import Lot, discard_expired, serve_fifo

SERVICE_TARGETS = (0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 0.98)
MULTIPLIERS = tuple(round(0.6 + 0.1 * i, 1) for i in range(11))  # 0,6 … 1,6
WARMUP_DAYS = 3


@dataclass(frozen=True)
class Variant:
    family: str  # "freshmesh" | "freshmesh_q28" (v1.1) | "freshmesh_p50" (v1.3) | "mean7" | "seasonal_naive"
    param: float  # service target (freshmesh) or multiplier of the baseline forecast
    net: bool = False  # baselines: order up to the target net of stock on hand

    @property
    def key(self) -> str:
        return f"{self.family}:{self.param:g}:{'net' if self.net else 'gross'}"


VARIANTS: tuple[Variant, ...] = (
    *(Variant("freshmesh", t) for t in SERVICE_TARGETS),
    *(Variant(f, m, net) for f in ("mean7", "seasonal_naive") for net in (False, True) for m in MULTIPLIERS),
)
# frn-v1.1: the same ordering rule fed with the empirical 28-day quantiles instead of the MLP.
V11_VARIANTS: tuple[Variant, ...] = tuple(Variant("freshmesh_q28", t) for t in SERVICE_TARGETS)
# frn-v1.3: the MLP median in the order-up-to rule (m × P50 net of stock), the baselines' multipliers.
V13_VARIANTS: tuple[Variant, ...] = tuple(Variant("freshmesh_p50", m, True) for m in MULTIPLIERS)
STATS = ("opening", "received", "wasted", "lost", "demand")


def simulate_series(
    demand: np.ndarray,
    quantiles: np.ndarray,
    point: dict[str, np.ndarray],
    shelf_life: int,
    start: dt.date,
    *,
    seed: int = 0,
    variants: tuple[Variant, ...] = VARIANTS,
    family_quantiles: dict[str, np.ndarray] | None = None,
) -> dict[str, dict[str, int]]:
    """``{variant.key: totals}`` for one series. ``demand`` (n,) units; ``quantiles`` (n, 3) the P10/P50/P90
    forecast of each day; ``point`` the baselines' P50 per day (``mean7``, ``seasonal_naive``);
    ``family_quantiles`` the P10/P50/P90 of other FreshMesh-rule families (``freshmesh_q28``)."""
    # Prices do not affect a service-target order (quantity_for_service); placeholders only.
    sku = SkuEconomics(
        "frn", "frn", unit_cost=1.0, unit_price=2.0, salvage_price=0.0, shelf_life_days=shelf_life
    )
    by_family = {"freshmesh": quantiles, **(family_quantiles or {})}
    q_sorted = {f: np.sort(np.maximum(q, 0.0), axis=1) for f, q in by_family.items()}
    out: dict[str, dict[str, int]] = {}
    for v in variants:
        lots: list[Lot] = []
        tot = dict.fromkeys(STATS, 0)
        for i, dem in enumerate(int(x) for x in demand):
            on_hand = sum(lot.qty for lot in lots)
            if i == WARMUP_DAYS:
                tot["opening"] = on_hand
            if v.family in q_sorted:
                day = start + dt.timedelta(days=i)
                stock = [
                    StockLot("S", "frn", lot.qty, start + dt.timedelta(days=lot.expires)) for lot in lots
                ]
                row = ForecastQuantiles("S", "frn", day, *(float(x) for x in q_sorted[v.family][i]))
                qty, _ = quantity_for_service("S", sku, [row], stock, v.param, seed=seed + i)
            else:
                qty = max(0, round(v.param * float(point[v.family][i]) - (on_hand if v.net else 0)))
            if qty:
                lots.append(Lot(i + shelf_life - 1, i, int(qty)))
            _, lost = serve_fifo(lots, dem)
            wasted = discard_expired(lots, i)
            if i >= WARMUP_DAYS:
                tot["received"] += int(qty)
                tot["wasted"] += wasted
                tot["lost"] += lost
                tot["demand"] += dem
        out[v.key] = tot
    return out
