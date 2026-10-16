import datetime as dt
import math

from decision.frontier import pareto, waste_at
from decision.inventory import (
    FRONTIER_TARGETS,
    plan_inventory,
    plan_inventory_with_frontier,
    quantity_for_service,
)
from decision.types import Constraints, ForecastQuantiles, SkuEconomics, StockLot


def test_pareto_keeps_only_non_dominated_points_in_stockout_order():
    pts = [(10.0, 5.0), (5.0, 9.0), (12.0, 6.0), (2.0, 20.0), (5.0, 8.0), (20.0, 1.0)]
    assert pareto(pts) == [(2.0, 20.0), (5.0, 8.0), (10.0, 5.0), (20.0, 1.0)]


def test_waste_at_interpolates_and_refuses_to_extrapolate():
    f = [(2.0, 20.0), (10.0, 4.0), (20.0, 1.0)]
    assert waste_at(f, 6.0) == 12.0 and waste_at(f, 10.0) == 4.0
    assert math.isnan(waste_at(f, 1.0)) and math.isnan(waste_at(f, 25.0)) and math.isnan(waste_at([], 5.0))


SKU = SkuEconomics("K", "Rau", unit_cost=1.0, unit_price=2.0, salvage_price=0.0, shelf_life_days=2)
DAY = dt.date(2024, 6, 12)


def test_quantity_for_service_rises_with_the_target_and_counts_stock_on_hand():
    rows = [ForecastQuantiles("S", "K", DAY, 20.0, 30.0, 45.0)]
    lean, s_lean = quantity_for_service("S", SKU, rows, [], 0.5)
    safe, s_safe = quantity_for_service("S", SKU, rows, [], 0.9)
    assert lean < safe and s_lean >= 0.5 and s_safe >= 0.9
    assert 25 <= lean <= 35  # around the median
    with_stock, _ = quantity_for_service("S", SKU, rows, [StockLot("S", "K", 10, DAY)], 0.9)
    assert with_stock < safe  # usable stock reduces the order


def test_plans_are_unchanged_and_the_frontier_is_monotone():
    skus = {"K": SKU, "L": SkuEconomics("L", "Thịt", 3.0, 5.0, 0.5, 1)}
    rows = [ForecastQuantiles("S", "K", DAY, 20.0, 30.0, 45.0), ForecastQuantiles("S", "L", DAY, 5.0, 8.0, 12.0)]
    stock = [StockLot("S", "K", 6, DAY)]
    plans, frontier = plan_inventory_with_frontier(rows, stock, skus, Constraints())
    assert plans == plan_inventory(rows, stock, skus, Constraints())
    assert [f.target_service_pct for f in frontier] == [round(100 * t, 1) for t in FRONTIER_TARGETS]
    for a, b in zip(frontier, frontier[1:], strict=False):
        assert b.total_cost_vnd >= a.total_cost_vnd and b.expected_stockout_pct <= a.expected_stockout_pct
    lean = next(p for p in plans if p.name == "lean")
    at_50 = frontier[0]
    assert {ln.sku_id: ln.qty for ln in at_50.lines} == {ln.sku_id: ln.qty for ln in lean.lines} or (
        lean.total_cost_vnd <= at_50.total_cost_vnd  # lean is capped at the balanced plan
    )


FR = [  # a monotone frontier: more service costs more and leaves more stock overnight
    {"name": f"target_{t}", "label_vi": f"Mức phục vụ {t}%", "total_cost_vnd": c, "expected_stockout_pct": so,
     "service_level_pct": sv, "expected_leftover_units": lo}
    for t, c, so, sv, lo in ((50, 2_000_000, 7.0, 55.0, 2.0), (80, 3_000_000, 2.5, 82.0, 6.0),
                             (90, 4_000_000, 1.0, 91.0, 11.0), (98, 6_000_000, 0.2, 98.0, 20.0))
]  # fmt: skip


def test_goal_picks_the_cheapest_point_meeting_every_goal():
    from decision.frontier import choose_for_goal

    out = choose_for_goal(FR, {"max_stockout_pct": 3.0, "max_cost_vnd": None})
    assert out["met"] and out["name"] == "target_80" and out["escalation"] is None
    assert "3.000.000 đ" in out["reason_vi"]


def test_unreachable_goal_asks_with_the_best_achievable_value():
    from decision.frontier import choose_for_goal

    out = choose_for_goal(FR, {"max_stockout_pct": 0.05})
    assert not out["met"] and out["escalation"]["kind"] == "out_of_scope"
    assert "0,2%" in out["escalation"]["question_vi"]


def test_conflicting_goals_return_one_specific_question_with_two_options():
    from decision.frontier import choose_for_goal

    out = choose_for_goal(FR, {"max_stockout_pct": 1.0, "max_cost_vnd": 3_500_000, "max_leftover_units": 50})
    q = out["escalation"]["question_vi"]
    assert not out["met"] and "tiền nhập" in q and "hết hàng" in q and "tồn mang sang" not in q
    assert out["escalation"]["choices_vi"] == ["Mức phục vụ 90% (target_90)", "Mức phục vụ 80% (target_80)"]


def test_unknown_goal_key_is_rejected():
    import pytest

    from decision.frontier import choose_for_goal

    with pytest.raises(ValueError):
        choose_for_goal(FR, {"max_waste_pct": 3})
