import datetime as dt

import pytest

from decision.markdown import suggest_markdown
from decision.transfer import compare_markdown_vs_transfer, stock_balance, transfer_stock
from decision.types import ForecastQuantiles, MarkdownPlan, SkuEconomics, StockLot, TransferLine, TransferPlan
from routing.config import RoutingConfig
from routing.geo import TravelPlane
from routing.models import AtRiskOrder, Batch, DeliveryMode, RoutePlan, Stop, Store, VehicleRoute
from routing.validate import screen_orders
from tests.routing.helpers import point_at

NOW = dt.datetime(2026, 10, 1, 14, 0)
DAY = NOW.date()
RAU = SkuEconomics("RAU", "Rau muống", 20_000, 30_000, 2_000, 1, 1, 1.0)
SKUS = {"RAU": RAU}
STORES = {
    "S3": Store("S3", *point_at(0, 0)),
    "S1": Store("S1", *point_at(2, 0)),
    "S2": Store("S2", *point_at(0, 3)),
    "FAR": Store("FAR", *point_at(100, 0)),
}


class FakeRouter:
    def __init__(self, road_km=8.0, at_risk=()):
        self.road_km = road_km
        self.at_risk = list(at_risk)
        self.batches: list[Batch] = []

    def __call__(self, batch: Batch) -> RoutePlan:
        self.batches.append(batch)
        served = [o for o in batch.orders if o.order_id not in self.at_risk]
        stops = [Stop(o.order_id, "home", None, 10 * (i + 1), False) for i, o in enumerate(served)]
        return RoutePlan(
            batch.store.store_id,
            [VehicleRoute(stops)] if stops else [],
            self.road_km * 3,
            self.road_km,
            1 if stops else 0,
            False,
            [AtRiskOrder(r, "unreachable_in_window") for r in self.at_risk],
            "fake",
            0.0,
        )


def fq(store, p50, p90, p10=None):
    return ForecastQuantiles(store, "RAU", DAY, p10 if p10 is not None else p50 * 0.7, p50, p90)


def scenario():
    forecasts = [fq("S3", 40, 50), fq("S1", 30, 40), fq("S2", 40, 55), fq("FAR", 10, 12)]
    stock = [StockLot("S3", "RAU", 100, DAY), StockLot("S1", "RAU", 5, DAY), StockLot("FAR", "RAU", 12, DAY)]
    return forecasts, stock


def test_stock_balance_uses_p90_for_surplus_and_p50_for_shortage():
    forecasts, stock = scenario()
    surplus, shortage = stock_balance(
        forecasts, stock + [StockLot("S2", "RAU", 9, DAY - dt.timedelta(days=1))], DAY
    )
    assert surplus == {("S3", "RAU"): 50}
    assert shortage == {("S1", "RAU"): 25, ("S2", "RAU"): 40}  # expired lot at S2 ignored


def test_transfer_builds_valid_batch_and_reports_saving():
    forecasts, stock = scenario()
    router = FakeRouter(road_km=8.0)
    plan = transfer_stock(forecasts, stock, STORES, SKUS, router=router, now=NOW)
    assert plan.from_store_id == "S3"  # picked automatically: largest surplus
    assert len(router.batches) == 1
    batch = router.batches[0]
    assert batch.store == STORES["S3"] and batch.pickup_points == []
    assert {o.order_id: o.demand for o in batch.orders} == {"S1": 25, "S2": 25}  # nearest first
    assert all(o.mode == DeliveryMode.HOME and o.latest_min <= 240 for o in batch.orders)
    cfg = RoutingConfig()
    screening = screen_orders(batch, TravelPlane(batch.store.lat, batch.store.lng, cfg), cfg)
    assert screening.at_risk == []
    assert plan.saved_value_vnd == 50 * 28_000
    assert plan.trip_cost_vnd == 8 * 5_000 + 30_000
    assert plan.net_saving_vnd == plan.saved_value_vnd - plan.trip_cost_vnd
    assert plan.recommended and plan.routed and plan.km == 8.0 and plan.vehicles == 1
    assert plan.units_moved == 50 and plan.destinations == 2
    assert "1.330.000 đ" in plan.rationale_vi
    d = plan.to_dict()
    assert "source" not in d and d["route_plan"]["road_km"] == 8.0


def test_router_not_called_when_value_below_trip_cost_bound():
    forecasts = [fq("S3", 40, 50), fq("FAR", 10, 12)]
    stock = [StockLot("S3", "RAU", 52, DAY), StockLot("FAR", "RAU", 9, DAY)]
    router = FakeRouter()
    plan = transfer_stock(forecasts, stock, STORES, SKUS, router=router, now=NOW, from_store_id="S3")
    assert router.batches == []
    assert not plan.routed and not plan.recommended
    assert plan.trip_cost_vnd > plan.saved_value_vnd


def test_not_recommended_when_routed_km_is_expensive():
    forecasts, stock = scenario()
    plan = transfer_stock(forecasts, stock, STORES, SKUS, router=FakeRouter(road_km=400.0), now=NOW)
    assert plan.routed and not plan.recommended
    assert plan.net_saving_vnd < 0


def test_unserved_stores_are_dropped_from_saving():
    forecasts, stock = scenario()
    plan = transfer_stock(forecasts, stock, STORES, SKUS, router=FakeRouter(at_risk=["S2"]), now=NOW)
    assert plan.unserved_store_ids == ["S2"]
    assert [line.to_store_id for line in plan.lines] == ["S1"]
    assert plan.saved_value_vnd == 25 * 28_000


def test_destination_load_respects_vehicle_capacity():
    forecasts, stock = scenario()
    router = FakeRouter()
    transfer_stock(forecasts, stock, STORES, SKUS, router=router, now=NOW, vehicle_capacity=20)
    assert all(o.demand <= 20 for o in router.batches[0].orders)


def test_no_surplus_means_no_routing():
    forecasts = [fq("S1", 30, 40), fq("S2", 40, 55)]
    router = FakeRouter()
    plan = transfer_stock(forecasts, [], STORES, SKUS, router=router, now=NOW)
    assert router.batches == [] and plan.lines == [] and not plan.recommended


def _markdown(gain: int) -> MarkdownPlan:
    return MarkdownPlan(
        store_id="S3",
        sku_id="RAU",
        units_at_risk=50,
        schedule=[],
        expected_units_sold=40.0,
        expected_units_wasted=10.0,
        recovered_revenue_vnd=900_000,
        waste_cost_vnd=180_000,
        net_value_vnd=720_000,
        baseline_units_wasted=30.0,
        baseline_revenue_vnd=900_000 - gain,
        baseline_net_value_vnd=720_000 - gain,
        gain_vs_no_discount_vnd=gain,
        cash_gain_vnd=gain,
        elasticity=2.0,
        rationale_vi="",
    )


def _transfer(net_value: int, cost: int, routed=True) -> TransferPlan:
    return TransferPlan(
        from_store_id="S3",
        lines=[TransferLine("S3", "S1", "RAU", 10, net_value)],
        units_moved=10,
        destinations=1,
        routed=routed,
        recommended=routed,
        km=5.0,
        vehicles=1,
        trip_cost_vnd=cost,
        saved_value_vnd=net_value,
        net_saving_vnd=net_value - cost,
        unserved_store_ids=[],
        rationale_vi="",
    )


@pytest.mark.parametrize(
    "md_gain,value,cost,expected",
    [
        (300_000, 500_000, 50_000, "transfer"),
        (600_000, 500_000, 50_000, "markdown"),
        (0, 40_000, 50_000, "none"),
    ],
)
def test_compare_recommends_larger_money_gain(md_gain, value, cost, expected):
    c = compare_markdown_vs_transfer(_markdown(md_gain), _transfer(value, cost))
    assert c.recommended == expected
    assert c.markdown_gain_vnd == md_gain
    assert c.transfer_gain_vnd == value - cost
    assert c.difference_vnd == abs(md_gain - (value - cost))
    assert f"{c.difference_vnd:,}".replace(",", ".") in c.recommendation_vi or expected == "none"
    assert "source" not in c.to_dict()


def test_compare_uses_cash_basis_so_full_price_transfer_beats_markdown():
    # 10 units would be wasted; markdown sells them discounted, transfer sells them at full price elsewhere.
    sku = SkuEconomics("RAU", "Rau muống", 20_000, 30_000, 2_000, 1, 1, 1.0)
    now = NOW.replace(hour=21)
    hourly = {now: 4.0}
    md = suggest_markdown([StockLot("S3", "RAU", 14, DAY)], hourly, sku, 4.0, now=now)
    assert md.schedule[0].discount_pct > 0
    rescued = md.baseline_units_wasted - md.expected_units_wasted
    assert md.cash_gain_vnd == pytest.approx(
        md.recovered_revenue_vnd - md.baseline_revenue_vnd - 2_000 * rescued, abs=300
    )
    value = round(rescued * (30_000 - 2_000))
    c = compare_markdown_vs_transfer(md, _transfer(value, 1_000))
    assert c.recommended == "transfer"


def test_transfer_requires_forecast_for_today():
    forecasts = [ForecastQuantiles("S3", "RAU", DAY + dt.timedelta(days=1), 30, 40, 50)]
    with pytest.raises(ValueError):
        transfer_stock(forecasts, [], STORES, SKUS, router=FakeRouter(), now=NOW)


def test_compare_end_to_end_with_markdown_and_fake_router():
    forecasts, stock = scenario()
    transfer = transfer_stock(forecasts, stock, STORES, SKUS, router=FakeRouter(), now=NOW)
    hourly = {NOW + dt.timedelta(hours=h): 5.0 for h in range(8)}
    md = suggest_markdown([s for s in stock if s.store_id == "S3"], hourly, RAU, 2.0, now=NOW)
    c = compare_markdown_vs_transfer(md, transfer)
    assert c.store_id == "S3" and c.recommended in {"markdown", "transfer"}
    assert "Nên" in c.recommendation_vi


def test_compare_removes_non_cash_stockout_value_from_cash_gain():
    """MED-2: the stockout penalty folded into line values is not cash; it is reported separately."""
    # 10 units, line value 500_000 of which 10 × 15_000 is the (non-cash) stockout penalty; trip 50_000.
    c = compare_markdown_vs_transfer(
        _markdown(280_000), _transfer(500_000, 50_000), non_cash_value_per_unit=15_000
    )
    assert c.transfer_gain_vnd == 500_000 - 150_000 - 50_000
    assert c.transfer_stockout_value_vnd == 150_000
    assert c.recommended == "transfer" and c.difference_vnd == 20_000
    c = compare_markdown_vs_transfer(
        _markdown(280_000), _transfer(500_000, 50_000), non_cash_value_per_unit=20_000
    )
    assert c.recommended == "markdown"  # with the penalty counted as money, transfer would have won
    assert "thiếu hàng" in c.recommendation_vi
