import datetime as dt

import numpy as np
import pytest

from decision import ForecastQuantiles
from decision.types import SkuEconomics
from simulation.freshmesh import FreshMeshPolicy, lots_from_rows
from simulation.inventory import (
    DayContext,
    Lot,
    MeanSalesBaseline,
    SkuSpec,
    discard_expired,
    ledger_metrics,
    round_to_moq,
    serve_fifo,
    simulate_policy,
)

D0 = dt.date(2026, 10, 1)
SKUS = {
    "R1": SkuSpec("R1", 1, 5, 4000.0, 7000.0, 0.0),
    "R2": SkuSpec("R2", 2, 10, 8000.0, 12000.0, 2000.0),
    "R3": SkuSpec("R3", 3, 6, 32000.0, 42000.0, 15000.0),
}
STORES = ("S1", "S2")


def _inputs(seed: int = 0, n: int = 20):
    rng = np.random.default_rng(seed)
    keys = [(s, k) for s in STORES for k in SKUS]
    demand = {key: rng.poisson(12, n).tolist() for key in keys}
    price = {key: [SKUS[key[1]].unit_price] * n for key in keys}
    promo = {key: [int(x) for x in rng.random(n) < 0.1] for key in keys}
    opening = {("S1", "R2"): [Lot(1, 0, 7), Lot(2, 0, 9)], ("S2", "R3"): [Lot(3, -1, 20)]}
    dates = [D0 + dt.timedelta(days=i) for i in range(n)]
    return keys, opening, demand, price, promo, [0.0] * n, dates


class RandomPolicy:
    name = "random"

    def __init__(self, seed: int):
        self.rng = np.random.default_rng(seed)

    def order(self, ctx):
        return {(s, k): int(self.rng.integers(0, 30)) for s in STORES for k in SKUS}

    def observe(self, day, date, sales, extra):
        pass


def test_serve_fifo_sells_oldest_expiry_first():
    lots = [Lot(3, 1, 5), Lot(1, 0, 4), Lot(2, 0, 6)]
    sold, lost = serve_fifo(lots, 7)
    assert (sold, lost) == (7, 0)
    assert sorted((x.expires, x.qty) for x in lots) == [(2, 3), (3, 5)]
    sold, lost = serve_fifo(lots, 20)
    assert (sold, lost) == (8, 12) and lots == []


def test_serve_fifo_equal_expiry_older_receipt_first():
    lots = [Lot(2, 1, 5), Lot(2, 0, 5)]
    serve_fifo(lots, 3)
    assert [(x.received, x.qty) for x in lots] == [(1, 5), (0, 2)]


def test_discard_expired_on_last_sellable_day():
    lots = [Lot(1, 0, 4), Lot(2, 1, 6)]
    assert discard_expired(lots, 0) == 0
    assert discard_expired(lots, 1) == 4
    assert [x.expires for x in lots] == [2]


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_fifo_accounting_conservation(seed):
    keys, opening, demand, price, promo, rain, dates = _inputs(seed)
    ledger = simulate_policy(RandomPolicy(seed), SKUS, opening, demand, price, promo, rain, dates)
    for key in keys:
        lhs = ledger.opening[key] + ledger.received[key]
        rhs = ledger.sold[key] + ledger.wasted[key] + ledger.closing[key]
        assert lhs == rhs, key
        assert ledger.sold[key] + ledger.lost[key] == ledger.demand[key] == sum(demand[key])
    # a 1-day SKU never carries stock past the window end
    assert all(ledger.closing[(s, "R1")] == 0 for s in STORES)


def test_new_lot_expires_after_shelf_life_days():
    keys, opening, demand, price, promo, rain, dates = _inputs(n=3)
    zero = {k: [0, 0, 0] for k in keys}

    class OnceR2:
        name = "once"

        def order(self, ctx):
            return {("S1", "R2"): 10} if ctx.day == 0 else {}

        def observe(self, *a):
            pass

    ledger = simulate_policy(OnceR2(), SKUS, {}, zero, price, promo, rain, dates)
    # received on day 1, sellable days 1..2, discarded at the end of day 2
    assert ledger.wasted[("S1", "R2")] == 10 and ledger.closing[("S1", "R2")] == 0


def test_round_to_moq_half_up():
    assert round_to_moq(4.9, 10) == 0
    assert round_to_moq(5.0, 10) == 10
    assert round_to_moq(14.9, 10) == 10
    assert round_to_moq(15.0, 10) == 20
    assert round_to_moq(-3, 5) == 0


def test_baseline_orders_mean_of_last_7_sales_rounded_to_moq():
    history = {("S1", "R1"): [1, 2, 3, 4, 5, 6, 7, 8, 9], ("S1", "R2"): [12] * 7, ("S1", "R3"): [2, 3]}
    bl = MeanSalesBaseline(SKUS, history)
    ctx = DayContext(0, D0, {("S1", "R2"): [Lot(2, 0, 50)]})
    orders = bl.order(ctx)
    assert orders[("S1", "R1")] == 5  # mean(3..9) = 6 -> nearest multiple of 5
    assert orders[("S1", "R2")] == 10  # ignores the 50 units on hand
    assert orders[("S1", "R3")] == 0  # mean 2.5 < moq/2 = 3
    bl.observe(1, D0, {("S1", "R1"): 30, ("S1", "R2"): 12, ("S1", "R3"): 2}, None)
    assert bl.mean7(("S1", "R1")) == pytest.approx((4 + 5 + 6 + 7 + 8 + 9 + 30) / 7)
    net = MeanSalesBaseline(SKUS, history, net=True)
    assert net.order(ctx)[("S1", "R2")] == 0
    assert net.name == "baseline_mean7_net" and bl.name == "baseline_mean7"


def test_ledger_metrics_profit_identity():
    keys, opening, demand, price, promo, rain, dates = _inputs(3)
    ledger = simulate_policy(RandomPolicy(3), SKUS, opening, demand, price, promo, rain, dates)
    m = ledger_metrics(ledger, SKUS, 0.5)
    sold_value = sum(ledger.sold[k] * SKUS[k[1]].unit_price for k in keys)
    assert m["revenue_vnd"] == pytest.approx(sold_value)
    # net profit = margin on units sold out of the window's flows minus waste loss (opening at cost)
    expected = sum(
        ledger.sold[k] * (SKUS[k[1]].unit_price - SKUS[k[1]].unit_cost)
        - ledger.wasted[k] * (SKUS[k[1]].unit_cost - SKUS[k[1]].salvage_price)
        for k in keys
    )
    assert m["net_profit_vnd"] == pytest.approx(expected)
    assert m["waste_pct"] == pytest.approx(
        100 * m["wasted_units"] / (m["opening_units"] + m["received_units"])
    )
    assert m["stockout_pct"] == pytest.approx(100 * m["lost_units"] / m["demand_units"])


class StubForecaster:
    def __init__(self):
        self.calls = []
        self.observed = []

    def forecast(self, as_of, store_ids, sku_ids, horizon_days):
        self.calls.append((as_of, horizon_days))
        return [
            ForecastQuantiles(s, k, as_of + dt.timedelta(days=h), 6.0, 12.0, 19.0)
            for s in store_ids
            for k in sku_ids
            for h in range(1, horizon_days + 1)
        ]

    def observe(self, date, sales, extra):
        self.observed.append(date)


ECON = {
    k: SkuEconomics(k, k, s.unit_cost, s.unit_price + 0.5 * (s.unit_price - s.unit_cost), s.salvage_price,
                    s.shelf_life_days, s.moq)
    for k, s in SKUS.items()
}  # fmt: skip


def _fm(plan: str, horizon: str = "h1", seed: int = 7, holding: float = 0.005):
    fc = StubForecaster()
    pol = FreshMeshPolicy(
        f"fm_{plan}", plan=plan, horizon=horizon, economics=ECON, store_ids=STORES, sku_ids=list(SKUS),
        forecaster=fc, seed=seed, n_sims=400, holding_rate=holding,
    )  # fmt: skip
    return pol, fc


def test_freshmesh_policy_plan_order_and_moq():
    ctx = DayContext(0, D0 - dt.timedelta(days=1), {})
    safe, lean, bal = (_fm(p)[0].order(ctx) for p in ("safe", "lean", "balanced"))
    for key in safe:
        assert safe[key] >= bal[key] >= lean[key] >= 0
        assert bal[key] % SKUS[key[1]].moq == 0


def test_freshmesh_policy_uses_stock_and_carry_cost():
    day = D0 - dt.timedelta(days=1)
    empty = _fm("balanced")[0].order(DayContext(0, day, {}))
    stocked = _fm("balanced")[0].order(DayContext(0, day, {("S1", "R3"): [Lot(2, 0, 40)]}))
    assert stocked[("S1", "R3")] < empty[("S1", "R3")]
    carry = _fm("balanced", holding=0.2)[0].order(DayContext(0, day, {}))
    assert carry[("S1", "R2")] <= empty[("S1", "R2")]


def test_freshmesh_policy_hL_requests_longest_shelf_life_horizon():
    pol, fc = _fm("balanced", horizon="hL")
    pol.order(DayContext(0, D0, {}))
    assert fc.calls == [(D0, 3)]


def test_simulation_is_deterministic_for_a_seed():
    keys, opening, demand, price, promo, rain, dates = _inputs(5, n=6)

    def run(seed):
        pol, fc = _fm("balanced", seed=seed)
        ledger = simulate_policy(pol, SKUS, opening, demand, price, promo, rain, dates)
        return ledger, fc

    (a, fca), (b, _) = run(11), run(11)
    assert a == b
    assert fca.observed == dates and fca.calls[0][0] == D0 - dt.timedelta(days=1)


def test_lots_from_rows_drops_expired():
    from decision import StockLot

    rows = [StockLot("S1", "R2", 5, D0), StockLot("S1", "R2", 3, D0 - dt.timedelta(days=1))]
    lots = lots_from_rows(rows, D0 - dt.timedelta(days=1))
    assert [(x.expires, x.qty) for x in lots[("S1", "R2")]] == [(1, 5)]
