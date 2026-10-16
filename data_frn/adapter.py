"""One FreshRetailNet city as a ``forecasting.features.ChainData``: a "chain" the FreshMesh forecasting, FL
and inventory code can run on unchanged.

Mapping (FRN → ChainData): store → store, product → SKU, ``1 − discount`` → promo depth, city-mean
``precpt`` → rain, ``holiday_flag`` → is_holiday (lunar flags 0), area type "unknown", category "other" (FRN
category ids carry no names; product identity still reaches the model through the hashed SKU embedding).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from data_frn import N_DAYS, N_EVAL_DAYS, N_TRAIN_DAYS, REVISION, START
from data_frn.censor import daytime_profiles, observed_demand, recovered_demand
from data_frn.rows import CityRows
from forecasting.features import MAX_HORIZON, ChainData

Mode = Literal["observed", "recovered"]
# FRN sale_amount is globally rescaled (median 0.7 per store-product-day). ×10 puts typical series well above
# the forecaster's scale floor of 1 unit; WAPE and mean-normalised pinball do not depend on this choice.
KAPPA = 10.0
MAX_PAIRS = 40_000  # store × product cells per city; above it products are sampled (seeded) to bound memory
CAL_DAYS = 14


@dataclass(frozen=True)
class FrnSplit:
    """Inclusive day indices: TRAIN 0..train_last, CAL ..cal_last (end of train.parquet), TEST = eval."""

    train_last: int = N_TRAIN_DAYS - CAL_DAYS - 1
    cal_last: int = N_TRAIN_DAYS - 1
    test_last: int = N_DAYS - 1

    @property
    def test_first(self) -> int:
        return self.cal_last + 1


SPLIT = FrnSplit()
assert SPLIT.test_last - SPLIT.test_first + 1 == N_EVAL_DAYS


def _sample_products(rows: CityRows, n_stores: int, max_pairs: int, seed: int) -> tuple[np.ndarray, int]:
    products = np.unique(rows.product_id)
    if n_stores * len(products) <= max_pairs:
        return products, len(products)
    k = max(1, max_pairs // n_stores)
    picked = np.random.default_rng(seed).choice(products, size=k, replace=False)
    return np.sort(picked), len(products)


def city_chain(
    rows: CityRows,
    mode: Mode = "observed",
    *,
    kappa: float = KAPPA,
    max_pairs: int = MAX_PAIRS,
    seed: int = 0,
) -> tuple[ChainData, dict[str, Any]]:
    if mode not in ("observed", "recovered"):
        raise ValueError(f"unknown mode {mode!r}")
    stores = np.unique(rows.store_id)
    products, n_products_city = _sample_products(rows, len(stores), max_pairs, seed)
    keep = np.isin(rows.product_id, products)
    s_pos = np.searchsorted(stores, rows.store_id[keep])
    k_pos = np.searchsorted(products, rows.product_id[keep])
    day = rows.day[keep]
    S, K, T = len(stores), len(products), N_DAYS + MAX_HORIZON

    if mode == "observed":
        y = observed_demand(rows.sale[keep], rows.stock_hours[keep])
    else:
        pair = s_pos * K + k_pos
        prof = daytime_profiles(pair, S * K, rows.hours_sale[keep], rows.stock_hours[keep])
        hours, status = rows.hours_sale[keep], rows.hours_status[keep]
        y = recovered_demand(hours, status, rows.stock_hours[keep], prof[pair])

    units = np.full((S, K, T), np.nan)
    units[s_pos, k_pos, day] = kappa * y
    promo = np.zeros((S, K, T))
    promo[s_pos, k_pos, day] = np.clip(1.0 - rows.discount[keep], 0.0, 1.0)

    cnt = np.bincount(rows.day, minlength=T).astype(np.float64)
    rain_sum = np.bincount(rows.day, weights=rows.precpt, minlength=T)
    rain = np.divide(rain_sum, cnt, out=np.full(T, np.nan), where=cnt > 0)
    cal = np.zeros((T, 4))
    np.maximum.at(cal[:, 3], rows.day, rows.holiday.astype(np.float64))
    store_day = np.unique(np.searchsorted(stores, rows.store_id) * T + rows.day)
    store_days = np.bincount(store_day // T, minlength=S).astype(np.int64)

    cd = ChainData(
        chain_id=f"FRN_C{rows.city_id:02d}",
        start=START,
        n_hist=N_DAYS,
        store_ids=[f"S{s}" for s in stores],
        sku_ids=[f"P{p}" for p in products],
        store_area=["unknown"] * S,
        store_history_days=store_days,
        sku_category=["other"] * K,
        sku_is_fresh=np.ones(K),
        units=units,
        promo=promo,
        rain=rain,
        cal=cal,
    )
    meta = {
        "revision": REVISION,
        "city_id": rows.city_id,
        "mode": mode,
        "kappa": kappa,
        "stores": S,
        "products": K,
        "products_in_city": n_products_city,
        "products_sampled": K < n_products_city,
        "rows": int(keep.sum()),
        "unobserved_share": float(np.isnan(y).mean()) if len(y) else 0.0,
    }
    return cd, meta
