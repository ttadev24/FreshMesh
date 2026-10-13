"""transfer_stock and compare_markdown_vs_transfer (spec §5.3)."""

from __future__ import annotations

import datetime
import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence

from decision.text import units, vnd
from decision.types import (
    Comparison,
    ForecastQuantiles,
    MarkdownPlan,
    SkuEconomics,
    StockLot,
    TransferLine,
    TransferPlan,
    jsonable,
)
from routing.models import Batch, DeliveryMode, Order, RoutePlan, Store

EARTH_RADIUS_KM = 6371.0


def _km(a: Store, b: Store) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a.lat, a.lng, b.lat, b.lng))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def stock_balance(
    forecasts: Sequence[ForecastQuantiles], stock: Sequence[StockLot], day: datetime.date
) -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], int]]:
    """Surplus and shortage per (store_id, sku_id) for `day`.

    surplus = usable stock − ceil(P90): units likely unsold even on a high-demand day;
    shortage = ceil(P50) − usable stock: units missing to cover the median demand.
    Usable stock = lots not yet expired on `day`.
    """
    on_hand: dict[tuple[str, str], int] = defaultdict(int)
    for lot in stock:
        if lot.expires_on >= day and lot.qty > 0:
            on_hand[(lot.store_id, lot.sku_id)] += lot.qty
    surplus: dict[tuple[str, str], int] = {}
    shortage: dict[tuple[str, str], int] = {}
    for f in forecasts:
        if f.date != day:
            continue
        key = (f.store_id, f.sku_id)
        have = on_hand.get(key, 0)
        if have > math.ceil(f.p90):
            surplus[key] = have - math.ceil(f.p90)
        elif math.ceil(f.p50) > have:
            shortage[key] = math.ceil(f.p50) - have
    return surplus, shortage


def transfer_stock(
    forecasts: Sequence[ForecastQuantiles],
    stock: Sequence[StockLot],
    stores: Mapping[str, Store],
    skus: Mapping[str, SkuEconomics],
    *,
    router: Callable[[Batch], RoutePlan],
    now: datetime.datetime,
    from_store_id: str | None = None,
    cost_per_km_vnd: float = 5_000.0,
    fixed_trip_cost_vnd: float = 30_000.0,
    stockout_penalty_vnd: float = 0.0,
    vehicle_capacity: int = 200,
    num_vehicles: int = 2,
    window_minutes: int = 240,
    service_minutes: float = 10.0,
    detour_factor: float = 1.3,
) -> TransferPlan:
    """Move surplus from one store (the routing depot) to shortage stores when it pays for the trip.

    Value of a moved unit = unit_price − salvage_price + stockout_penalty_vnd (sold at the destination
    instead of being salvaged at the origin). Trip cost = cost_per_km × km + fixed cost × vehicles.
    The router is called only if the value exceeds a lower bound of the trip cost (round trip to the
    farthest destination × detour_factor); the final decision uses the routed km and vehicles.
    """
    day = now.date()
    if not any(f.date == day for f in forecasts):
        raise ValueError(f"no forecast row for {day.isoformat()}: transfer_stock needs that day's demand")
    surplus, shortage = stock_balance(forecasts, stock, day)

    def unit_value(sku_id: str) -> float:
        s = skus[sku_id]
        return s.unit_price - s.salvage_price + stockout_penalty_vnd

    if from_store_id is None:
        totals: dict[str, float] = defaultdict(float)
        for (store_id, sku_id), q in surplus.items():
            totals[store_id] += q * unit_value(sku_id)
        from_store_id = max(sorted(totals), key=lambda s: totals[s]) if totals else ""
    if from_store_id and from_store_id not in stores:
        raise ValueError(f"unknown store {from_store_id}")

    def no_transfer(reason_vi: str, *, lines=(), km=0.0, cost=0, saved=0) -> TransferPlan:
        return TransferPlan(
            from_store_id=from_store_id or "",
            lines=list(lines),
            units_moved=sum(line.qty for line in lines),
            destinations=len({line.to_store_id for line in lines}),
            routed=False,
            recommended=False,
            km=round(km, 1),
            vehicles=0,
            trip_cost_vnd=cost,
            saved_value_vnd=saved,
            net_saving_vnd=0,
            unserved_store_ids=[],
            rationale_vi=reason_vi,
        )

    depot = stores.get(from_store_id) if from_store_id else None
    if depot is None:
        return no_transfer("Không có cửa hàng nào dư hàng so với dự báo P90, không cần điều chuyển.")

    # Greedy allocation: per SKU, nearest shortage stores first; one order per destination ≤ capacity.
    load: dict[str, int] = defaultdict(int)
    lines: list[TransferLine] = []
    for (src, sku_id), extra in sorted(surplus.items()):
        if src != from_store_id:
            continue
        targets = sorted(
            (k for k in shortage if k[1] == sku_id and k[0] != src and k[0] in stores),
            key=lambda k: (_km(depot, stores[k[0]]), k[0]),
        )
        for dst, _ in targets:
            qty = min(extra, shortage[(dst, sku_id)], vehicle_capacity - load[dst])
            if qty <= 0:
                continue
            extra -= qty
            load[dst] += qty
            lines.append(TransferLine(src, dst, sku_id, qty, round(qty * unit_value(sku_id))))
    if not lines:
        return no_transfer(f"Cửa hàng {from_store_id} không có hàng dư khớp với cửa hàng đang thiếu.")

    potential = sum(line.value_vnd for line in lines)
    bound_km = max(2 * _km(depot, stores[d]) for d in load) * detour_factor
    bound_cost = round(fixed_trip_cost_vnd + cost_per_km_vnd * bound_km)
    if potential <= bound_cost:
        return no_transfer(
            f"Không nên điều chuyển: giá trị cứu được {vnd(potential)} không vượt chi phí chuyến "
            f"tối thiểu ước tính {vnd(bound_cost)}.",
            lines=lines,
            km=bound_km,
            cost=bound_cost,
            saved=potential,
        )

    orders = [
        Order(
            order_id=dst,
            lat=stores[dst].lat,
            lng=stores[dst].lng,
            demand=units,
            earliest_min=0.0,
            latest_min=float(window_minutes),
            mode=DeliveryMode.HOME,
            service_min=service_minutes,
        )
        for dst, units in sorted(load.items())
    ]
    batch = Batch(depot, orders, [], num_vehicles, vehicle_capacity)
    plan = router(batch)

    unserved = sorted({r.order_id for r in plan.at_risk})
    delivered = [line for line in lines if line.to_store_id not in unserved]
    saved = sum(line.value_vnd for line in delivered)
    trip_cost = round(cost_per_km_vnd * plan.road_km + fixed_trip_cost_vnd * plan.vehicles_used)
    net = saved - trip_cost
    recommended = bool(delivered) and net > 0
    km = round(plan.road_km, 1)
    n_units = sum(line.qty for line in delivered)
    n_dest = len({line.to_store_id for line in delivered})
    if recommended:
        text = (
            f"Nên điều chuyển {n_units} đơn vị từ {from_store_id} sang {n_dest} cửa hàng thiếu: "
            f"{units(km)} km, {plan.vehicles_used} xe, chi phí chuyến {vnd(trip_cost)}, "
            f"giá trị cứu được {vnd(saved)}, lợi ròng {vnd(net)}."
        )
    else:
        text = (
            f"Không nên điều chuyển: sau khi tính lộ trình ({units(km)} km, {plan.vehicles_used} xe), "
            f"chi phí chuyến {vnd(trip_cost)} không thấp hơn giá trị cứu được {vnd(saved)}."
        )
    if unserved:
        text += f" Không giao kịp: {', '.join(unserved)}."
    return TransferPlan(
        from_store_id=from_store_id,
        lines=delivered,
        units_moved=n_units,
        destinations=n_dest,
        routed=True,
        recommended=recommended,
        km=km,
        vehicles=plan.vehicles_used,
        trip_cost_vnd=trip_cost,
        saved_value_vnd=saved,
        net_saving_vnd=net,
        unserved_store_ids=unserved,
        rationale_vi=text,
        route_plan=jsonable(plan),
    )


def compare_markdown_vs_transfer(
    markdown: MarkdownPlan,
    transfer: TransferPlan,
    *,
    non_cash_value_per_unit: float = 0.0,
    sku_name: str | None = None,
) -> Comparison:
    """Money comparison (VND) of the two ways to handle surplus of one SKU at one store.

    Both on a cash basis against doing nothing: markdown gain = extra sales revenue + salvage money vs no
    discount (MarkdownPlan.cash_gain_vnd); transfer gain = cash value of this SKU's moved units
    (line value − ``non_cash_value_per_unit`` × units, i.e. price − salvage when the line value also carries
    a stockout penalty) − its share (by units) of the trip cost. The removed non-cash part is reported as
    ``transfer_stockout_value_vnd`` and never enters the comparison. They are treated as alternatives.
    """
    if transfer.from_store_id and markdown.store_id and transfer.from_store_id != markdown.store_id:
        raise ValueError("markdown and transfer plans must be for the same store")
    sku_lines = [line for line in transfer.lines if line.sku_id == markdown.sku_id]
    total_units = sum(line.qty for line in transfer.lines)
    stockout_value = 0
    if sku_lines and transfer.routed:
        sku_units = sum(line.qty for line in sku_lines)
        share = transfer.trip_cost_vnd * sku_units / total_units
        stockout_value = sum(round(non_cash_value_per_unit * line.qty) for line in sku_lines)
        transfer_gain = round(sum(line.value_vnd for line in sku_lines) - stockout_value - share)
    else:
        transfer_gain = 0
    # Cash basis for both options: extra money in (sales + salvage) versus doing nothing.
    markdown_gain = markdown.cash_gain_vnd

    head = (
        f"Với {sku_name or markdown.sku_id} tại {markdown.store_id or transfer.from_store_id}: "
        "giảm giá theo khung giờ "
        f"lợi thêm {vnd(markdown_gain)}, điều chuyển lợi thêm {vnd(transfer_gain)} tiền mặt"
    )
    if max(markdown_gain, transfer_gain) <= 0:
        recommended = "none"
        text = f"{head}. Cả hai cách đều không mang lại thêm tiền, giữ nguyên giá và không điều chuyển."
    elif transfer_gain > markdown_gain:
        recommended = "transfer"
        text = f"{head}. Nên điều chuyển (hơn {vnd(transfer_gain - markdown_gain)})."
    else:
        recommended = "markdown"
        text = f"{head}. Nên giảm giá theo khung giờ (hơn {vnd(markdown_gain - transfer_gain)})."
    if stockout_value:
        text += (
            " Điều chuyển còn giúp tránh thiếu hàng ở cửa hàng nhận "
            f"(giá trị ước tính {vnd(stockout_value)}, không phải tiền mặt nên không tính vào so sánh)."
        )
    if not transfer.routed:
        text += f" Điều chuyển không được tính lộ trình: {transfer.rationale_vi}"
    return Comparison(
        store_id=markdown.store_id or transfer.from_store_id,
        sku_id=markdown.sku_id,
        markdown_gain_vnd=markdown_gain,
        transfer_gain_vnd=transfer_gain,
        difference_vnd=abs(markdown_gain - transfer_gain),
        recommended=recommended,
        recommendation_vi=text,
        transfer_stockout_value_vnd=stockout_value,
    )
