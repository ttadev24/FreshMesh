import datetime as dt

import numpy as np
import pytest

from forecasting.baselines import empirical_q28, mean7, predict_baseline, seasonal_naive
from forecasting.features import MAX_HORIZON, ChainData


def _cd(series: list[float]) -> ChainData:
    T = len(series) + MAX_HORIZON
    units = np.full((1, 1, T), np.nan)
    units[0, 0, : len(series)] = series
    return ChainData(
        chain_id="T", start=dt.date(2026, 1, 5), n_hist=len(series), store_ids=["S"], sku_ids=["K"],
        store_area=["residential"], store_history_days=np.array([len(series)]), sku_category=["vegetable"],
        sku_is_fresh=np.ones(1), units=units, promo=np.zeros((1, 1, T)), rain=np.zeros(T), cal=np.zeros((T, 4)),
    )  # fmt: skip


Z = np.array([0])


def test_mean7_uses_the_last_seven_days_only():
    cd = _cd([100.0] * 7 + list(range(1, 8)))  # last 7 days 1..7
    assert mean7(cd, Z, Z, np.array([13]))[0].tolist() == [4.0, 4.0, 4.0]


def test_seasonal_naive_reads_the_same_weekday_and_falls_back_when_missing():
    series = [float(d) for d in range(14)]
    cd = _cd(series)
    # origin 13, horizon 1 → target 14 → same weekday a week earlier = day 7
    assert seasonal_naive(cd, Z, Z, np.array([13]), np.array([1]))[0, 1] == 7.0
    # horizon 7 → target 20 → day 13 (the latest same weekday ≤ origin)
    assert seasonal_naive(cd, Z, Z, np.array([13]), np.array([7]))[0, 1] == 13.0
    cd.units[0, 0, 7] = np.nan
    assert seasonal_naive(cd, Z, Z, np.array([13]), np.array([1]))[0, 1] == mean7(cd, Z, Z, np.array([13]))[0, 1]


def test_empirical_q28_gives_ordered_quantiles_of_the_window():
    cd = _cd([float(x) for x in range(40)])
    q = empirical_q28(cd, Z, Z, np.array([39]))[0]  # window = days 12..39
    assert q.tolist() == pytest.approx(np.quantile(np.arange(12, 40), [0.1, 0.5, 0.9]).tolist())
    assert q[0] <= q[1] <= q[2]


def test_baselines_never_read_after_the_origin():
    cd = _cd([1.0] * 20)
    cd.units[0, 0, 20:] = 1e6  # "future" values must not leak
    for name in ("mean7", "seasonal_naive", "empirical_q28"):
        assert predict_baseline(name, cd, Z, Z, np.array([19]), np.array([1]))[0].max() == 1.0
    with pytest.raises(ValueError):
        predict_baseline("oracle", cd, Z, Z, np.array([19]), np.array([1]))
