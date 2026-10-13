import datetime as dt

import numpy as np
import pytest

from decision.markdown import _poisson_pmf, _sell, suggest_markdown
from decision.types import SkuEconomics, StockLot

NOW = dt.datetime(2026, 10, 1, 14, 0)
SKU = SkuEconomics("RAU", "Rau muống", 20_000, 30_000, 2_000, 1, 1, 1.0)


def forecast(hours=8, rate=4.0, start=NOW):
    return {start + dt.timedelta(hours=h): rate for h in range(hours)}


def lots(qty, expires=NOW.date()):
    return [StockLot("S3", "RAU", qty, expires)]


def discounts(plan):
    return [s.discount_pct for s in plan.schedule]


def test_poisson_step_matches_expected_sales():
    pmf = _poisson_pmf(3.0, 50)
    assert pmf.sum() == pytest.approx(1.0)
    start = np.zeros(51)
    start[50] = 1.0
    after, sold = _sell(start, pmf)
    assert sold == pytest.approx(3.0, abs=1e-6)  # plenty of stock: sells the mean
    tight = np.zeros(3)
    tight[2] = 1.0
    after, sold = _sell(tight, _poisson_pmf(3.0, 2))
    p0, p1 = np.exp(-3.0), 3.0 * np.exp(-3.0)
    assert sold == pytest.approx(p1 * 1 + (1 - p0 - p1) * 2)  # E[min(2, D)]
    assert after.sum() == pytest.approx(1.0)


@pytest.mark.parametrize("stock", [45, 200])
def test_zero_elasticity_never_discounts(stock):
    plan = suggest_markdown(lots(stock), forecast(), SKU, 0.0, now=NOW)
    assert set(discounts(plan)) == {0}
    assert plan.gain_vs_no_discount_vnd == 0


def test_moderate_surplus_discounts_rise_toward_closing():
    plan = suggest_markdown(lots(40), forecast(), SKU, 2.0, now=NOW)
    d = discounts(plan)
    assert d[0] == 0 and d[-1] > 0
    assert d == sorted(d)
    assert plan.expected_units_wasted < plan.baseline_units_wasted
    assert plan.gain_vs_no_discount_vnd > 0


def test_large_surplus_with_high_elasticity_reaches_deep_discount():
    plan = suggest_markdown(lots(200), forecast(), SKU, 3.0, now=NOW)
    d = discounts(plan)
    assert d == sorted(d) and d[-1] == 50
    assert plan.net_value_vnd == plan.recovered_revenue_vnd - plan.waste_cost_vnd
    assert plan.net_value_vnd > plan.baseline_net_value_vnd


def test_elasticity_sign_is_ignored():
    a = suggest_markdown(lots(60), forecast(), SKU, 2.5, now=NOW)
    b = suggest_markdown(lots(60), forecast(), SKU, -2.5, now=NOW)
    assert discounts(a) == discounts(b)


def test_only_future_slots_and_expiring_lots_are_used():
    fc = forecast(hours=10, start=NOW - dt.timedelta(hours=2))
    stock = lots(30) + lots(100, NOW.date() + dt.timedelta(days=2))
    plan = suggest_markdown(stock, fc, SKU, 2.0, now=NOW + dt.timedelta(minutes=30))
    assert plan.schedule[0].start == NOW
    assert len(plan.schedule) == 8
    assert plan.units_at_risk == 30


def test_no_stock_at_risk_gives_empty_outcome():
    plan = suggest_markdown([], forecast(), SKU, 2.0, now=NOW)
    assert plan.units_at_risk == 0 and plan.expected_units_wasted == 0
    assert set(discounts(plan)) == {0}


def test_output_is_serializable_and_rationale_uses_fields():
    plan = suggest_markdown(lots(60), forecast(), SKU, 2.5, now=NOW)
    d = plan.to_dict()
    assert d["source"] == "SIMULATED"
    assert d["schedule"][0]["start"] == NOW.isoformat()
    assert f"{plan.recovered_revenue_vnd:,}".replace(",", ".") in plan.rationale_vi
    assert sum(s.expected_units_sold for s in plan.schedule) == pytest.approx(plan.expected_units_sold, abs=0.5)
