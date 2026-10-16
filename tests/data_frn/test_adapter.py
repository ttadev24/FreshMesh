import numpy as np
import pytest

from data_frn import N_DAYS, START
from data_frn.adapter import KAPPA, SPLIT, city_chain
from data_frn.rows import CityRows
from forecasting.features import MAX_HORIZON, build_features, target_rows


def _rows(n_stores=2, n_products=3, stockout_every=5, seed=0) -> CityRows:
    rng = np.random.default_rng(seed)
    s, p, d = (a.ravel() for a in np.meshgrid(np.arange(n_stores) + 100, np.arange(n_products) + 7,
                                                np.arange(N_DAYS), indexing="ij"))  # fmt: skip
    n = len(s)
    hours = np.zeros((n, 24), dtype=np.float32)
    hours[:, 6:22] = rng.uniform(0.0, 0.2, size=(n, 16)).astype(np.float32)
    status = np.zeros((n, 24), dtype=np.int8)
    status[d % stockout_every == 0, 18:22] = 1  # every 5th day: evening stockout
    hours[status == 1] = 0.0
    return CityRows(
        city_id=3, store_id=s, product_id=p, first_category_id=np.zeros(n, dtype=np.int64), day=d,
        sale=hours.sum(axis=1).astype(np.float64), stock_hours=(status[:, 6:22] == 1).sum(axis=1),
        discount=np.where(d % 7 == 0, 0.8, 1.0), activity=np.zeros(n, dtype=np.int64),
        holiday=(d == 35).astype(np.int64), precpt=np.full(n, 2.0), hours_sale=hours, hours_status=status,
    )  # fmt: skip


def test_split_covers_train_cal_and_the_seven_eval_days():
    assert (SPLIT.train_last, SPLIT.cal_last, SPLIT.test_first, SPLIT.test_last) == (75, 89, 90, 96)


@pytest.mark.parametrize("mode", ["observed", "recovered"])
def test_city_chain_builds_a_chain_the_forecaster_can_use(mode):
    rows = _rows()
    cd, meta = city_chain(rows, mode)
    assert cd.chain_id == "FRN_C03" and cd.start == START and cd.n_hist == N_DAYS
    assert cd.units.shape == (2, 3, N_DAYS + MAX_HORIZON)
    assert np.isnan(cd.units[:, :, N_DAYS:]).all()  # forecast horizon appended, unobserved
    censored_day = 10  # 10 % 5 == 0
    if mode == "observed":
        assert np.isnan(cd.units[:, :, censored_day]).all()
    else:
        assert not np.isnan(cd.units[:, :, censored_day]).any()
    clean = rows.day == 11
    assert np.allclose(cd.units[:, :, 11].ravel(), KAPPA * rows.sale[clean])
    assert np.isclose(cd.promo[0, 0, 7], 0.2) and cd.promo[0, 0, 8] == 0.0
    assert cd.cal[35, 3] == 1 and cd.cal[34, 3] == 0 and np.isclose(cd.rain[0], 2.0)
    assert meta["mode"] == mode and not meta["products_sampled"]
    s, k, o, h = target_rows(cd, SPLIT.test_first, SPLIT.test_last)
    assert len(s) > 0
    fb = build_features(cd, s[:50], k[:50], o[:50], h[:50], known_rain=False, rain_clim=cd.rain_climatology(SPLIT.cal_last))
    assert np.isfinite(fb.X).all()


def test_products_are_sampled_reproducibly_above_the_cell_budget():
    rows = _rows(n_stores=2, n_products=6)
    a, meta = city_chain(rows, max_pairs=6, seed=1)
    b, _ = city_chain(rows, max_pairs=6, seed=1)
    assert len(a.sku_ids) == 3 and a.sku_ids == b.sku_ids
    assert meta["products_sampled"] and meta["products_in_city"] == 6


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        city_chain(_rows(), "raw")  # type: ignore[arg-type]
