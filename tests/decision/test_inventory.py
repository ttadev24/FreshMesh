import datetime as dt

import numpy as np
import pytest

from decision.distribution import QuantileDistribution
from decision.inventory import critical_ratio, plan_inventory, simulate_fifo
from decision.types import Constraints, ForecastQuantiles, SkuEconomics, StockLot

D0 = dt.date(2026, 10, 1)


def sku(sku_id="RAU", *, cost=20_000, price=30_000, salvage=5_000, life=1, moq=1, cold=0.0):
    return SkuEconomics(sku_id, f"Hàng {sku_id}", cost, price, salvage, life, moq, cold)


def fc(sku_id="RAU", p=(40.0, 60.0, 90.0), days=1, store="S1"):
    return [ForecastQuantiles(store, sku_id, D0 + dt.timedelta(days=k), *p) for k in range(days)]


def by_name(plans):
    return {p.name: p for p in plans}


def qty_of(plan, sku_id="RAU"):
    return next(line.qty for line in plan.lines if line.sku_id == sku_id)


# ---------- newsvendor ----------


@pytest.mark.parametrize("penalty", [0.0, 35_000.0])
def test_newsvendor_balanced_plan_hits_critical_ratio(penalty):
    s = sku()
    cr = critical_ratio(s, penalty)
    expected_q = QuantileDistribution(40.0, 60.0, 90.0).ppf(cr)
    plans = by_name(
        plan_inventory(fc(), [], {"RAU": s}, Constraints(stockout_penalty_vnd=penalty), n_sims=6000, seed=1)
    )
    assert qty_of(plans["balanced"]) == pytest.approx(expected_q, abs=3)


def test_service_targets_match_quantiles():
    s = sku(price=60_000)  # CR between 0.5 and 0.85
    plans = by_name(plan_inventory(fc(), [], {"RAU": s}, Constraints(), n_sims=6000, seed=2))
    d = QuantileDistribution(40.0, 60.0, 90.0)
    assert qty_of(plans["safe"]) == pytest.approx(d.ppf(0.85), abs=3)
    assert qty_of(plans["lean"]) == pytest.approx(d.ppf(0.50), abs=3)
    assert plans["safe"].target_service_pct == 85.0
    assert plans["balanced"].target_service_pct is None


# ---------- FIFO ----------


def test_fifo_lot_is_discarded_at_end_of_its_expiry_day():
    lots = [(0, 5), (1, 3)]
    waste, short, _, _ = simulate_fifo(np.array([0]), 0, lots, np.zeros((1, 1), dtype=int))
    assert waste[0, 0] == 5  # day-0 lot wasted on day 0, day-1 lot still good
    waste, _, _, _ = simulate_fifo(np.array([0]), 0, lots, np.zeros((1, 2), dtype=int))
    assert waste[0, 0] == 8


def test_fifo_sells_oldest_expiry_first_and_counts_shortage():
    # new lot (5 units) expires day 0, existing lot (3) expires day 1; demand 2 then 4
    waste, short, carried, avail = simulate_fifo(np.array([5]), 0, [(1, 3)], np.array([[2, 4]]))
    assert waste[0, 0] == 3  # 3 unsold units of the new lot
    assert short[0, 0] == 1  # day 1: only 3 left for demand 4
    assert carried[0, 0] == 3  # existing lot carried overnight
    assert avail[0, 0] == 8


def test_plan_counts_waste_of_existing_stock_on_exact_day():
    s = sku()
    zero = fc(p=(0.0, 0.0, 0.0))
    today = [StockLot("S1", "RAU", 10, D0)]
    plans = plan_inventory(zero, today, {"RAU": s}, Constraints(), n_sims=200)
    assert all(qty_of(p) == 0 for p in plans)
    assert plans[0].lines[0].expected_waste_units == 10.0
    tomorrow = [StockLot("S1", "RAU", 10, D0 + dt.timedelta(days=1))]
    plans = plan_inventory(zero, tomorrow, {"RAU": s}, Constraints(), n_sims=200)
    assert plans[0].lines[0].expected_waste_units == 0.0


def test_existing_stock_reduces_order():
    s = sku(life=2)
    lots = [StockLot("S1", "RAU", 40, D0 + dt.timedelta(days=1))]
    a = by_name(plan_inventory(fc(), [], {"RAU": s}, Constraints(), n_sims=2000))
    b = by_name(plan_inventory(fc(), lots, {"RAU": s}, Constraints(), n_sims=2000))
    assert qty_of(b["balanced"]) < qty_of(a["balanced"])


# ---------- MOQ / constraints ----------


def test_quantities_are_multiples_of_moq():
    s = sku(moq=12)
    plans = plan_inventory(fc(), [], {"RAU": s}, Constraints(), n_sims=2000)
    for p in plans:
        assert qty_of(p) % 12 == 0
    safe = by_name(plans)["safe"]
    assert qty_of(safe) >= QuantileDistribution(40.0, 60.0, 90.0).ppf(0.85) - 12


def test_budget_is_respected_and_stated():
    skus = {"RAU": sku("RAU"), "THIT": sku("THIT", cost=80_000, price=120_000, salvage=20_000)}
    forecasts = fc("RAU") + fc("THIT", p=(10.0, 15.0, 22.0))
    budget = 1_500_000
    plans = plan_inventory(forecasts, [], skus, Constraints(budget_vnd=budget), n_sims=1000)
    for p in plans:
        assert p.total_cost_vnd <= budget
    assert plans[0].constrained
    assert "ngân sách" in plans[0].rationale_vi


def test_budget_below_one_pack_orders_nothing():
    s = sku(moq=10)
    plans = plan_inventory(fc(), [], {"RAU": s}, Constraints(budget_vnd=150_000), n_sims=500)
    assert all(qty_of(p) == 0 for p in plans)


def test_cold_storage_capacity_counts_existing_stock():
    s = sku(cold=1.0, life=2)
    lots = [StockLot("S1", "RAU", 20, D0 + dt.timedelta(days=1))]
    plans = plan_inventory(fc(), lots, {"RAU": s}, Constraints(cold_storage_capacity=50), n_sims=1000)
    for p in plans:
        assert qty_of(p) + 20 <= 50
    assert "kho lạnh" in plans[0].rationale_vi


# ---------- ordering / output ----------


@pytest.mark.parametrize("penalty,price", [(0.0, 22_000), (0.0, 60_000), (200_000.0, 30_000)])
def test_plans_ordered_by_service_level(penalty, price):
    s = sku(price=price)
    plans = plan_inventory(fc(), [], {"RAU": s}, Constraints(stockout_penalty_vnd=penalty), n_sims=2000)
    assert [p.label_vi for p in plans] == ["An toàn", "Cân bằng", "Tiết kiệm"]
    q = [qty_of(p) for p in plans]
    assert q[0] >= q[1] >= q[2]
    sl = [p.service_level_pct for p in plans]
    assert sl[0] >= sl[1] >= sl[2]


def test_ordering_holds_after_budget_scaling():
    skus = {"RAU": sku("RAU", price=60_000), "THIT": sku("THIT", cost=80_000, price=200_000, salvage=10_000)}
    forecasts = fc("RAU") + fc("THIT", p=(10.0, 15.0, 22.0))
    plans = plan_inventory(forecasts, [], skus, Constraints(budget_vnd=1_800_000), n_sims=1000)
    for sku_id in skus:
        q = [qty_of(p, sku_id) for p in plans]
        assert q[0] >= q[1] >= q[2]


def test_deterministic_with_seed_and_serializable():
    s = sku()
    a = plan_inventory(fc(days=2), [], {"RAU": s}, Constraints(), horizon_days=2, n_sims=500, seed=7)
    b = plan_inventory(fc(days=2), [], {"RAU": s}, Constraints(), horizon_days=2, n_sims=500, seed=7)
    assert [p.to_dict() for p in a] == [p.to_dict() for p in b]
    d = a[0].to_dict()
    assert "source" not in d
    assert {
        "name",
        "label_vi",
        "lines",
        "total_cost_vnd",
        "expected_waste_pct",
        "expected_stockout_pct",
        "rationale_vi",
        "assumptions_vi",
    } <= d.keys()
    assert {"sku_id", "qty", "cost_vnd"} <= d["lines"][0].keys()


def test_rationale_numbers_come_from_plan_fields():
    s = sku()
    p = plan_inventory(fc(), [], {"RAU": s}, Constraints(), n_sims=500)[1]
    total = f"{p.total_cost_vnd:,}".replace(",", ".")
    assert total in p.rationale_vi
    assert f"{p.expected_waste_pct:.1f}".replace(".", ",") + "%" in p.rationale_vi


def test_unreachable_service_target_does_not_jump_to_search_cap():
    s = sku(life=1)  # one delivery cannot cover day 2
    plans = by_name(plan_inventory(fc(days=2), [], {"RAU": s}, Constraints(), horizon_days=2, n_sims=2000))
    assert qty_of(plans["safe"]) <= qty_of(plans["balanced"]) + 1
    assert "không đạt được" in plans["safe"].rationale_vi
    assert plans["safe"].items_ordered == 1


def test_rejects_multiple_stores_and_missing_days():
    s = sku()
    with pytest.raises(ValueError):
        plan_inventory(fc(store="S1") + fc(store="S2"), [], {"RAU": s}, Constraints())
    with pytest.raises(ValueError):
        plan_inventory(fc(days=1), [], {"RAU": s}, Constraints(), horizon_days=2)


def test_assumptions_state_the_fresh_carry_cost_actually_used():
    """MED-5: the user-facing assumptions describe the 20%/day overnight cost of fresh items."""
    from decision.inventory import inventory_assumptions_vi
    from decision.text import pct

    default = " ".join(inventory_assumptions_vi(Constraints()))
    assert f"{pct(20)}" in default and "hạn dùng ≤ 3 ngày" in default and pct(0.5) in default
    plans = plan_inventory(
        fc(), [], {"RAU": sku()}, Constraints(fresh_carry_cost_rate_per_day=0.1), n_sims=500
    )
    assert pct(10) in " ".join(plans[0].assumptions_vi)
    off = " ".join(inventory_assumptions_vi(Constraints(fresh_carry_cost_rate_per_day=None)))
    assert "hạn dùng ≤ 3 ngày" not in off
