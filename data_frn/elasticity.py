"""Exploratory E of protocol frn-v1 §4: price elasticity on FreshRetailNet. Observed (not censored) days;
y = log(units + 1) with units = sale × KAPPA; x = log(discount) (price ratio, 1 = full price); fixed effects
store × product and weekday, by the within transformation (every column is demeaned per series, which is
exact for the series effect; the weekday dummies stay as regressors); OLS per ``first_category_id`` with at
least ``MIN_OBS`` observations; 95% CI by bootstrap over stores (sufficient statistics per store, so a
resample is a sum). Elasticity e as in FreshMesh: sales ∝ (price ratio)^e.

Stated limit: discounts may be endogenous (cut when sales are slow), which biases e towards zero or even
positive values; FreshMesh defaults are not changed from this alone."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from data_frn import START
from data_frn.adapter import KAPPA
from data_frn.bootstrap import N_RESAMPLES, SEED
from data_frn.rows import CityRows

MIN_OBS = 2000
AI_RANGE = (-3.8, -1.3)  # elasticity range of fresh goods proposed by the AI parameter step (data_sim)
K = 7  # log(discount) + 6 weekday dummies (Monday is the reference)

Stats = dict[int, dict[str, tuple[np.ndarray, np.ndarray, int]]]  # category -> store -> (Z'Z, Z'y, n)


def city_stats(rows: CityRows) -> Stats:
    """Per category and store: the within-transformed Z'Z, Z'y and observation count."""
    ok = (rows.stock_hours == 0) & (rows.discount > 0)
    y = np.log1p(KAPPA * rows.sale[ok])
    x = np.log(rows.discount[ok])
    wd = np.array([(START + dt.timedelta(days=int(d))).weekday() for d in range(int(rows.day.max()) + 1)])
    dow = wd[rows.day[ok]]
    Z = np.column_stack([x, *((dow == d).astype(float) for d in range(1, 7))])
    pairs = np.column_stack([rows.store_id[ok], rows.product_id[ok]])
    series = np.unique(pairs, axis=0, return_inverse=True)[1].ravel()
    n_series = int(series.max()) + 1 if len(series) else 0
    count = np.bincount(series, minlength=n_series)
    y = y - (np.bincount(series, y, n_series) / count)[series]
    for j in range(K):
        Z[:, j] -= (np.bincount(series, Z[:, j], n_series) / count)[series]
    cat, store = rows.first_category_id[ok], rows.store_id[ok]
    out: Stats = defaultdict(dict)
    for c in np.unique(cat):
        for s in np.unique(store[cat == c]):
            m = (cat == c) & (store == s)
            out[int(c)][f"C{rows.city_id:02d}:S{int(s)}"] = (Z[m].T @ Z[m], Z[m].T @ y[m], int(m.sum()))
    return dict(out)


def merge(total: Stats, part: Stats) -> None:
    for c, stores in part.items():
        total.setdefault(c, {}).update(stores)


def _beta(xtx: np.ndarray, xty: np.ndarray) -> float:
    try:
        return float(np.linalg.solve(xtx, xty)[0])
    except np.linalg.LinAlgError:
        return float("nan")


def estimates(stats: Stats) -> list[dict[str, Any]]:
    out = []
    rng = np.random.default_rng(SEED)
    for c in sorted(stats):
        stores = list(stats[c].values())
        n = sum(t[2] for t in stores)
        if n < MIN_OBS:
            continue
        xtx = np.stack([t[0] for t in stores])
        xty = np.stack([t[1] for t in stores])
        e = _beta(xtx.sum(axis=0), xty.sum(axis=0))
        idx = rng.integers(0, len(stores), size=(N_RESAMPLES, len(stores)))
        boot = np.array([_beta(xtx[ix].sum(axis=0), xty[ix].sum(axis=0)) for ix in idx])
        boot = boot[~np.isnan(boot)]
        lo, hi = np.percentile(boot, [2.5, 97.5]) if boot.size else (np.nan, np.nan)
        out.append({"category": c, "n": n, "stores": len(stores), "elasticity": e,
                    "ci_low": lo, "ci_high": hi})  # fmt: skip
    return out


def summary(est: list[dict[str, Any]]) -> dict[str, Any]:
    med = float(np.median([r["elasticity"] for r in est])) if est else float("nan")
    inside = AI_RANGE[0] <= med <= AI_RANGE[1]
    return {"median_elasticity": med, "inside_ai_range": inside, "ai_range": list(AI_RANGE),
            "categories": est}  # fmt: skip


def run(data_dir: Path | str, docs_dir: Path | str, cities: list[int] | None = None) -> Path:
    from data_frn.elasticity_report import write_report
    from data_frn.load import city_ids, load_city

    total: Stats = {}
    for c in cities if cities is not None else city_ids(data_dir):
        merge(total, city_stats(load_city(data_dir, c)))
        print(f"city {c:2d} done", flush=True)
    return write_report(summary(estimates(total)), Path(docs_dir))
