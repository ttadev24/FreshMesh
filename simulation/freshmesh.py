"""FreshMesh ordering policy: rolling ``forecast_demand`` → ``plan_inventory`` (same economics as the API).

The forecaster is injectable (``Forecaster`` protocol) so the policy can be unit-tested with a stub. The real
one, :class:`DbForecaster`, works on a private copy of the chain DB: each evening it appends the day's
*sales* (censored by stock) to ``daily_sales`` and calls ``forecast_demand(..., as_of=that day,
model="local")`` — exactly the production function, on the policy's own history.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import shutil
import sqlite3
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from data_sim import SOURCE, chain_db_path
from decision import Constraints, ForecastQuantiles, StockLot, plan_inventory
from decision.types import SkuEconomics
from forecasting.features import MAX_HORIZON
from forecasting.service import _model_paths, forecast_demand
from simulation.inventory import DayContext, DayExtra, Key, Lot

PLAN_NAMES = ("safe", "balanced", "lean")


class Forecaster(Protocol):
    def forecast(
        self, as_of: dt.date, store_ids: Sequence[str], sku_ids: Sequence[str], horizon_days: int
    ) -> list[ForecastQuantiles]: ...

    def observe(self, date: dt.date, sales: Mapping[Key, int], extra: DayExtra) -> None: ...


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def model_files(data_dir: Path, chain_id: str) -> tuple[Path, Path]:
    return _model_paths(chain_id, data_dir)


def snapshot_inputs(
    src_data_dir: Path, chain_id: str, dest: Path, fresh_sku_ids: Sequence[str]
) -> dict[str, str]:
    """Copy the chain DB (consistent sqlite backup, fresh-SKU sales only) and the local model into ``dest``.

    Returns SHA-256 hashes of the *source* DB snapshot and model weights. Dry-SKU sales rows are dropped from
    the copy only to make ``load_chain`` faster; forecasts of a fresh SKU depend on its own series only.
    """
    dest = Path(dest)
    (dest / "chains").mkdir(parents=True, exist_ok=True)
    (dest / "models").mkdir(parents=True, exist_ok=True)
    src_db = chain_db_path(src_data_dir, chain_id)
    if not src_db.exists():
        raise FileNotFoundError(f"chain database not found: {src_db}")
    out_db = chain_db_path(dest, chain_id)
    src = sqlite3.connect(src_db.resolve().as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(out_db)
    try:
        src.backup(dst)
    finally:
        src.close()
    db_hash = file_sha256(out_db)
    try:
        marks = ",".join("?" * len(fresh_sku_ids))
        with dst:
            dst.execute(f"DELETE FROM daily_sales WHERE sku_id NOT IN ({marks})", tuple(fresh_sku_ids))
        dst.execute("VACUUM")
    finally:
        dst.close()
    hashes = {"db_sha256": db_hash}
    for src_file, dst_file, label in zip(
        model_files(src_data_dir, chain_id),
        model_files(dest, chain_id),
        ("model_sha256", "meta_sha256"),
        strict=True,
    ):
        if not src_file.exists():
            raise FileNotFoundError(
                f"local forecast model {src_file} missing; run `uv run python -m forecasting train` first "
                "(sim30 never trains a model on simulated data)"
            )
        shutil.copyfile(src_file, dst_file)
        hashes[label] = file_sha256(dst_file)
    return hashes


class DbForecaster:
    """``forecast_demand`` on a private copy of a snapshot dir; appends realised sales each evening."""

    def __init__(self, chain_id: str, snapshot_dir: Path, work_dir: Path):
        self.chain_id = chain_id
        self.data_dir = Path(work_dir)
        (self.data_dir / "chains").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "models").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(chain_db_path(snapshot_dir, chain_id), chain_db_path(self.data_dir, chain_id))
        for src, dst in zip(
            model_files(snapshot_dir, chain_id), model_files(self.data_dir, chain_id), strict=True
        ):
            shutil.copyfile(src, dst)

    def forecast(
        self, as_of: dt.date, store_ids: Sequence[str], sku_ids: Sequence[str], horizon_days: int
    ) -> list[ForecastQuantiles]:
        for f in model_files(self.data_dir, self.chain_id):
            if not f.exists():  # forecast_demand would silently retrain on simulated data
                raise FileNotFoundError(f"model artifact {f} missing in the simulation work dir")
        rows = forecast_demand(
            self.chain_id,
            list(store_ids),
            list(sku_ids),
            horizon_days,
            data_dir=self.data_dir,
            as_of=as_of,
            model="local",
        )
        return [ForecastQuantiles(r.store_id, r.sku_id, r.date, r.p10, r.p50, r.p90) for r in rows]

    def observe(self, date: dt.date, sales: Mapping[Key, int], extra: DayExtra) -> None:
        day = date.isoformat()
        con = sqlite3.connect(chain_db_path(self.data_dir, self.chain_id))
        try:
            with con:
                con.executemany(
                    "INSERT OR REPLACE INTO daily_sales VALUES (?,?,?,?,?,?,?,?)",
                    [
                        (
                            s,
                            k,
                            day,
                            int(q),
                            float(extra.price[(s, k)]),
                            int(extra.promo[(s, k)]),
                            float(extra.rain_mm),
                            SOURCE,
                        )
                        for (s, k), q in sorted(sales.items())
                    ],
                )
                con.execute("INSERT OR REPLACE INTO weather VALUES (?, ?)", (day, float(extra.rain_mm)))
        finally:
            con.close()


class FreshMeshPolicy:
    """Each evening: forecast, then ``plan_inventory`` per store; order the lines of plan ``plan``.

    ``horizon="h1"``: one call with ``horizon_days=1`` (production default). ``horizon="hL"``: SKUs grouped
    by shelf life ``L`` (capped at the forecast horizon), one call per group with ``horizon_days=L``.
    ``holding_rate``: ``Constraints.holding_cost_rate_per_day`` (default = the production default).
    """

    def __init__(
        self,
        name: str,
        *,
        plan: str,
        horizon: str,
        economics: Mapping[str, SkuEconomics],
        store_ids: Sequence[str],
        sku_ids: Sequence[str],
        forecaster: Forecaster,
        seed: int,
        n_sims: int = 2000,
        holding_rate: float = 0.005,
    ):
        if plan not in PLAN_NAMES:
            raise ValueError(f"unknown plan {plan!r}")
        if horizon not in ("h1", "hL"):
            raise ValueError(f"unknown horizon mode {horizon!r}")
        self.name = name
        self.plan = plan
        self.horizon = horizon
        self.economics = dict(economics)
        self.store_ids = list(store_ids)
        self.sku_ids = list(sku_ids)
        self.forecaster = forecaster
        self.seed = seed
        self.n_sims = n_sims
        self.constraints = Constraints(
            holding_cost_rate_per_day=holding_rate, fresh_carry_cost_rate_per_day=holding_rate
        )

    def _groups(self) -> list[tuple[int, list[str]]]:
        if self.horizon == "h1":
            return [(1, list(self.sku_ids))]
        by_h: dict[int, list[str]] = defaultdict(list)
        for k in self.sku_ids:
            by_h[min(self.economics[k].shelf_life_days, MAX_HORIZON)].append(k)
        return sorted(by_h.items())

    def order(self, ctx: DayContext) -> dict[Key, int]:
        groups = self._groups()
        rows = self.forecaster.forecast(ctx.date, self.store_ids, self.sku_ids, max(h for h, _ in groups))
        by_store: dict[str, list[ForecastQuantiles]] = defaultdict(list)
        for r in rows:
            by_store[r.store_id].append(r)
        out: dict[Key, int] = {}
        for si, store_id in enumerate(self.store_ids):
            stock = [
                StockLot(store_id, sku_id, lot.qty, ctx.date + dt.timedelta(days=lot.expires - ctx.day))
                for (s, sku_id), lots in ctx.lots.items()
                if s == store_id
                for lot in lots
                if lot.qty > 0
            ]
            for h, group in groups:
                last = ctx.date + dt.timedelta(days=h)
                fq = [r for r in by_store[store_id] if r.sku_id in group and r.date <= last]
                plans = plan_inventory(
                    fq,
                    stock,
                    {k: self.economics[k] for k in group},
                    self.constraints,
                    horizon_days=h,
                    n_sims=self.n_sims,
                    seed=(self.seed * 1000 + ctx.day) * 100 + si,
                )
                chosen = next(p for p in plans if p.name == self.plan)
                for line in chosen.lines:
                    out[(store_id, line.sku_id)] = int(line.qty)
        return out

    def observe(self, day: int, date: dt.date, sales: Mapping[Key, int], extra: DayExtra) -> None:
        self.forecaster.observe(date, sales, extra)


def lots_from_rows(rows: Sequence[StockLot], day0: dt.date) -> dict[Key, list[Lot]]:
    """DB stock lots → simulator lots (day index relative to ``day0``); expired lots are dropped."""
    out: dict[Key, list[Lot]] = defaultdict(list)
    for r in rows:
        expires = (r.expires_on - day0).days
        if expires >= 1 and r.qty > 0:
            out[(r.store_id, r.sku_id)].append(Lot(expires, 0, int(r.qty)))
    return dict(out)
