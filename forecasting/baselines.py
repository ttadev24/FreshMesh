"""Naive forecast baselines of the pre-registered FRN protocol (``docs/experiments/frn-protocol.md`` §2).

Each returns ``(n, 3)`` P10/P50/P90 for rows ``(store, sku, origin, horizon)`` from history up to ``origin``
only (no peeking). Point baselines repeat their P50 in all three columns.
"""

from __future__ import annotations

import numpy as np

from forecasting.features import ChainData
from forecasting.service import baseline_mean7


def _window(cd: ChainData, s: np.ndarray, k: np.ndarray, origin: np.ndarray, width: int) -> np.ndarray:
    """(n, width) history ending at ``origin`` (NaN before day 0 and where unobserved)."""
    days = origin[:, None] + np.arange(1 - width, 1)[None, :]
    out = np.full(days.shape, np.nan)
    ok = days >= 0
    rows = np.broadcast_to(np.arange(len(origin))[:, None], days.shape)
    out[ok] = cd.units[s[rows[ok]], k[rows[ok]], days[ok]]
    return out


def mean7(cd: ChainData, s: np.ndarray, k: np.ndarray, origin: np.ndarray) -> np.ndarray:
    p50 = baseline_mean7(cd, s, k, origin)[:, 1]
    return np.repeat(p50[:, None], 3, axis=1)


def seasonal_naive(cd: ChainData, s: np.ndarray, k: np.ndarray, origin: np.ndarray, horizon: np.ndarray):
    """P50 = the same weekday one week before the target (``target − 7k``, the latest such day ≤ origin);
    falls back to ``mean7`` when that day is unobserved."""
    s, k, origin, horizon = (np.asarray(a, dtype=np.int64) for a in (s, k, origin, horizon))
    target = origin + horizon
    lag_day = target - 7 * ((horizon + 6) // 7)
    vals = np.full(len(s), np.nan)
    ok = lag_day >= 0
    vals[ok] = cd.units[s[ok], k[ok], lag_day[ok]]
    p50 = np.where(np.isnan(vals), mean7(cd, s, k, origin)[:, 1], vals)
    return np.repeat(p50[:, None], 3, axis=1)


def empirical_q28(cd: ChainData, s: np.ndarray, k: np.ndarray, origin: np.ndarray) -> np.ndarray:
    """P10/P50/P90 = empirical quantiles of the observed days among the last 28 (``mean7`` if none)."""
    s, k, origin = (np.asarray(a, dtype=np.int64) for a in (s, k, origin))
    win = _window(cd, s, k, origin, 28)
    out = mean7(cd, s, k, origin)
    seen = (~np.isnan(win)).any(axis=1)
    if seen.any():
        out[seen] = np.nanquantile(win[seen], [0.1, 0.5, 0.9], axis=1).T
    return out


BASELINES = ("mean7", "seasonal_naive", "empirical_q28")


def predict_baseline(name: str, cd: ChainData, s, k, origin, horizon) -> np.ndarray:
    if name == "mean7":
        return mean7(cd, s, k, origin)
    if name == "seasonal_naive":
        return seasonal_naive(cd, s, k, origin, horizon)
    if name == "empirical_q28":
        return empirical_q28(cd, s, k, origin)
    raise ValueError(f"unknown baseline {name!r}")
