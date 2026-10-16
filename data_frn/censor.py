"""Sales observed under stockouts understate demand (44% of FRN store-product-days have at least one
out-of-stock hour within 6–21h). Two treatments, both pure numpy:

* ``observed``  — a day with any out-of-stock hour in the daytime window is not an observation (NaN). Used to
  *evaluate* forecasts: errors are measured only on days whose sales equal demand.
* ``recovered`` — daytime demand = daytime sales / share of the series' usual daytime sales that falls in
  in-stock hours (its hourly profile on fully in-stock days; pooled profile when it has fewer than
  ``MIN_CLEAN_DAYS``); night sales are kept as recorded. A share below ``MIN_SHARE`` gives NaN (too little
  in-stock time to infer the day). Used as the "true demand" of inventory simulations.
"""

from __future__ import annotations

import numpy as np

from data_frn import DAY_HOURS, OUT_OF_STOCK

MIN_CLEAN_DAYS = 3
MIN_SHARE = 0.2


def observed_demand(sale: np.ndarray, stock_hours: np.ndarray) -> np.ndarray:
    return np.where(stock_hours > 0, np.nan, sale)


def daytime_profiles(
    series: np.ndarray, n_series: int, hours_sale: np.ndarray, stock_hours: np.ndarray
) -> np.ndarray:
    """(n_series, n_day_hours) share of each series' daytime sales by hour, from its fully in-stock days."""
    day = hours_sale[:, DAY_HOURS].astype(np.float64)
    clean = stock_hours == 0
    sums = np.zeros((n_series, day.shape[1]))
    np.add.at(sums, series[clean], day[clean])
    clean_days = np.bincount(series[clean], minlength=n_series)
    pooled = day[clean].sum(axis=0)
    pooled = pooled / pooled.sum() if pooled.sum() > 0 else np.full(day.shape[1], 1.0 / day.shape[1])
    totals = sums.sum(axis=1, keepdims=True)
    ok = (clean_days >= MIN_CLEAN_DAYS) & (totals[:, 0] > 0)
    out = np.tile(pooled, (n_series, 1))
    out[ok] = sums[ok] / totals[ok]
    return out


def instock_share(profile_rows: np.ndarray, hours_status: np.ndarray) -> np.ndarray:
    """Share of the usual daytime sales that falls in the day's in-stock hours (1.0 when fully stocked)."""
    in_stock = hours_status[:, DAY_HOURS] != OUT_OF_STOCK
    return (profile_rows * in_stock).sum(axis=1)


def recovered_demand(
    hours_sale: np.ndarray, hours_status: np.ndarray, stock_hours: np.ndarray, profile_rows: np.ndarray
) -> np.ndarray:
    total = hours_sale.astype(np.float64).sum(axis=1)
    daytime = hours_sale[:, DAY_HOURS].astype(np.float64).sum(axis=1)
    share = instock_share(profile_rows, hours_status)
    est = total - daytime + np.divide(daytime, share, out=np.full_like(daytime, np.nan), where=share > 0)
    est = np.where(stock_hours == 0, total, est)  # fully stocked: sales are demand
    return np.where((stock_hours > 0) & (share < MIN_SHARE), np.nan, est)
