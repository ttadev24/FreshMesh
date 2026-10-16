"""Experiment F of protocol frn-v1 (§2): FreshMesh quantile MLP vs naive baselines on real FRN demand.

Per city: history = recovered (primary) or observed (exploratory) demand; the MLP is fit on TRAIN and
conformal-calibrated on observed CAL days; every method forecasts h = 1 rolling over CAL and TEST; only
observed (uncensored) target days are scored. Output: per-store sums (``frn_forecast_sums_<history>.csv``)
from which ``data_frn.forecast_report`` computes pooled metrics, bootstrap CIs and the verdicts.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

import numpy as np

from data_frn.adapter import SPLIT, city_chain
from data_frn.load import city_ids, load_city
from data_frn.protocol import stamp
from forecasting.baselines import BASELINES, predict_baseline
from forecasting.features import build_features, target_rows
from forecasting.model import QUANTILES
from forecasting.service import _predict_units, fit_quantile_model

METHODS = ("mlp", *BASELINES)
STATS = ("n", "y", "abs_err", "pinball", "covered")
WINDOWS = {"cal": (SPLIT.train_last + 1, SPLIT.cal_last), "test": (SPLIT.test_first, SPLIT.test_last)}


def _store_sums(store: np.ndarray, n_stores: int, y: np.ndarray, q: np.ndarray) -> dict[str, np.ndarray]:
    taus = np.asarray(QUANTILES)
    u = y[:, None] - q
    pin = np.maximum(taus * u, (taus - 1.0) * u).mean(axis=1)
    covered = ((y >= q[:, 0]) & (y <= q[:, 2])).astype(np.float64)
    vals = {"n": np.ones_like(y), "y": y, "abs_err": np.abs(y - q[:, 1]), "pinball": pin, "covered": covered}
    return {k: np.bincount(store, weights=v, minlength=n_stores) for k, v in vals.items()}


def city_rows(data_dir: Path, city_id: int, history: str, seed: int) -> list[dict]:
    rows = load_city(data_dir, city_id)
    cd_hist, meta = city_chain(rows, history)  # type: ignore[arg-type]
    cd_obs, _ = city_chain(rows, "observed")
    model, fit = fit_quantile_model(
        cd_hist, train_last=SPLIT.train_last, cal_first=SPLIT.train_last + 1, cal_last=SPLIT.cal_last,
        seed=seed, target_cd=cd_obs,
    )  # fmt: skip
    clim = cd_hist.rain_climatology(SPLIT.cal_last)
    n_stores = len(cd_hist.store_ids)
    out = []
    for window, (first, last) in WINDOWS.items():
        s, k, o, h = target_rows(cd_hist, first, last, horizons=np.array([1]))
        seen = ~np.isnan(cd_obs.units[s, k, o + h])
        s, k, o, h = s[seen], k[seen], o[seen], h[seen]
        y = cd_obs.units[s, k, o + h]
        preds = {name: predict_baseline(name, cd_hist, s, k, o, h) for name in BASELINES}
        fb = build_features(cd_hist, s, k, o, h, known_rain=False, rain_clim=clim)
        preds["mlp"] = _predict_units(model, fit, fb, h)
        for method in METHODS:
            sums = _store_sums(s, n_stores, y, preds[method])
            for i, store in enumerate(cd_hist.store_ids):
                if sums["n"][i] > 0:
                    out.append({
                        "city_id": city_id, "store": f"C{city_id:02d}:{store}", "window": window,
                        "method": method, **{st: float(sums[st][i]) for st in STATS},
                    })  # fmt: skip
    return out


def run(
    data_dir: Path | str, docs_dir: Path | str, *, history: str = "recovered", seed: int = 0,
    cities: list[int] | None = None,
) -> Path:  # fmt: skip
    data_dir, docs_dir = Path(data_dir), Path(docs_dir)
    stamp_fields = stamp(docs_dir)  # refuses to run without the committed protocol
    rows: list[dict] = []
    for c in cities if cities is not None else city_ids(data_dir):
        t0 = time.time()
        rows.extend(city_rows(data_dir, c, history, seed))
        print(f"city {c:2d} done in {time.time() - t0:.0f}s", flush=True)
    path = docs_dir / f"frn_forecast_sums_{history}.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fields = ["protocol", "protocol_sha256", "history", "seed", "city_id", "store", "window", "method"]
        w = csv.DictWriter(fh, fieldnames=[*fields, *STATS], lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({**stamp_fields, "history": history, "seed": seed, **r})
    return path
