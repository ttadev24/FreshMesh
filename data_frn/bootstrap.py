"""Paired bootstrap over stores for ratio metrics built from per-store sums (protocol frn-v1: 1 000 resamples,
seed 0). Resampling whole stores keeps each store's rows together, so the CI reflects store-to-store variation."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np

N_RESAMPLES = 1000
SEED = 0

Sums = Mapping[str, np.ndarray]  # name -> (n_stores,) per-store sum


def resample_sums(sums: Sums, n: int = N_RESAMPLES, seed: int = SEED) -> dict[str, np.ndarray]:
    """``{name: (n,) totals}`` over ``n`` resamples of stores with replacement (one index draw shared by all
    names, so differences between methods stay paired)."""
    n_stores = len(next(iter(sums.values())))
    idx = np.random.default_rng(seed).integers(0, n_stores, size=(n, n_stores))
    return {name: np.asarray(v, dtype=np.float64)[idx].sum(axis=1) for name, v in sums.items()}


def paired_ci(
    sums: Sums, metric_diff: Callable[[Mapping[str, np.ndarray]], np.ndarray], *, n: int = N_RESAMPLES,
    seed: int = SEED,
) -> dict[str, float]:  # fmt: skip
    """Point estimate on all stores plus the 95% percentile CI of ``metric_diff`` (a function of totals)."""
    point = float(metric_diff({k: np.asarray([np.sum(v)]) for k, v in sums.items()})[0])
    boot = metric_diff(resample_sums(sums, n, seed))
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"diff": point, "ci_low": float(lo), "ci_high": float(hi)}
