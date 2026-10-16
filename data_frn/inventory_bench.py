"""Experiment I of protocol frn-v1 (§3): FreshMesh service-target ordering vs naive ordering families on real
FRN demand. Per city: the MLP is fit on days 0–61 and calibrated on 62–75; decisions roll over days 76–96 with
h = 1 forecasts from the true past demand; up to ``SERIES_PER_CITY`` store-product series are simulated.
Output: per-store sums per policy variant (``frn_inventory_sums_L<shelf life>.csv``)."""

from __future__ import annotations

import csv
import datetime as dt
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from data_frn import START
from data_frn.adapter import city_chain
from data_frn.inventory_sim import STATS, simulate_series
from data_frn.load import city_ids, load_city
from data_frn.protocol import stamp
from forecasting.baselines import predict_baseline
from forecasting.features import build_features
from forecasting.service import _predict_units, fit_quantile_model

FIT_LAST, CAL_LAST, SIM_FIRST, SIM_LAST = 61, 75, 76, 96
SERIES_PER_CITY = 200
MIN_HISTORY_DAYS = 14


def _true_demand(cd_rec, cd_sales) -> np.ndarray:
    """Recovered demand on the simulated days, recorded sales where recovery was not possible."""
    rec = cd_rec.units[:, :, SIM_FIRST : SIM_LAST + 1]
    return np.where(np.isnan(rec), cd_sales.units[:, :, SIM_FIRST : SIM_LAST + 1], rec)


def city_rows(data_dir: Path, city_id: int, shelf_life: int, seed: int = 0) -> list[dict]:
    rows = load_city(data_dir, city_id)
    cd_rec, _ = city_chain(rows, "recovered")
    cd_obs, _ = city_chain(rows, "observed")
    cd_sales, _ = city_chain(rows, "sales")
    model, fit = fit_quantile_model(
        cd_rec, train_last=FIT_LAST, cal_first=FIT_LAST + 1, cal_last=CAL_LAST, seed=seed, target_cd=cd_obs
    )
    demand = _true_demand(cd_rec, cd_sales)
    history = (~np.isnan(cd_rec.units[:, :, :SIM_FIRST])).sum(axis=2)
    ok = ~np.isnan(demand).any(axis=2) & (history >= MIN_HISTORY_DAYS)
    pairs = np.argwhere(ok)
    if len(pairs) > SERIES_PER_CITY:
        pick = np.random.default_rng(seed).choice(len(pairs), size=SERIES_PER_CITY, replace=False)
        pairs = pairs[np.sort(pick)]
    n_days = SIM_LAST - SIM_FIRST + 1
    s = np.repeat(pairs[:, 0], n_days)
    k = np.repeat(pairs[:, 1], n_days)
    o = np.tile(np.arange(SIM_FIRST - 1, SIM_LAST), len(pairs))
    h = np.ones_like(o)
    fb = build_features(cd_rec, s, k, o, h, known_rain=False, rain_clim=cd_rec.rain_climatology(CAL_LAST))
    quant = _predict_units(model, fit, fb, h).reshape(len(pairs), n_days, 3)
    point = {b: predict_baseline(b, cd_rec, s, k, o, h)[:, 1].reshape(len(pairs), n_days)
             for b in ("mean7", "seasonal_naive")}  # fmt: skip
    start = START + dt.timedelta(days=SIM_FIRST)
    per_store: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: dict.fromkeys(STATS, 0))
    for j, (si, ki) in enumerate(pairs):
        dem = np.rint(np.maximum(demand[si, ki], 0.0)).astype(int)
        series_point = {b: v[j] for b, v in point.items()}
        res = simulate_series(dem, quant[j], series_point, shelf_life, start, seed=seed)
        store = f"C{city_id:02d}:{cd_rec.store_ids[si]}"
        for variant, tot in res.items():
            acc = per_store[(store, variant)]
            for st in STATS:
                acc[st] += tot[st]
    return [{"city_id": city_id, "store": st, "variant": v, **t} for (st, v), t in per_store.items()]


def run(
    data_dir: Path | str, docs_dir: Path | str, *, shelf_life: int = 2, seed: int = 0,
    cities: list[int] | None = None,
) -> Path:  # fmt: skip
    data_dir, docs_dir = Path(data_dir), Path(docs_dir)
    stamp_fields = stamp(docs_dir)
    out: list[dict] = []
    for c in cities if cities is not None else city_ids(data_dir):
        t0 = time.time()
        out.extend(city_rows(data_dir, c, shelf_life, seed))
        print(f"city {c:2d} done in {time.time() - t0:.0f}s", flush=True)
    path = docs_dir / f"frn_inventory_sums_L{shelf_life}.csv"
    fields = ["protocol", "protocol_sha256", "shelf_life", "seed", "city_id", "store", "variant", *STATS]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in out:
            w.writerow({**stamp_fields, "shelf_life": shelf_life, "seed": seed, **r})
    return path
