"""Data types of the decision module. All money is in VND, all quantities in units."""

from __future__ import annotations

import dataclasses
import datetime
import enum
from dataclasses import dataclass, field
from typing import Any


def jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


class _Serializable:
    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(frozen=True)
class ForecastQuantiles(_Serializable):
    """Same fields as forecasting.service.ForecastRow (without confidence/reason)."""

    store_id: str
    sku_id: str
    date: datetime.date
    p10: float
    p50: float
    p90: float


@dataclass(frozen=True)
class StockLot(_Serializable):
    """Stock on hand. `expires_on` is the last day the units may be sold."""

    store_id: str
    sku_id: str
    qty: int
    expires_on: datetime.date


@dataclass(frozen=True)
class SkuEconomics(_Serializable):
    sku_id: str
    name: str
    unit_cost: float
    unit_price: float
    salvage_price: float
    shelf_life_days: int
    moq: int = 1
    cold_storage_units: float = 0.0


FRESH_MAX_SHELF_DAYS = 3


@dataclass(frozen=True)
class Constraints(_Serializable):
    budget_vnd: float | None = None
    cold_storage_capacity: float | None = None  # same unit as SkuEconomics.cold_storage_units
    stockout_penalty_vnd: float = 0.0  # loss of goodwill per unit short, on top of the lost margin
    holding_cost_rate_per_day: float = 0.005  # share of unit_cost per unsold, unexpired unit per day
    # Overnight carry-over cost for short-shelf-life items (shelf_life_days <= FRESH_MAX_SHELF_DAYS).
    # 0.20 is the sim30-v2 revision (docs/experiments/sim30-protocol.md); None falls back to the rate above.
    fresh_carry_cost_rate_per_day: float | None = 0.20


@dataclass(frozen=True)
class PlanLine(_Serializable):
    store_id: str
    sku_id: str
    qty: int
    cost_vnd: int
    service_level_pct: float
    expected_waste_units: float
    expected_shortage_units: float


@dataclass(frozen=True)
class InventoryPlan(_Serializable):
    name: str  # "safe" | "balanced" | "lean"
    label_vi: str  # "An toàn" | "Cân bằng" | "Tiết kiệm"
    lines: list[PlanLine]
    total_cost_vnd: int  # purchase amount of the order
    items_ordered: int  # SKUs with qty > 0
    expected_loss_vnd: int  # expected waste cost + shortage cost + holding cost
    expected_waste_pct: float
    expected_stockout_pct: float
    service_level_pct: float  # probability (demand-weighted over SKUs) of no stockout over the horizon
    target_service_pct: float | None  # 85 / 50 for safe / lean, None for the cost-optimal plan
    constrained: bool
    rationale_vi: str
    assumptions_vi: list[str] = field(default_factory=list)
    # Unexpired units carried overnight, summed over the horizon's nights (for a 1-day plan: what is left on
    # the shelf at closing, tomorrow's waste risk for fresh goods). Waste % only counts what expires within the
    # horizon, so ordering more can lower it; this shows the other side of the trade-off.
    expected_leftover_units: float = 0.0


@dataclass(frozen=True)
class MarkdownSlot(_Serializable):
    start: datetime.datetime
    discount_pct: int
    price_vnd: int
    expected_units_sold: float


@dataclass(frozen=True)
class MarkdownPlan(_Serializable):
    store_id: str
    sku_id: str
    units_at_risk: int
    schedule: list[MarkdownSlot]
    expected_units_sold: float
    expected_units_wasted: float
    recovered_revenue_vnd: int
    waste_cost_vnd: int
    net_value_vnd: int  # recovered revenue − waste cost
    baseline_units_wasted: float  # without any discount
    baseline_revenue_vnd: int
    baseline_net_value_vnd: int
    gain_vs_no_discount_vnd: int  # on the objective (revenue − waste cost)
    cash_gain_vnd: int  # extra sales + salvage money vs no discount (used to compare with transfer)
    elasticity: float
    rationale_vi: str


@dataclass(frozen=True)
class TransferLine(_Serializable):
    from_store_id: str
    to_store_id: str
    sku_id: str
    qty: int
    value_vnd: int  # (unit_price − salvage_price + stockout penalty) × qty


@dataclass(frozen=True)
class TransferPlan(_Serializable):
    from_store_id: str
    lines: list[TransferLine]
    units_moved: int
    destinations: int
    routed: bool  # the router was called
    recommended: bool  # net saving > 0 after routing
    km: float
    vehicles: int
    trip_cost_vnd: int
    saved_value_vnd: int  # value of the units actually delivered
    net_saving_vnd: int  # saved value − trip cost
    unserved_store_ids: list[str]
    rationale_vi: str
    route_plan: dict[str, Any] | None = None


@dataclass(frozen=True)
class Comparison(_Serializable):
    store_id: str
    sku_id: str
    markdown_gain_vnd: int
    transfer_gain_vnd: int
    difference_vnd: int  # |markdown gain − transfer gain|
    recommended: str  # "markdown" | "transfer" | "none"
    recommendation_vi: str
    # Non-cash value of avoided stockouts at the destinations (penalty × units); shown, never compared.
    transfer_stockout_value_vnd: int = 0
