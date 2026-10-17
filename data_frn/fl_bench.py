"""Criterion L1 of protocol frn-v1 §5: federated learning with FreshRetailNet cities as clients, K = 18 (the
single full set; the K-subset trend L2 and the Centralized reference are not run: holding every city's data
at once does not fit the shared server). Per seed, 10% of each city's stores (at least 1) are made new: their
history starts 14 days before CAL. Local = the F model of each city (``fit_quantile_model``); FL = FedAvg +
FedPer with the deployed ``FLConfig``. Both scored as F: observed TEST days, h = 1. A city's training rows are
the only data its client keeps between rounds; calibration and evaluation reload the city at the end.
Output: per-store sums by method (``frn_fl_sums.csv``)."""

from __future__ import annotations

import csv
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from data_frn.adapter import SPLIT, city_chain
from data_frn.forecast_bench import STATS, _store_sums
from data_frn.load import city_ids, load_city
from data_frn.protocol import stamp
from data_frn.rows import CityRows
from forecasting.conformal import TARGET_COVERAGE, cqr_offset
from forecasting.features import MAX_HORIZON, ChainData, build_features, target_rows
from forecasting.fl.client import NEW_STORE_DAYS, FLConfig
from forecasting.fl.runtime import run_federated
from forecasting.model import QuantileMLP
from forecasting.service import _predict_scaled, _predict_units, _rows_features, fit_quantile_model

SEEDS = (0, 1)
NEW_SHARE = 0.10
OPEN = SPLIT.train_last + 1 - NEW_STORE_DAYS  # first day of a new store's history
Loader = Callable[[Path, int], CityRows]


def city_data(data_dir: Path, city_id: int, seed: int, load: Loader = load_city):
    """``(cd_recovered, cd_observed, new_store_mask)`` with this seed's new stores applied to both views."""
    rows = load(data_dir, city_id)
    cd_rec, _ = city_chain(rows, "recovered")
    cd_obs, _ = city_chain(rows, "observed")
    n_s = len(cd_rec.store_ids)
    new = np.zeros(n_s, dtype=bool)
    picked = np.random.default_rng([seed, city_id]).choice(n_s, size=max(1, round(NEW_SHARE * n_s)), replace=False)
    new[picked] = True

    def cut(cd: ChainData) -> ChainData:
        units = cd.units.copy()
        units[new, :, :OPEN] = np.nan
        hist = np.where(new, NEW_STORE_DAYS, cd.store_history_days)
        return replace(cd, units=units, store_history_days=hist, _csum=None, _csq=None, _ccnt=None)

    return cut(cd_rec), cut(cd_obs), new


def _test_eval(cd_rec: ChainData, cd_obs: ChainData, new: np.ndarray, predict: Callable) -> list[dict]:
    s, k, o, h = target_rows(cd_rec, SPLIT.test_first, SPLIT.test_last, horizons=np.array([1]))
    seen = ~np.isnan(cd_obs.units[s, k, o + h])
    s, k, o, h = s[seen], k[seen], o[seen], h[seen]
    clim = cd_rec.rain_climatology(SPLIT.cal_last)
    fb = build_features(cd_rec, s, k, o, h, known_rain=False, rain_clim=clim)
    sums = _store_sums(s, len(cd_rec.store_ids), cd_obs.units[s, k, o + h], predict(fb, h))
    return [{"store_idx": i, "new_store": bool(new[i]), **{st: float(sums[st][i]) for st in STATS}}
            for i in range(len(cd_rec.store_ids)) if sums["n"][i] > 0]  # fmt: skip


@dataclass
class FrnClient:
    """One city as a Flower client: training arrays only; calibration/evaluation reload the city."""

    chain_id: str
    city_id: int
    seed: int
    data_dir: Path
    load: Loader
    X: np.ndarray
    sku: np.ndarray
    y: np.ndarray
    feature_mean: np.ndarray
    feature_std: np.ndarray
    store_rows: list[dict] = field(default_factory=list)
    _cds: tuple | None = None

    @property
    def n_train(self) -> int:
        return int(len(self.y))

    def meta(self, cfg: FLConfig) -> dict:
        return {"feature_mean": self.feature_mean, "feature_std": self.feature_std}

    def calibrate(self, model: QuantileMLP, meta: dict) -> tuple[list[float], int]:
        """Split-CQR offset for h = 1 on observed CAL days (as ``fit_quantile_model``; only h = 1 is scored)."""
        cd_rec, cd_obs, _ = self._cds = city_data(self.data_dir, self.city_id, self.seed, self.load)
        s, k, o, h = target_rows(cd_rec, SPLIT.train_last + 1, SPLIT.cal_last, horizons=np.array([1]))
        seen = ~np.isnan(cd_obs.units[s, k, o + h])
        fb = _rows_features(cd_rec, (s[seen], k[seen], o[seen], h[seen]), SPLIT.train_last, known_rain=False)
        q = _predict_scaled(model, meta, fb)
        y = cd_obs.units[s[seen], k[seen], fb.target_idx] / fb.scale
        off = cqr_offset(q[:, 0], q[:, 2], y, alpha=1.0 - TARGET_COVERAGE)
        return [off] * MAX_HORIZON, int(len(y))

    def eval_sums(self, model: QuantileMLP, meta: dict) -> dict[str, float]:
        cd_rec, cd_obs, new = self._cds
        self._cds = None
        self.store_rows = _test_eval(cd_rec, cd_obs, new, lambda fb, h: _predict_units(model, meta, fb, h))
        return {"all.n": float(sum(r["n"] for r in self.store_rows))}


def prepare(data_dir: Path, city_id: int, seed: int, cfg: FLConfig, load: Loader = load_city):
    """Local method + this city's FL client, from one load of the city."""
    cd_rec, cd_obs, new = city_data(data_dir, city_id, seed, load)
    model, meta = fit_quantile_model(cd_rec, train_last=SPLIT.train_last, cal_first=SPLIT.train_last + 1,
                                     cal_last=SPLIT.cal_last, seed=seed, target_cd=cd_obs)  # fmt: skip
    local = _test_eval(cd_rec, cd_obs, new, lambda fb, h: _predict_units(model, meta, fb, h))
    s, k, o, h = target_rows(cd_rec, 1, SPLIT.train_last)
    rng = np.random.default_rng(seed)
    if len(s) > cfg.max_train_rows:
        pick = np.sort(rng.choice(len(s), size=cfg.max_train_rows, replace=False))
        s, k, o, h = s[pick], k[pick], o[pick], h[pick]
    fb = _rows_features(cd_rec, (s, k, o, h), SPLIT.train_last, known_rain=False)
    mu, sd = fb.X.mean(axis=0), fb.X.std(axis=0)
    sd = np.where(sd < 1e-6, 1.0, sd)
    client = FrnClient(f"C{city_id:02d}", city_id, seed, Path(data_dir), load,
                       ((fb.X - mu) / sd).astype(np.float32), fb.sku_bucket, cd_rec.units[s, k, fb.target_idx]
                       / fb.scale, mu, sd)  # fmt: skip
    return local, client


def run(data_dir: Path | str, docs_dir: Path | str, *, seeds=SEEDS, cities: list[int] | None = None,
        cfg: FLConfig | None = None, load: Loader = load_city) -> Path:  # fmt: skip
    data_dir, docs_dir = Path(data_dir), Path(docs_dir)
    cfg = cfg or FLConfig()
    stamp_fields = stamp(docs_dir)
    cities = cities if cities is not None else city_ids(data_dir)
    out: list[dict] = []
    for seed in seeds:
        clients = {}
        for c in cities:
            t0 = time.time()
            local, clients[f"C{c:02d}"] = prepare(data_dir, c, seed, cfg, load)
            out += [{"seed": seed, "city_id": c, "method": "local", **r} for r in local]
            print(f"seed {seed} city {c:2d} prepared in {time.time() - t0:.0f}s", flush=True)
        t0 = time.time()
        run_federated(list(clients), data_dir, config=cfg, seed=seed, clients=clients)
        for c, client in zip(cities, clients.values(), strict=True):
            out += [{"seed": seed, "city_id": c, "method": "fl", **r} for r in client.store_rows]
        print(f"seed {seed} federated in {time.time() - t0:.0f}s", flush=True)
    path = docs_dir / "frn_fl_sums.csv"
    fields = ["protocol", "protocol_sha256", "seed", "city_id", "method", "store_idx", "new_store", *STATS]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in out:
            w.writerow({**stamp_fields, **r})
    return path
