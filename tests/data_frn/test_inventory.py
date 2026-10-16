import datetime as dt

import numpy as np

from data_frn.inventory_report import verdict, write_report
from data_frn.inventory_sim import VARIANTS, WARMUP_DAYS, simulate_series

START = dt.date(2024, 6, 11)
N = 12


def _run(shelf_life, demand=10, quant=(9.0, 10.0, 11.0)):
    dem = np.full(N, demand)
    q = np.tile(np.array(quant), (N, 1))
    point = {"mean7": np.full(N, float(demand)), "seasonal_naive": np.full(N, float(demand))}
    return simulate_series(dem, q, point, shelf_life, START, seed=0)


def test_exact_baseline_orders_neither_waste_nor_stock_out():
    t = _run(2)["mean7:1:gross"]
    assert t == {"opening": 0, "received": 10 * (N - WARMUP_DAYS), "wasted": 0, "lost": 0, "demand": 10 * (N - WARMUP_DAYS)}


def test_over_ordering_wastes_the_excess_with_one_day_shelf_life():
    t = _run(1)["mean7:1.5:gross"]
    assert t["wasted"] == 5 * (N - WARMUP_DAYS) and t["lost"] == 0


def test_net_ordering_counts_stock_on_hand():
    gross, net = _run(2)["seasonal_naive:1.5:gross"], _run(2)["seasonal_naive:1.5:net"]
    assert net["received"] < gross["received"] and net["wasted"] < gross["wasted"]


def test_freshmesh_service_target_trades_waste_for_stockout():
    res = _run(2, quant=(6.0, 10.0, 14.0))
    lo, hi = res["freshmesh:0.5:gross"], res["freshmesh:0.98:gross"]
    assert hi["lost"] < lo["lost"] and hi["wasted"] >= lo["wasted"]  # more service costs more waste
    assert len(res) == len(VARIANTS)


def _sums(fm_waste_scale):
    rng = np.random.default_rng(0)
    n = 40
    demand = rng.uniform(100, 200, n)
    sums = {}
    for v in VARIANTS:
        if v.family == "freshmesh":
            so = (1 - v.param) * 40  # 20% … 0,8% stockout: spans the 5/10/15% levels with margin
            waste = fm_waste_scale * (v.param * 12)
        else:
            so = max(0.0, (1.6 - v.param) * 25)
            waste = v.param * 14
        sums[v.key] = {"opening": np.zeros(n), "received": demand, "wasted": demand * waste / 100,
                       "lost": demand * so / 100, "demand": demand}  # fmt: skip
    return sums


def test_i1_passes_only_when_the_freshmesh_frontier_is_lower_at_all_levels(tmp_path):
    assert verdict(_sums(0.5))["pass"]
    assert not verdict(_sums(3.0))["pass"]  # at 5% stockout FreshMesh would waste 31,5% vs the baseline's 19,6%


def test_report_writes_the_primary_verdict_and_chart(tmp_path):
    import csv

    path = tmp_path / "sums.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["protocol", "protocol_sha256", "shelf_life", "seed", "city_id", "store",
                                           "variant", "opening", "received", "wasted", "lost", "demand"])
        w.writeheader()
        for key, s in _sums(0.5).items():
            for i in range(len(s["demand"])):
                w.writerow({"protocol": "frn-v1", "protocol_sha256": "b" * 64, "shelf_life": 2, "seed": 0,
                            "city_id": 1, "store": f"C01:S{i}", "variant": key,
                            **{st: s[st][i] for st in ("opening", "received", "wasted", "lost", "demand")}})
    text = write_report({2: path}, tmp_path).read_text(encoding="utf-8")
    assert "I1 ĐẠT" in text and (tmp_path / "frn_inventory_frontier.svg").exists()
