import datetime as dt

import numpy as np
import pytest

from forecasting.features import (
    FEATURE_NAMES,
    MAX_HORIZON,
    N_FEATURES,
    build_features,
    calendar_flags,
    load_chain,
    stable_bucket,
    target_rows,
)
from tests.forecasting.conftest import CHAIN, N_DAYS, NEW_STORE_DAYS

F = {name: i for i, name in enumerate(FEATURE_NAMES)}


@pytest.fixture()
def cd(chain_dir):
    return load_chain(CHAIN, chain_dir)


def test_dense_layout(cd):
    assert cd.n_hist == N_DAYS
    assert cd.n_days == N_DAYS + MAX_HORIZON
    new = cd.store_index("T_NEW")
    assert np.isnan(cd.units[new, :, : N_DAYS - NEW_STORE_DAYS]).all()
    assert not np.isnan(cd.units[new, :, N_DAYS - NEW_STORE_DAYS : N_DAYS]).any()
    assert np.isnan(cd.units[:, :, N_DAYS:]).all()


def test_lags_for_horizon_one_are_lag_1_7_14(cd):
    si = cd.store_index("T_S1")
    s, k, o = np.array([si]), np.array([2]), np.array([120])
    fb = build_features(cd, s, k, o, np.array([1]), known_rain=True)
    y = cd.units[si, 2]
    scale = fb.scale[0]
    assert scale == pytest.approx(max(np.mean(y[120 - 27 : 121]), 1.0))
    assert fb.X[0, F["lag_last"]] * scale == pytest.approx(y[120])  # target 121 -> lag 1
    assert fb.X[0, F["lag_sdow1"]] * scale == pytest.approx(y[121 - 7])
    assert fb.X[0, F["lag_sdow2"]] * scale == pytest.approx(y[121 - 14])
    assert fb.X[0, F["roll_mean7"]] * scale == pytest.approx(np.mean(y[114:121]))
    assert fb.X[0, F["roll_std7"]] * scale == pytest.approx(np.std(y[114:121]))


def test_direct_multi_horizon_anchors_on_origin(cd):
    o = 120
    si = cd.store_index("T_S2")
    fb = build_features(
        cd, np.array([si, si]), np.array([0, 0]), np.array([o, o]), np.array([3, 7]), known_rain=True
    )
    y = cd.units[si, 0]
    scale = fb.scale[0]
    np.testing.assert_allclose(fb.X[:, F["lag_last"]] * scale, [y[o], y[o]])
    np.testing.assert_allclose(fb.X[:, F["lag_sdow1"]] * scale, [y[o + 3 - 7], y[o + 7 - 7]])
    np.testing.assert_allclose(fb.X[:, F["horizon"]], [3 / 7, 1.0])
    target_dows = [cd.date_of(o + 3).weekday(), cd.date_of(o + 7).weekday()]
    for row, dow in enumerate(target_dows):
        assert fb.X[row, F[f"dow_{dow}"]] == 1.0


def test_no_leakage_from_days_after_origin(cd):
    origin = 110
    s, k, o, h = target_rows(cd, origin + 1, origin + MAX_HORIZON)
    sel = o == origin
    rows = (s[sel], k[sel], o[sel], h[sel])
    assert len(rows[0]) == 3 * len(cd.sku_ids) * MAX_HORIZON  # the new store has no history yet
    clim = cd.rain_climatology(origin)
    before = build_features(cd, *rows, known_rain=False, rain_clim=clim)
    # Corrupt every observation strictly after the origin (including the targets); features must not move.
    future = cd.units[:, :, origin + 1 :]
    cd.units[:, :, origin + 1 :] = np.where(np.isnan(future), np.nan, 1e6)
    cd._csum = cd._csq = cd._ccnt = None
    after = build_features(cd, *rows, known_rain=False, rain_clim=clim)
    np.testing.assert_array_equal(after.X, before.X)
    np.testing.assert_array_equal(after.scale, before.scale)


def test_short_history_has_no_nan_and_flags_missing(cd):
    new = cd.store_index("T_NEW")
    K = len(cd.sku_ids)
    seen = 9  # origin with only 9 observed days: lag 14 lies before the store opened
    o = cd.n_hist - NEW_STORE_DAYS + seen - 1
    fb = build_features(
        cd,
        np.full(K, new),
        np.arange(K),
        np.full(K, o),
        np.full(K, 1),
        known_rain=False,
        rain_clim=cd.rain_climatology(o),
    )
    assert fb.X.shape == (K, N_FEATURES)
    assert np.isfinite(fb.X).all()
    assert (fb.X[:, F["miss_sdow2"]] == 1.0).all()  # target - 14 is before the store opened
    assert (fb.X[:, F["miss_last"]] == 0.0).all()
    assert fb.X[0, F["hist_frac"]] == pytest.approx(seen / 56)


def test_future_rain_uses_climatology(cd):
    o = cd.n_hist - 1
    clim = cd.rain_climatology(o)
    fb = build_features(
        cd, np.array([0]), np.array([0]), np.array([o]), np.array([1]), known_rain=False, rain_clim=clim
    )
    month = cd.date_of(o + 1).month
    assert fb.X[0, F["rain"]] == pytest.approx(np.log1p(clim[month]))
    assert fb.X[0, F["promo"]] == 0.0  # no planned promotion rows after as_of
    with pytest.raises(ValueError):
        build_features(cd, np.array([0]), np.array([0]), np.array([o]), np.array([1]), known_rain=False)


def test_horizon_bounds(cd):
    with pytest.raises(ValueError):
        build_features(
            cd, np.array([0]), np.array([0]), np.array([50]), np.array([MAX_HORIZON + 1]), known_rain=True
        )


def test_calendar_flags_known_dates():
    assert calendar_flags(dt.date(2026, 2, 17)) == (1, 0, 1, 1)  # Tết Bính Ngọ, mùng 1
    assert calendar_flags(dt.date(2026, 9, 2))[3] == 1  # Quốc khánh
    is_tet, is_ram, is_mung1, _ = calendar_flags(dt.date(2026, 9, 25))  # rằm tháng 8 âm lịch
    assert (is_tet, is_ram, is_mung1) == (0, 1, 0)


def test_stable_bucket_is_deterministic():
    assert stable_bucket("SKU_RAU", 64) == stable_bucket("SKU_RAU", 64)
    assert 0 <= stable_bucket("anything", 8) < 8
