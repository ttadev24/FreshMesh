import datetime as dt

import numpy as np

from forecasting.features import MAX_HORIZON, ChainData, target_rows


def _reference(cd, first_target, last_target, horizons=None):
    """The original full S × K grid implementation, kept to prove the pair-based one is identical."""
    hs = np.arange(1, MAX_HORIZON + 1) if horizons is None else np.asarray(horizons)
    S, K = cd.units.shape[:2]
    targets = np.arange(first_target, last_target + 1)
    s, k, t, h = (a.ravel() for a in np.meshgrid(np.arange(S), np.arange(K), targets, hs, indexing="ij"))
    origin = t - h
    keep = origin >= 0
    s, k, origin, h, t = s[keep], k[keep], origin[keep], h[keep], t[keep]
    keep = ~np.isnan(cd.units[s, k, t]) & (cd.history_count(s, k, origin) > 0)
    return s[keep], k[keep], origin[keep], h[keep]


def _chain(seed: int) -> ChainData:
    rng = np.random.default_rng(seed)
    S, K, T = 5, 7, 60
    units = rng.poisson(4.0, size=(S, K, T)).astype(float)
    units[rng.random((S, K, T)) < 0.35] = np.nan  # scattered gaps
    units[1, 2, :] = np.nan  # a pair never observed
    units[3, :, :40] = np.nan  # a store that opens late
    return ChainData(
        chain_id="T", start=dt.date(2026, 1, 1), n_hist=T - MAX_HORIZON, store_ids=[f"S{i}" for i in range(S)],
        sku_ids=[f"K{i}" for i in range(K)], store_area=["residential"] * S, store_history_days=np.full(S, 60),
        sku_category=["vegetable"] * K, sku_is_fresh=np.ones(K), units=units, promo=np.zeros((S, K, T)),
        rain=np.zeros(T), cal=np.zeros((T, 4)),
    )  # fmt: skip


def test_pair_based_target_rows_equal_the_full_grid():
    for seed in range(4):
        cd = _chain(seed)
        for window, hz in (((1, 52), None), ((30, 45), np.array([1])), ((0, 10), np.array([2, 5]))):
            got = target_rows(cd, *window, horizons=hz)
            want = _reference(cd, *window, horizons=hz)
            for a, b in zip(got, want, strict=True):
                assert np.array_equal(a, b)
