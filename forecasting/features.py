"""Chain data loading and leakage-free feature construction for demand forecasting.

Design (documented here because the rest of the package relies on it):

* **Dense layout.** ``daily_sales`` is pivoted to ``units[store, sku, day]`` with ``NaN`` for days without a
  row (e.g. before a new store opened). Lag/rolling features are array lookups, so a feature for a target
  day can only read days up to its *origin*.
* **Direct multi-horizon.** A row is ``(store, sku, origin o, horizon h)`` with target day ``t = o + h``,
  ``1 <= h <= MAX_HORIZON``. Observation-based features (last value, rolling mean/std, same-weekday lags)
  are anchored at the origin: ``lag_last = y[o]`` and same-weekday lags ``y[t-7]``, ``y[t-14]`` (both
  ``<= o`` because ``h <= 7``). For ``h = 1`` these are exactly lag 1/7/14. One model serves all horizons,
  with ``h`` as an input feature (no iterative feedback of predictions).
* **Known-ahead covariates** use the target day: weekday, solar/lunar calendar flags, holiday, promo.
  The ``calendar`` table is used when it covers the day, otherwise flags are computed with ``lunardate``.
  Promotions have no rows after ``as_of``; future promo is taken as 0 (no planned promotion).
* **Rain.** Future rain is unknown at forecast time, so evaluation, conformal calibration and production
  forecasts use the *climatological* value: mean rain of the same calendar month over observed days up to
  the end of the window available to that step. Training uses the same climatological value
  (``known_rain=False``) so there is no train/serve skew; the rain-driven variance is absorbed by the
  quantiles and the conformal offsets. (Training on realised rain was measured too: no WAPE/pinball gain.)
  ``known_rain=True`` is kept for what-if use with a real weather forecast. Weather rows after ``as_of``
  are ignored on purpose.
* **Scaling.** Each row has ``scale = max(mean of observed units over the 28 days ending at the origin, 1)``
  (falls back to the mean over all history up to the origin, then 1). Targets and level features are
  divided by ``scale``; the model predicts quantiles of ``y / scale``. This keeps one network usable for SKUs
  selling 2 or 200 units a day.
* **Fixed vocabularies** (needed for FedAvg in ``forecasting/fl``): area types are a fixed list, categories
  are a fixed catalogue list plus an ``other`` slot, and SKUs are hashed into ``N_SKU_BUCKETS``
  embedding rows with ``zlib.crc32`` (process-independent), so weight shapes never depend on one chain's data.
* **Short history** (new stores with ~14 days): missing lags are imputed with the available rolling mean and
  flagged with indicator features; ``hist_frac`` tells the model how much history exists.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from lunardate import LunarDate

MAX_HORIZON = 7
AREA_TYPES = ("residential", "market", "office")
CATEGORIES = (
    "vegetable", "meat", "seafood", "egg", "dairy", "tofu", "staple", "condiment", "beverage", "snack",
    "household", "other",
)  # fmt: skip
N_CATEGORY_BUCKETS = len(CATEGORIES)
N_SKU_BUCKETS = 256  # collision-free for the 30-SKU simulated catalogue
HIST_CAP_DAYS = 56
SCALE_WINDOW = 28

FEATURE_NAMES: tuple[str, ...] = (
    "lag_last",
    "lag_sdow1",
    "lag_sdow2",
    "miss_last",
    "miss_sdow1",
    "miss_sdow2",
    "roll_mean7",
    "roll_std7",
    "log_scale",
    "hist_frac",
    "horizon",
    *(f"dow_{i}" for i in range(7)),
    "is_tet",
    "is_ram",
    "is_mung1",
    "is_holiday",
    "month_sin",
    "month_cos",
    "dom_start",
    "dom_end",
    "promo",
    "rain",
    *(f"area_{a}" for a in AREA_TYPES),
    *(f"cat_{c}" for c in CATEGORIES),
    "is_fresh",
)
N_FEATURES = len(FEATURE_NAMES)

# Fixed-date (solar) public holidays in Viet Nam.
_SOLAR_HOLIDAYS = {(1, 1), (4, 30), (5, 1), (9, 2), (9, 3)}


def stable_bucket(key: str, n_buckets: int) -> int:
    """Process-independent hash bucket (``hash()`` is salted per process)."""
    return zlib.crc32(key.encode("utf-8")) % n_buckets


def calendar_flags(day: dt.date) -> tuple[int, int, int, int]:
    """(is_tet, is_ram, is_mung1, is_holiday) computed from the solar date via ``lunardate``."""
    lunar = LunarDate.from_solar_date(day.year, day.month, day.day)
    leap = bool(lunar.is_leap_month)
    is_tet = int(not leap and lunar.month == 1 and lunar.day <= 3)
    is_ram = int(lunar.day == 15)
    is_mung1 = int(lunar.day == 1)
    hung_kings = not leap and lunar.month == 3 and lunar.day == 10
    tet_eve = not leap and lunar.month == 12 and day + dt.timedelta(days=1) == _next_tet(day)
    is_holiday = int(bool(is_tet) or hung_kings or tet_eve or (day.month, day.day) in _SOLAR_HOLIDAYS)
    return is_tet, is_ram, is_mung1, is_holiday


def _next_tet(day: dt.date) -> dt.date:
    lunar = LunarDate.from_solar_date(day.year, day.month, day.day)
    return LunarDate(lunar.year + 1, 1, 1).to_solar_date()


@dataclass
class ChainData:
    """Dense, read-only view of one chain's history (plus ``MAX_HORIZON`` future days)."""

    chain_id: str
    start: dt.date
    n_hist: int  # number of history days (index n_hist - 1 is the last day in daily_sales)
    store_ids: list[str]
    sku_ids: list[str]
    store_area: list[str]
    store_history_days: np.ndarray  # from the stores table
    sku_category: list[str]
    sku_is_fresh: np.ndarray
    units: np.ndarray  # (S, K, T) float64, NaN where no observation
    promo: np.ndarray  # (S, K, T) float64
    rain: np.ndarray  # (T,) realised rain mm, NaN where unknown
    cal: np.ndarray  # (T, 4) is_tet, is_ram, is_mung1, is_holiday
    _csum: np.ndarray | None = None
    _csq: np.ndarray | None = None
    _ccnt: np.ndarray | None = None

    @property
    def n_days(self) -> int:
        return self.units.shape[2]

    def date_of(self, idx: int) -> dt.date:
        return self.start + dt.timedelta(days=int(idx))

    def index_of(self, day: dt.date) -> int:
        return (day - self.start).days

    @property
    def last_date(self) -> dt.date:
        return self.date_of(self.n_hist - 1)

    def store_index(self, store_id: str) -> int:
        try:
            return self.store_ids.index(store_id)
        except ValueError as exc:
            raise ValueError(f"unknown store_id {store_id!r} for chain {self.chain_id}") from exc

    def sku_index(self, sku_id: str) -> int:
        try:
            return self.sku_ids.index(sku_id)
        except ValueError as exc:
            raise ValueError(f"unknown sku_id {sku_id!r} for chain {self.chain_id}") from exc

    def cumulative(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Prefix sums over days of units, units^2 and observation counts; index ``t + 1`` covers ``<= t``."""
        if self._csum is None:
            obs = ~np.isnan(self.units)
            vals = np.where(obs, self.units, 0.0)
            pad = np.zeros(self.units.shape[:2] + (1,))
            self._csum = np.concatenate([pad, np.cumsum(vals, axis=2)], axis=2)
            self._csq = np.concatenate([pad, np.cumsum(vals * vals, axis=2)], axis=2)
            self._ccnt = np.concatenate([pad, np.cumsum(obs, axis=2, dtype=np.float64)], axis=2)
        assert self._csq is not None and self._ccnt is not None
        return self._csum, self._csq, self._ccnt

    def history_count(self, s_idx: np.ndarray, k_idx: np.ndarray, origin: np.ndarray) -> np.ndarray:
        _, _, ccnt = self.cumulative()
        return ccnt[s_idx, k_idx, origin + 1]

    def rain_climatology(self, upto_idx: int) -> np.ndarray:
        """Mean rain per calendar month (index 1..12) over days ``<= upto_idx``; overall mean if unseen."""
        months = np.array([self.date_of(i).month for i in range(upto_idx + 1)])
        rain = self.rain[: upto_idx + 1]
        ok = ~np.isnan(rain)
        overall = float(rain[ok].mean()) if ok.any() else 0.0
        clim = np.full(13, overall)
        for m in range(1, 13):
            sel = ok & (months == m)
            if sel.any():
                clim[m] = float(rain[sel].mean())
        return clim


def chain_db_path(data_dir: Path, chain_id: str) -> Path:
    return Path(data_dir) / "chains" / f"{chain_id}.sqlite"


def load_chain(chain_id: str, data_dir: Path) -> ChainData:
    """Load one chain DB (read-only) into a dense ``ChainData`` with ``MAX_HORIZON`` future days appended."""
    path = chain_db_path(data_dir, chain_id)
    if not path.exists():
        raise FileNotFoundError(f"chain database not found: {path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        stores = con.execute(
            "SELECT store_id, area_type, COALESCE(history_days, 0) FROM stores ORDER BY store_id"
        ).fetchall()
        skus = con.execute("SELECT sku_id, category, is_fresh FROM skus ORDER BY sku_id").fetchall()
        sales = con.execute(
            "SELECT store_id, sku_id, date, units, promo, rain_mm FROM daily_sales"
        ).fetchall()
        cal_rows = con.execute("SELECT date, is_tet, is_ram, is_mung1, is_holiday FROM calendar").fetchall()
        has_weather = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='weather'"
        ).fetchone()
        weather = con.execute("SELECT date, rain_mm FROM weather").fetchall() if has_weather else []
    finally:
        con.close()
    if not sales:
        raise ValueError(f"no daily_sales rows for chain {chain_id}")

    store_ids = [r[0] for r in stores]
    sku_ids = [r[0] for r in skus]
    s_pos = {s: i for i, s in enumerate(store_ids)}
    k_pos = {k: i for i, k in enumerate(sku_ids)}
    dates = [r[2] for r in sales]
    start = dt.date.fromisoformat(min(dates))
    end = dt.date.fromisoformat(max(dates))
    n_hist = (end - start).days + 1
    n_days = n_hist + MAX_HORIZON

    units = np.full((len(store_ids), len(sku_ids), n_days), np.nan)
    promo = np.zeros_like(units)
    rain_sum = np.zeros(n_days)
    rain_cnt = np.zeros(n_days)
    for store_id, sku_id, day, qty, pr, rain_mm in sales:
        t = (dt.date.fromisoformat(day) - start).days
        s, k = s_pos[store_id], k_pos[sku_id]
        units[s, k, t] = float(qty)
        promo[s, k, t] = float(pr or 0)
        if rain_mm is not None:
            rain_sum[t] += float(rain_mm)
            rain_cnt[t] += 1
    rain = np.where(rain_cnt > 0, rain_sum / np.maximum(rain_cnt, 1), np.nan)
    for day, rain_mm in weather:
        t = (dt.date.fromisoformat(day) - start).days
        if 0 <= t < n_hist and rain_mm is not None:
            rain[t] = float(rain_mm)
    rain[n_hist:] = np.nan

    cal_table = {r[0]: r[1:] for r in cal_rows}
    cal = np.zeros((n_days, 4))
    for t in range(n_days):
        day = start + dt.timedelta(days=t)
        row = cal_table.get(day.isoformat())
        cal[t] = row if row is not None else calendar_flags(day)

    return ChainData(
        chain_id=chain_id,
        start=start,
        n_hist=n_hist,
        store_ids=store_ids,
        sku_ids=sku_ids,
        store_area=[r[1] for r in stores],
        store_history_days=np.array([r[2] for r in stores], dtype=np.int64),
        sku_category=[r[1] or "" for r in skus],
        sku_is_fresh=np.array([int(r[2] or 0) for r in skus], dtype=np.float64),
        units=units,
        promo=promo,
        rain=rain,
        cal=cal,
    )


def _window(arr: np.ndarray, s: np.ndarray, k: np.ndarray, end: np.ndarray, width: int) -> np.ndarray:
    lo = np.maximum(end + 1 - width, 0)
    return arr[s, k, end + 1] - arr[s, k, lo]


@dataclass(frozen=True)
class FeatureBatch:
    X: np.ndarray  # (n, N_FEATURES)
    sku_bucket: np.ndarray  # (n,) int64 embedding row
    scale: np.ndarray  # (n,)
    target_idx: np.ndarray  # (n,) day index of the target


def build_features(
    cd: ChainData,
    s_idx: np.ndarray,
    k_idx: np.ndarray,
    origin: np.ndarray,
    horizon: np.ndarray,
    *,
    known_rain: bool,
    rain_clim: np.ndarray | None = None,
) -> FeatureBatch:
    """Features for rows ``(store, sku, origin, horizon)``; observation features only read days ``<= origin``.

    ``known_rain=False`` requires ``rain_clim`` (from ``ChainData.rain_climatology``) and uses it for the
    target day's rain.
    """
    s_idx = np.asarray(s_idx, dtype=np.int64)
    k_idx = np.asarray(k_idx, dtype=np.int64)
    origin = np.asarray(origin, dtype=np.int64)
    horizon = np.asarray(horizon, dtype=np.int64)
    if np.any(horizon < 1) or np.any(horizon > MAX_HORIZON):
        raise ValueError(f"horizon must be within 1..{MAX_HORIZON}")
    target = origin + horizon
    if np.any(origin < 0) or np.any(target >= cd.n_days):
        raise ValueError("origin/target outside the loaded date range")
    csum, csq, ccnt = cd.cumulative()

    cnt7 = _window(ccnt, s_idx, k_idx, origin, 7)
    sum7 = _window(csum, s_idx, k_idx, origin, 7)
    sq7 = _window(csq, s_idx, k_idx, origin, 7)
    cnt_s = _window(ccnt, s_idx, k_idx, origin, SCALE_WINDOW)
    sum_s = _window(csum, s_idx, k_idx, origin, SCALE_WINDOW)
    cnt_all = ccnt[s_idx, k_idx, origin + 1]
    sum_all = csum[s_idx, k_idx, origin + 1]

    mean_all = np.divide(sum_all, cnt_all, out=np.zeros_like(sum_all), where=cnt_all > 0)
    mean_s = np.divide(sum_s, cnt_s, out=mean_all.copy(), where=cnt_s > 0)
    mean7 = np.divide(sum7, cnt7, out=mean_s.copy(), where=cnt7 > 0)
    var7 = np.divide(sq7, cnt7, out=np.zeros_like(sq7), where=cnt7 > 0) - np.where(cnt7 > 0, mean7**2, 0.0)
    std7 = np.sqrt(np.maximum(var7, 0.0))
    scale = np.maximum(mean_s, 1.0)

    def lag(day_idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        valid = day_idx >= 0
        vals = np.full(day_idx.shape, np.nan)
        vals[valid] = cd.units[s_idx[valid], k_idx[valid], day_idx[valid]]
        miss = np.isnan(vals)
        return np.where(miss, mean7, vals), miss.astype(np.float64)

    weeks = (horizon + 6) // 7
    lag_last, miss_last = lag(origin)
    lag_s1, miss_s1 = lag(target - 7 * weeks)
    lag_s2, miss_s2 = lag(target - 7 * weeks - 7)

    n = len(s_idx)
    X = np.empty((n, N_FEATURES))
    X[:, 0] = lag_last / scale
    X[:, 1] = lag_s1 / scale
    X[:, 2] = lag_s2 / scale
    X[:, 3] = miss_last
    X[:, 4] = miss_s1
    X[:, 5] = miss_s2
    X[:, 6] = mean7 / scale
    X[:, 7] = std7 / scale
    X[:, 8] = np.log1p(scale)
    X[:, 9] = np.minimum(cnt_all, HIST_CAP_DAYS) / HIST_CAP_DAYS
    X[:, 10] = horizon / MAX_HORIZON

    target_dates = [cd.date_of(t) for t in range(cd.n_days)]
    dow_all = np.array([d.weekday() for d in target_dates])
    month_all = np.array([d.month for d in target_dates])
    dom_all = np.array([d.day for d in target_dates])
    dow = dow_all[target]
    X[:, 11:18] = np.eye(7)[dow]
    X[:, 18:22] = cd.cal[target]
    month = month_all[target]
    X[:, 22] = np.sin(2 * np.pi * month / 12)
    X[:, 23] = np.cos(2 * np.pi * month / 12)
    X[:, 24] = (dom_all[target] <= 3).astype(np.float64)
    X[:, 25] = (dom_all[target] >= 28).astype(np.float64)
    X[:, 26] = cd.promo[s_idx, k_idx, target]
    if known_rain:
        rain = cd.rain[target]
        if rain_clim is not None:
            rain = np.where(np.isnan(rain), rain_clim[month], rain)
        rain = np.nan_to_num(rain, nan=0.0)
    else:
        if rain_clim is None:
            raise ValueError("rain_clim is required when known_rain=False")
        rain = rain_clim[month]
    X[:, 27] = np.log1p(rain)
    area = np.array([AREA_TYPES.index(a) if a in AREA_TYPES else -1 for a in cd.store_area])[s_idx]
    X[:, 28:31] = 0.0
    ok = area >= 0
    X[np.flatnonzero(ok), 28 + area[ok]] = 1.0
    other = CATEGORIES.index("other")
    cat = np.array([CATEGORIES.index(c) if c in CATEGORIES else other for c in cd.sku_category])[k_idx]
    c0 = 31
    X[:, c0 : c0 + N_CATEGORY_BUCKETS] = np.eye(N_CATEGORY_BUCKETS)[cat]
    X[:, c0 + N_CATEGORY_BUCKETS] = cd.sku_is_fresh[k_idx]

    sku_bucket = np.array([stable_bucket(k, N_SKU_BUCKETS) for k in cd.sku_ids], dtype=np.int64)[k_idx]
    return FeatureBatch(X=X, sku_bucket=sku_bucket, scale=scale, target_idx=target)


def target_rows(
    cd: ChainData, first_target: int, last_target: int, horizons: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """All ``(s, k, origin, h)`` whose target day lies in ``[first_target, last_target]``, is observed, and
    whose series has at least one observation at the origin."""
    hs = np.arange(1, MAX_HORIZON + 1) if horizons is None else np.asarray(horizons)
    S, K = cd.units.shape[:2]
    targets = np.arange(first_target, last_target + 1)
    s, k, t, h = (a.ravel() for a in np.meshgrid(np.arange(S), np.arange(K), targets, hs, indexing="ij"))
    origin = t - h
    keep = origin >= 0
    s, k, origin, h, t = s[keep], k[keep], origin[keep], h[keep], t[keep]
    keep = ~np.isnan(cd.units[s, k, t]) & (cd.history_count(s, k, origin) > 0)
    return s[keep], k[keep], origin[keep], h[keep]
