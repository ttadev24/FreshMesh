import numpy as np
import pytest

from forecasting.conformal import apply_offset, cqr_offset, interval_coverage


def _hetero(rng, n):
    x = rng.uniform(0, 3, size=n)
    sigma = 0.3 + x
    y = 2 * x + sigma * rng.standard_t(df=5, size=n)
    return x, sigma, y


@pytest.mark.parametrize("width_factor", [0.4, 1.0, 2.5])  # too narrow, roughly right, too wide
def test_cqr_reaches_80pct_coverage_on_synthetic_data(width_factor):
    rng = np.random.default_rng(11)
    z = 1.2816 * width_factor
    x_cal, s_cal, y_cal = _hetero(rng, 2000)
    q = cqr_offset(2 * x_cal - z * s_cal, 2 * x_cal + z * s_cal, y_cal, alpha=0.2)
    covs = []
    for rep in range(5):
        x_t, s_t, y_t = _hetero(np.random.default_rng(100 + rep), 4000)
        covs.append(interval_coverage(2 * x_t - z * s_t - q, 2 * x_t + z * s_t + q, y_t))
    assert abs(np.mean(covs) - 0.8) < 0.05
    raw_cov = interval_coverage(2 * x_t - z * s_t, 2 * x_t + z * s_t, y_t)
    if width_factor < 1:
        assert q > 0 and raw_cov < 0.7
    if width_factor > 2:
        assert q < 0 and raw_cov > 0.9


def test_offset_finite_when_calibration_too_small():
    """OPEN (b): a tiny calibration set gives the largest observed score (conservative), never inf, so the
    offsets stay JSON-safe (model meta, API responses)."""
    import json

    q = cqr_offset(np.zeros(3), np.ones(3), np.array([0.5, 2.0, -1.0]), alpha=0.2)
    assert q == 1.0
    json.dumps({"q": q}, allow_nan=False)
    with pytest.raises(ValueError):
        cqr_offset(np.array([]), np.array([]), np.array([]))


def test_negative_offset_shrinks_without_moving_p50():
    """OPEN (b): shrinking stops at P50; P50 itself only changes when clamped at 0."""
    q = np.array([[1.0, 1.1, 1.2], [8.0, 10.0, 12.0], [2.0, 9.0, 10.0]])
    out = apply_offset(q, -3.0)
    np.testing.assert_allclose(out[:, 1], q[:, 1])
    np.testing.assert_allclose(out, [[1.1, 1.1, 1.1], [10.0, 10.0, 10.0], [5.0, 9.0, 9.0]])
    assert np.all(np.diff(out, axis=1) >= 0)
    neg = apply_offset(np.array([[-2.0, -1.0, 0.5]]), 0.0)
    np.testing.assert_allclose(neg, [[0.0, 0.0, 0.5]])


def test_apply_offset_rejects_non_finite_offsets():
    with pytest.raises(ValueError):
        apply_offset(np.array([[1.0, 2.0, 3.0]]), np.inf)


def test_apply_offset_clamps_and_keeps_order():
    q = np.array([[0.2, 1.0, 2.0], [5.0, 6.0, 7.0], [1.0, 1.1, 1.2]])
    out = apply_offset(q, np.array([0.5, -0.5, -1.0]))
    np.testing.assert_allclose(out[0], [0.0, 1.0, 2.5])
    np.testing.assert_allclose(out[1], [5.5, 6.0, 6.5])
    np.testing.assert_allclose(out[2], [1.1, 1.1, 1.1])  # shrink stops at P50 (P50 not moved)
    assert np.all(out >= 0)
    assert np.all(np.diff(out, axis=1) >= 0)
