import numpy as np

from data_frn.adapter import KAPPA
from data_frn.elasticity import city_stats, estimates, summary
from data_frn.elasticity_report import write_report
from data_frn.rows import CityRows


def _rows(e_true: float, n_stores: int = 30, n_products: int = 20, days: int = 60, seed: int = 0) -> CityRows:
    rng = np.random.default_rng(seed)
    s, p, d = (a.ravel() for a in np.meshgrid(np.arange(n_stores), np.arange(n_products), np.arange(days),
                                               indexing="ij"))  # fmt: skip
    n = len(s)
    level = rng.normal(1.5, 0.5, (n_stores, n_products))[s, p]  # series fixed effect
    weekday = np.array([0.0, 0.0, 0.0, 0.0, 0.1, 0.3, 0.4])[(d + 3) % 7]  # START is a Thursday
    discount = np.where(rng.random(n) < 0.3, rng.choice([0.7, 0.8, 0.9], n), 1.0)
    y = level + weekday + e_true * np.log(discount) + rng.normal(0, 0.1, n)
    sale = (np.exp(y) - 1) / KAPPA
    zeros = np.zeros(n, dtype=np.int64)
    return CityRows(1, s, p, zeros + 5, d, sale, zeros, discount, zeros, zeros, np.zeros(n),
                    np.zeros((n, 24), np.float32), np.zeros((n, 24), np.int8))  # fmt: skip


def test_within_estimator_recovers_a_known_elasticity_with_fixed_effects():
    est = estimates(city_stats(_rows(-2.0)))
    assert len(est) == 1 and abs(est[0]["elasticity"] + 2.0) < 0.05
    assert est[0]["ci_low"] < -2.0 < est[0]["ci_high"] or abs(est[0]["ci_high"] - est[0]["ci_low"]) < 0.1


def test_report_says_whether_the_median_is_inside_the_ai_range(tmp_path):
    out = summary(estimates(city_stats(_rows(-2.0))))
    assert out["inside_ai_range"]
    text = write_report(out, tmp_path).read_text(encoding="utf-8")
    assert "nằm trong" in text and (tmp_path / "frn_elasticity_summary.json").exists()
    weak = summary(estimates(city_stats(_rows(-0.4))))
    assert not weak["inside_ai_range"]
