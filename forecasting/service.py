"""Public forecasting service: local training, calibrated forecasts, confidence and drift.

Time split per chain (by target day, ``T`` = number of history days):

* train: targets ``< T - CAL_DAYS - TEST_DAYS``
* calibration: next ``CAL_DAYS`` target days — conformal offsets (one per horizon) are fitted here
* test: last ``TEST_DAYS`` target days — held-out metrics stored in the model ``.json``

The saved model is the one fitted on the train window only, so the conformal guarantee applies to it.
Forecasts read lags up to ``as_of`` (default: last day in the chain DB) and predict ``as_of + 1 .. + h``.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import tempfile
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from agent.template import UNKNOWN_SOURCE_ID, UNKNOWN_SOURCE_VI
from forecasting.confidence import (
    SHORT_HISTORY_DAYS,
    DriftStatus,
    confidence_level,
    drift_status_from_coverage,
    relative_width,
)
from forecasting.conformal import TARGET_COVERAGE, apply_offset, cqr_offset
from forecasting.features import (
    FEATURE_NAMES,
    MAX_HORIZON,
    N_FEATURES,
    N_SKU_BUCKETS,
    ChainData,
    FeatureBatch,
    build_features,
    chain_db_path,
    load_chain,
    target_rows,
)
from forecasting.model import QUANTILES, QuantileMLP
from provenance import label_vi, load_registry, sources_for

# Tables the forecast model reads (provenance of every forecast / model artifact).
FORECAST_TABLES: tuple[str, ...] = ("daily_sales", "calendar", "weather", "stores", "skus")
CAL_DAYS = 28
TEST_DAYS = 28
MIN_TRAIN_DAYS = 28
MODEL_VERSION = 1
FORECAST_MODEL_ENV = "FRESHMESH_FORECAST_MODEL"
FORECAST_MODELS = ("local", "fl")


@dataclass(frozen=True)
class TrainConfig:
    hidden: tuple[int, ...] = (64, 32)
    emb_dim: int = 4
    epochs: int = 12
    batch_size: int = 1024
    lr: float = 2e-3
    weight_decay: float = 1e-3
    max_train_rows: int = 200_000


@dataclass(frozen=True)
class ForecastRow:
    store_id: str
    sku_id: str
    date: dt.date
    p10: float
    p50: float
    p90: float
    confidence: str
    reason: str


@dataclass(frozen=True)
class ModelArtifact:
    chain_id: str
    weights_path: Path
    meta_path: Path
    metrics: dict


# --- metrics -----------------------------------------------------------------------------------------------
def wape(y: np.ndarray, p50: np.ndarray) -> float:
    y = np.asarray(y, dtype=np.float64)
    denom = np.abs(y).sum()
    return float(np.abs(y - np.asarray(p50)).sum() / denom) if denom > 0 else float("nan")


def pinball_loss(y: np.ndarray, q: np.ndarray, quantiles: Sequence[float] = QUANTILES) -> float:
    """Mean pinball loss over rows and the given quantiles; ``q`` has shape ``(n, len(quantiles))``."""
    y = np.asarray(y, dtype=np.float64)
    taus = np.asarray(quantiles)
    u = y[:, None] - np.asarray(q, dtype=np.float64)
    return float(np.maximum(taus * u, (taus - 1.0) * u).mean())


def coverage(y: np.ndarray, p10: np.ndarray, p90: np.ndarray) -> float:
    y = np.asarray(y, dtype=np.float64)
    if len(y) == 0:
        return float("nan")
    return float(np.mean((y >= p10) & (y <= p90)))


def baseline_mean7(cd: ChainData, s_idx: np.ndarray, k_idx: np.ndarray, origin: np.ndarray) -> np.ndarray:
    """Naive baseline, same for every horizon: P50 = mean of the last 7 observed days up to ``origin``;
    P10/P90 = empirical 10%/90% quantiles of the last 28 days. Falls back to P50 when no window data."""
    s_idx, k_idx, origin = (np.asarray(a, dtype=np.int64) for a in (s_idx, k_idx, origin))
    offs = np.arange(-27, 1)
    days = origin[:, None] + offs[None, :]
    valid = days >= 0
    win = np.full(days.shape, np.nan)
    rows = np.broadcast_to(np.arange(len(origin))[:, None], days.shape)
    win[valid] = cd.units[s_idx[rows[valid]], k_idx[rows[valid]], days[valid]]
    last7 = win[:, -7:]
    cnt7 = (~np.isnan(last7)).sum(axis=1)
    cnt28 = (~np.isnan(win)).sum(axis=1)
    sum7 = np.nansum(last7, axis=1)
    sum28 = np.nansum(win, axis=1)
    p50 = np.where(
        cnt7 > 0, sum7 / np.maximum(cnt7, 1), np.where(cnt28 > 0, sum28 / np.maximum(cnt28, 1), 0.0)
    )
    filled = np.where(np.isnan(win), p50[:, None], win)
    any_obs = cnt28 > 0
    p10 = np.where(any_obs, np.quantile(filled, 0.1, axis=1), p50)
    p90 = np.where(any_obs, np.quantile(filled, 0.9, axis=1), p50)
    return np.stack([np.minimum(p10, p50), p50, np.maximum(p90, p50)], axis=1)


# --- model persistence -------------------------------------------------------------------------------------
def resolve_model_kind(model: str | None = None) -> str:
    """``model`` if given, else ``$FRESHMESH_FORECAST_MODEL``, else ``"local"``.

    Must be ``local`` or ``fl``."""
    kind = model or os.environ.get(FORECAST_MODEL_ENV) or "local"
    if kind not in FORECAST_MODELS:
        raise ValueError(f"unknown forecast model {kind!r}; expected one of {FORECAST_MODELS}")
    return kind


def _model_paths(chain_id: str, data_dir: Path, kind: str = "local") -> tuple[Path, Path]:
    base = Path(data_dir) / "models"
    stem = chain_id if kind == "local" else f"{chain_id}.{kind}"
    return base / f"{stem}.npz", base / f"{stem}.json"


def load_model(chain_id: str, data_dir: Path, kind: str = "local") -> tuple[QuantileMLP, dict]:
    weights_path, meta_path = _model_paths(chain_id, data_dir, kind)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    model = QuantileMLP(
        meta["n_features"], meta["n_sku_buckets"], emb_dim=meta["emb_dim"], hidden=tuple(meta["hidden"])
    )
    with np.load(weights_path) as npz:
        model.set_weights([npz[f"w{i}"] for i in range(len(npz.files))])
    return model, meta


class ModelNotReadyError(FileNotFoundError):
    """The chain's forecast model artifact is missing and on-demand training is disabled (API)."""


_TRAIN_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_TRAIN_LOCKS_GUARD = threading.Lock()


def _train_lock(chain_id: str, data_dir: Path) -> threading.Lock:
    key = (str(Path(data_dir).resolve()), chain_id)
    with _TRAIN_LOCKS_GUARD:
        return _TRAIN_LOCKS.setdefault(key, threading.Lock())


def model_ready(chain_id: str, data_dir: Path, kind: str = "local") -> bool:
    weights_path, meta_path = _model_paths(chain_id, Path(data_dir), kind)
    return weights_path.exists() and meta_path.exists()


def _ensure_model(
    chain_id: str, data_dir: Path, kind: str = "local", *, auto_train: bool = True
) -> tuple[QuantileMLP, dict]:
    """Local models are trained on demand when ``auto_train`` (CLI, experiments) — once per chain even under
    concurrent calls; the API passes ``auto_train=False`` and gets :class:`ModelNotReadyError` instead.
    The federated model must come from ``python -m forecasting.fl train`` (it needs every chain)."""
    weights_path, _ = _model_paths(chain_id, data_dir, kind)
    if not model_ready(chain_id, data_dir, kind):
        if kind != "local":
            raise FileNotFoundError(
                f"federated model for {chain_id} not found at {weights_path}; "
                "run `uv run python -m forecasting.fl train` first"
            )
        if not auto_train:
            raise ModelNotReadyError(
                f"local model for {chain_id} not found at {weights_path}; run scripts/bootstrap.sh"
            )
        with _train_lock(chain_id, data_dir):
            if not model_ready(chain_id, data_dir, kind):  # another thread may have trained it meanwhile
                train_local(chain_id, data_dir=data_dir)
    return load_model(chain_id, data_dir, kind)


# --- prediction --------------------------------------------------------------------------------------------
def _predict_scaled(model: QuantileMLP, meta: dict, fb: FeatureBatch) -> np.ndarray:
    mu = np.asarray(meta["feature_mean"])
    sd = np.asarray(meta["feature_std"])
    return model.predict((fb.X - mu) / sd, fb.sku_bucket).astype(np.float64)


def _predict_units(model: QuantileMLP, meta: dict, fb: FeatureBatch, horizon: np.ndarray) -> np.ndarray:
    q = _predict_scaled(model, meta, fb)
    offsets = np.asarray(meta["conformal_offsets"])[np.asarray(horizon) - 1]
    return apply_offset(q, offsets) * fb.scale[:, None]


def _rows_features(
    cd: ChainData, rows: tuple[np.ndarray, ...], upto: int, *, known_rain: bool
) -> FeatureBatch:
    s, k, o, h = rows
    return build_features(cd, s, k, o, h, known_rain=known_rain, rain_clim=cd.rain_climatology(upto))


def _evaluate(
    cd: ChainData, model: QuantileMLP, meta: dict, rows: tuple[np.ndarray, ...], upto: int
) -> dict[str, dict[str, float]]:
    s, k, o, h = rows
    fb = _rows_features(cd, rows, upto, known_rain=False)
    y = cd.units[s, k, fb.target_idx]
    q_model = _predict_units(model, meta, fb, h)
    q_base = baseline_mean7(cd, s, k, o)
    new_store = cd.store_history_days[s] < SHORT_HISTORY_DAYS
    out: dict[str, dict[str, float]] = {}
    for name, mask in (
        ("all", np.ones_like(new_store)),
        ("established", ~new_store),
        ("new_store", new_store),
    ):
        if not mask.any():
            continue
        out[name] = {"n": int(mask.sum())}
        for label, q in (("local", q_model), ("baseline_mean7", q_base)):
            out[name][f"{label}_wape"] = wape(y[mask], q[mask, 1])
            out[name][f"{label}_pinball"] = pinball_loss(y[mask], q[mask])
            out[name][f"{label}_coverage"] = coverage(y[mask], q[mask, 0], q[mask, 2])
    return out


# --- provenance --------------------------------------------------------------------------------------------
def table_sources(con: sqlite3.Connection, tables: Sequence[str]) -> list[str]:
    """Dataset ids behind ``tables`` (``provenance.sources_for``), sorted and unique. A table whose origin
    is not recorded (no row-level ``source`` and no ``data_sources`` entry, or absent) adds ``unknown``:
    provenance is never guessed."""
    ids: set[str] = set()
    for table in tables:
        try:
            found = sources_for(con, [table])
        except ValueError:  # table absent from this DB
            found = []
        ids.update(found or [UNKNOWN_SOURCE_ID])
    return sorted(ids)


def data_sources(chain_id: str, data_dir: Path, tables: Sequence[str] = FORECAST_TABLES) -> list[str]:
    """Dataset ids behind ``tables`` of one chain DB."""
    con = sqlite3.connect(f"file:{chain_db_path(Path(data_dir), chain_id)}?mode=ro", uri=True)
    try:
        return table_sources(con, tables)
    finally:
        con.close()


def source_labels_vi(ids: Sequence[str], data_dir: Path = Path("data")) -> list[str]:
    """Vietnamese labels of dataset ids from the registry of ``data_dir`` (``unknown`` → không rõ nguồn)."""
    reg = load_registry(Path(data_dir))
    return [UNKNOWN_SOURCE_VI if i == UNKNOWN_SOURCE_ID else label_vi(i, reg) for i in ids]


# --- training ----------------------------------------------------------------------------------------------
def train_local(
    chain_id: str, *, data_dir: Path, seed: int = 0, config: TrainConfig | None = None
) -> ModelArtifact:
    """Train the local quantile MLP for one chain, calibrate it, evaluate it and write the artifacts."""
    cfg = config or TrainConfig()
    data_dir = Path(data_dir)
    cd = load_chain(chain_id, data_dir)
    T = cd.n_hist
    test_start = T - TEST_DAYS
    cal_start = test_start - CAL_DAYS
    train_end = cal_start - 1
    if train_end < MIN_TRAIN_DAYS:
        raise ValueError(f"chain {chain_id} has {T} days; need > {CAL_DAYS + TEST_DAYS + MIN_TRAIN_DAYS}")
    rng = np.random.default_rng(seed)

    s, k, o, h = target_rows(cd, 1, train_end)
    if len(s) > cfg.max_train_rows:
        pick = np.sort(rng.choice(len(s), size=cfg.max_train_rows, replace=False))
        s, k, o, h = s[pick], k[pick], o[pick], h[pick]
    fb = _rows_features(cd, (s, k, o, h), train_end, known_rain=False)
    y_scaled = cd.units[s, k, fb.target_idx] / fb.scale
    mu = fb.X.mean(axis=0)
    sd = fb.X.std(axis=0)
    sd = np.where(sd < 1e-6, 1.0, sd)

    model = QuantileMLP(N_FEATURES, N_SKU_BUCKETS, emb_dim=cfg.emb_dim, hidden=cfg.hidden, seed=seed)
    losses = model.fit(
        (fb.X - mu) / sd,
        fb.sku_bucket,
        y_scaled,
        epochs=cfg.epochs,
        batch_size=cfg.batch_size,
        lr=cfg.lr,
        weight_decay=cfg.weight_decay,
        seed=seed,
    )
    meta: dict = {
        "version": MODEL_VERSION,
        "chain_id": chain_id,
        "sources": data_sources(chain_id, data_dir),
        "seed": seed,
        "quantiles": list(QUANTILES),
        "n_features": N_FEATURES,
        "feature_names": list(FEATURE_NAMES),
        "n_sku_buckets": N_SKU_BUCKETS,
        "emb_dim": cfg.emb_dim,
        "hidden": list(cfg.hidden),
        "max_horizon": MAX_HORIZON,
        "feature_mean": mu.tolist(),
        "feature_std": sd.tolist(),
        "train_config": {k_: (list(v) if isinstance(v, tuple) else v) for k_, v in cfg.__dict__.items()},
        "train_loss": [float(x) for x in losses],
        "data_start": cd.start.isoformat(),
        "data_end": cd.last_date.isoformat(),
        "train_targets": [cd.date_of(1).isoformat(), cd.date_of(train_end).isoformat()],
        "cal_targets": [cd.date_of(cal_start).isoformat(), cd.date_of(test_start - 1).isoformat()],
        "test_targets": [cd.date_of(test_start).isoformat(), cd.last_date.isoformat()],
        "n_train_rows": int(len(s)),
    }

    cal_rows = target_rows(cd, cal_start, test_start - 1)
    fb_cal = _rows_features(cd, cal_rows, train_end, known_rain=False)
    q_cal = _predict_scaled(model, meta, fb_cal)
    y_cal = cd.units[cal_rows[0], cal_rows[1], fb_cal.target_idx] / fb_cal.scale
    offsets = []
    for hh in range(1, MAX_HORIZON + 1):
        sel = cal_rows[3] == hh
        offsets.append(cqr_offset(q_cal[sel, 0], q_cal[sel, 2], y_cal[sel], alpha=1.0 - TARGET_COVERAGE))
    meta["conformal_offsets"] = offsets
    meta["conformal"] = {
        "method": "split CQR in scaled space, one offset per horizon",
        "target_coverage": TARGET_COVERAGE,
        "n_cal": int(len(y_cal)),
    }

    test_rows = target_rows(cd, test_start, T - 1)
    meta["metrics"] = _evaluate(cd, model, meta, test_rows, cal_start - 1)

    weights_path, meta_path = _model_paths(chain_id, data_dir)
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    # Write both artifacts to temp files in the same directory, then swap them in with os.replace (weights
    # first, meta last) so a reader never sees a half-written file and a failure leaves the old pair intact.
    fd_w, tmp_w = tempfile.mkstemp(prefix=f".{chain_id}.", suffix=".npz", dir=weights_path.parent)
    fd_m, tmp_m = tempfile.mkstemp(prefix=f".{chain_id}.", suffix=".json", dir=weights_path.parent)
    try:
        with os.fdopen(fd_w, "wb") as f:
            np.savez(f, **{f"w{i}": w for i, w in enumerate(model.get_weights())})
        with os.fdopen(fd_m, "w", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False, indent=2))
        os.replace(tmp_w, weights_path)
        os.replace(tmp_m, meta_path)
    finally:
        for tmp in (tmp_w, tmp_m):
            if os.path.exists(tmp):
                os.unlink(tmp)
    return ModelArtifact(chain_id, weights_path, meta_path, meta["metrics"])


# --- forecasting -------------------------------------------------------------------------------------------
def _origin_index(cd: ChainData, as_of: dt.date | None) -> int:
    origin = cd.n_hist - 1 if as_of is None else cd.index_of(as_of)
    if not 0 <= origin < cd.n_hist:
        raise ValueError(f"as_of {as_of} outside data range {cd.start}..{cd.last_date}")
    return origin


def _store_coverage_7d(
    cd: ChainData, model: QuantileMLP, meta: dict, s: int, origin: int
) -> tuple[float | None, int]:
    """Realised coverage of calibrated 1-day-ahead P10–P90 over the 7 days ending at ``origin``."""
    targets = np.arange(max(origin - 6, 1), origin + 1)
    K = len(cd.sku_ids)
    tt = np.repeat(targets, K)
    kk = np.tile(np.arange(K), len(targets))
    ss = np.full_like(kk, s)
    oo = tt - 1
    keep = ~np.isnan(cd.units[ss, kk, tt]) & (cd.history_count(ss, kk, oo) > 0)
    if not keep.any():
        return None, 0
    rows = (ss[keep], kk[keep], oo[keep], np.ones(int(keep.sum()), dtype=np.int64))
    fb = _rows_features(cd, rows, origin, known_rain=False)
    q = _predict_units(model, meta, fb, rows[3])
    y = cd.units[rows[0], rows[1], fb.target_idx]
    return coverage(y, q[:, 0], q[:, 2]), int(len(y))


def forecast_demand(
    chain_id: str,
    store_ids: Sequence[str],
    sku_ids: Sequence[str],
    horizon_days: int,
    *,
    data_dir: Path = Path("data"),
    as_of: dt.date | None = None,
    model: str | None = None,
    auto_train: bool = True,
) -> list[ForecastRow]:
    """Calibrated P10/P50/P90 for each store × SKU × day in ``as_of + 1 .. as_of + horizon_days``.

    ``model``: ``"local"`` (default) or ``"fl"`` (federated FedAvg+FedPer artifact ``<chain>.fl.npz``); when
    ``None`` the ``FRESHMESH_FORECAST_MODEL`` environment variable decides. Trains the chain's local model
    first if no local artifact exists in ``data_dir/models`` (``auto_train=False``: raise
    :class:`ModelNotReadyError` instead, as the API does).
    """
    if not 1 <= horizon_days <= MAX_HORIZON:
        raise ValueError(f"horizon_days must be within 1..{MAX_HORIZON}")
    kind = resolve_model_kind(model)
    data_dir = Path(data_dir)
    cd = load_chain(chain_id, data_dir)
    net, meta = _ensure_model(chain_id, data_dir, kind, auto_train=auto_train)
    origin = _origin_index(cd, as_of)
    s_list = [cd.store_index(x) for x in store_ids]
    k_list = [cd.sku_index(x) for x in sku_ids]
    if not s_list or not k_list:
        return []

    grid = np.meshgrid(s_list, k_list, np.arange(1, horizon_days + 1), indexing="ij")
    s, k, h = (g.ravel() for g in grid)
    o = np.full_like(s, origin)
    fb = _rows_features(cd, (s, k, o, h), origin, known_rain=False)
    q = _predict_units(net, meta, fb, h)

    hist_counts = cd.history_count(s, k, o)
    store_hist = {si: int(hist_counts[s == si].max()) for si in s_list}
    store_cov = {si: _store_coverage_7d(cd, net, meta, si, origin)[0] for si in s_list}

    rows: list[ForecastRow] = []
    for i in range(len(s)):
        p10, p50, p90 = (round(float(v), 2) for v in q[i])
        level, reason = confidence_level(relative_width(p10, p50, p90), store_hist[s[i]], store_cov[s[i]])
        rows.append(
            ForecastRow(
                store_id=cd.store_ids[s[i]],
                sku_id=cd.sku_ids[k[i]],
                date=cd.date_of(int(fb.target_idx[i])),
                p10=p10,
                p50=p50,
                p90=p90,
                confidence=level,
                reason=reason,
            )
        )
    return rows


def drift_status(
    chain_id: str,
    store_id: str,
    *,
    data_dir: Path = Path("data"),
    as_of: dt.date | None = None,
    model: str | None = None,
    auto_train: bool = True,
) -> DriftStatus:
    """Realised 7-day P10–P90 coverage for a store; alert (suggest the "An toàn" plan) when below 70%.

    ``model`` selects the forecast model as in ``forecast_demand``."""
    data_dir = Path(data_dir)
    cd = load_chain(chain_id, data_dir)
    net, meta = _ensure_model(chain_id, data_dir, resolve_model_kind(model), auto_train=auto_train)
    cov, n = _store_coverage_7d(cd, net, meta, cd.store_index(store_id), _origin_index(cd, as_of))
    return drift_status_from_coverage(chain_id, store_id, cov, n)
