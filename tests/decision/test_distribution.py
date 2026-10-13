import numpy as np
import pytest

from decision.distribution import QuantileDistribution, sample_demand


def test_ppf_passes_through_the_three_quantiles():
    d = QuantileDistribution(20.0, 30.0, 45.0)
    assert d.ppf(0.1) == pytest.approx(20.0)
    assert d.ppf(0.5) == pytest.approx(30.0)
    assert d.ppf(0.9) == pytest.approx(45.0)


def test_ppf_is_monotone_with_exponential_tails():
    d = QuantileDistribution(20.0, 30.0, 45.0)
    u = np.linspace(0.001, 0.999, 999)
    x = d.ppf(u)
    assert np.all(np.diff(x) > 0)
    assert d.ppf(0.99) > 45.0 + 5.0  # tail extends beyond P90
    assert d.ppf(0.01) < 20.0


def test_samples_reproduce_quantiles():
    rng = np.random.default_rng(1)
    x = sample_demand(QuantileDistribution(40.0, 60.0, 90.0), rng, 40_000)
    assert x.dtype.kind == "i"
    q10, q50, q90 = np.quantile(x, [0.1, 0.5, 0.9])
    assert q10 == pytest.approx(40, abs=1.5)
    assert q50 == pytest.approx(60, abs=1.5)
    assert q90 == pytest.approx(90, abs=1.5)


def test_samples_are_clipped_at_zero():
    rng = np.random.default_rng(2)
    x = sample_demand(QuantileDistribution(0.5, 2.0, 6.0), rng, 10_000)
    assert x.min() >= 0
    assert (x == 0).mean() > 0.05


def test_degenerate_quantiles_give_constant_demand():
    rng = np.random.default_rng(3)
    x = sample_demand(QuantileDistribution(7.0, 7.0, 7.0), rng, 100)
    assert np.all(x == 7)


def test_sampling_is_deterministic_with_seed():
    d = QuantileDistribution(5.0, 9.0, 14.0)
    a = sample_demand(d, np.random.default_rng(42), 50)
    b = sample_demand(d, np.random.default_rng(42), 50)
    assert np.array_equal(a, b)


def test_rejects_unordered_quantiles():
    with pytest.raises(ValueError):
        QuantileDistribution(10.0, 5.0, 20.0)
