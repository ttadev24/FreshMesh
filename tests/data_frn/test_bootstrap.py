import numpy as np

from data_frn.bootstrap import paired_ci, resample_sums


def _wape_diff(t):
    return t["abs_a"] / t["y"] - t["abs_b"] / t["y"]


def test_point_estimate_is_the_pooled_metric_and_ci_brackets_it():
    rng = np.random.default_rng(1)
    y = rng.uniform(50, 150, size=40)
    sums = {"y": y, "abs_a": 0.30 * y + rng.normal(0, 2, 40), "abs_b": 0.40 * y + rng.normal(0, 2, 40)}
    out = paired_ci(sums, _wape_diff)
    pooled = sums["abs_a"].sum() / y.sum() - sums["abs_b"].sum() / y.sum()
    assert np.isclose(out["diff"], pooled)
    assert out["ci_low"] < out["diff"] < out["ci_high"] < 0  # A clearly better than B


def test_resamples_are_paired_and_reproducible():
    sums = {"a": np.arange(10.0), "b": np.arange(10.0)}
    r1, r2 = resample_sums(sums, n=50, seed=3), resample_sums(sums, n=50, seed=3)
    assert np.array_equal(r1["a"], r2["a"]) and np.array_equal(r1["a"], r1["b"])
