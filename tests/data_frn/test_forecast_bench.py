import numpy as np

import data_frn.forecast_bench as bench
from data_frn.forecast_report import verdicts, write_report
from tests.data_frn.test_adapter import _rows


def test_city_rows_scores_every_method_on_observed_days_only(monkeypatch):
    monkeypatch.setattr(bench, "load_city", lambda data_dir, city_id: _rows(n_stores=3, n_products=4))
    rows = bench.city_rows("unused", 3, "recovered", seed=0)
    assert {r["method"] for r in rows} == set(bench.METHODS)
    assert {r["window"] for r in rows} == {"cal", "test"}
    test = [r for r in rows if r["window"] == "test" and r["method"] == "mlp"]
    # 3 stores × 4 products × 7 TEST days, minus censored days (every 5th day: days 90 and 95)
    assert sum(r["n"] for r in test) == 3 * 4 * 5
    assert all(r["covered"] <= r["n"] and r["abs_err"] >= 0 for r in rows)


def _sums(scale_err):
    rng = np.random.default_rng(0)
    y = rng.uniform(50, 100, 30)

    def method(err):
        return {"n": np.full(30, 7.0), "y": y, "abs_err": err * y, "pinball": 0.3 * err * y, "covered": np.full(30, 5.6)}

    return {
        "cal": {"mlp": method(0.30), "mean7": method(0.45), "seasonal_naive": method(0.40), "empirical_q28": method(0.50)},
        "test": {"mlp": method(scale_err), "mean7": method(0.45), "seasonal_naive": method(0.40), "empirical_q28": method(0.50)},
    }


def test_best_baseline_is_chosen_on_cal_and_verdicts_follow_the_ci():
    good = verdicts(_sums(0.30))
    assert good["best_baseline_on_cal"] == "seasonal_naive"
    assert good["F1"]["pass"] and good["F2"]["pass"] and good["F3"]["pass"]  # coverage 5.6 / 7 = 80%
    bad = verdicts(_sums(0.42))
    assert not bad["F2"]["pass"]  # worse than seasonal naive (0.40)


def test_report_marks_primary_and_exploratory(tmp_path):
    import csv

    path = tmp_path / "sums.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["protocol", "protocol_sha256", "history", "seed", "city_id", "store",
                                           "window", "method", "n", "y", "abs_err", "pinball", "covered"])
        w.writeheader()
        for window in ("cal", "test"):
            for m, e in (("mlp", 0.3), ("mean7", 0.45), ("seasonal_naive", 0.4), ("empirical_q28", 0.5)):
                for s in range(5):
                    w.writerow({"protocol": "frn-v1", "protocol_sha256": "a" * 64, "history": "recovered", "seed": 0,
                                "city_id": 1, "store": f"C01:S{s}", "window": window, "method": m, "n": 7,
                                "y": 70 + s, "abs_err": e * (70 + s), "pinball": 0.3 * e * (70 + s), "covered": 5.6})
    text = write_report({"recovered": path}, tmp_path).read_text(encoding="utf-8")
    assert "F1 ĐẠT" in text and "F2 ĐẠT" in text and "chính / primary" in text
    assert "5 cửa hàng, 35 dòng TEST" in text
