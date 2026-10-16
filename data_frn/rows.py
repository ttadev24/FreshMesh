"""Numpy view of one FreshRetailNet city (no pyarrow needed, so adapters and tests can build it directly)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CityRows:
    """One row per store-product-day of a city (train + eval days)."""

    city_id: int
    store_id: np.ndarray  # (n,) int64
    product_id: np.ndarray  # (n,) int64
    first_category_id: np.ndarray  # (n,) int64
    day: np.ndarray  # (n,) int64 day index from data_frn.START (eval days follow train days)
    sale: np.ndarray  # (n,) float64, rescaled units as published
    stock_hours: np.ndarray  # (n,) int64 out-of-stock hours within data_frn.DAY_HOURS
    discount: np.ndarray  # (n,) float64, 1.0 = no discount
    activity: np.ndarray  # (n,) int64
    holiday: np.ndarray  # (n,) int64
    precpt: np.ndarray  # (n,) float64
    hours_sale: np.ndarray  # (n, 24) float32
    hours_status: np.ndarray  # (n, 24) int8

    @property
    def n(self) -> int:
        return len(self.sale)
