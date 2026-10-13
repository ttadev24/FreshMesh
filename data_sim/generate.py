"""Deterministic builder of the per-chain SQLite databases.

Real public inputs (offline, from the committed snapshots in `data_real/`): store / pickup-point / delivery
locations (OpenStreetMap, ODbL), daily rain (Open-Meteo, CC BY 4.0), official holidays (CALENDAR_VN).
Program-generated layers (dataset GEN_PROGRAM_V1, seed-determined): chains, SKU catalogue and prices,
daily sales, promotions, inventory lots, online orders (time, size, window, mode), demo users.
Every row's `source` column holds the dataset id; `data_sources` lists datasets of columns without a
row-level source; `osm_refs` keeps the OSM element behind each located row.
"""

import datetime as dt
import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from data_sim.assumptions import (
    ASSUMPTION_DESCRIPTIONS_VI,
    ASSUMPTIONS,
    HISTORY_DAYS,
    NEW_STORE_HISTORY_DAYS,
    SIM_AS_OF,
    SIM_BATCH_START,
    SIM_BATCH_WINDOW_MINUTES,
)
from data_sim.auth import hash_password
from data_sim.calendar_weather import PRE_TET_DAYS, CalendarDay, build_calendar, real_rain
from data_sim.catalog import (
    AREA_CATEGORY_MIX,
    AREA_VOLUME,
    CHAINS,
    DOW_FACTORS,
    HEAVY_RAIN_MM,
    PROMO_DAYS,
    PROMO_PRICE_FACTOR,
    PROMO_UPLIFT,
    RAIN_FACTORS,
    SKUS,
    SURPLUS_STORE_INDEX,
    ChainProfile,
    SkuSpec,
)
from data_sim.locations import haversine_km
from data_sim.schema import TABLES_DDL, views_ddl
from data_sim.sites import (
    COUNTER_RADIUS_KM,
    Point,
    Site,
    buildings_within,
    lobby_candidates,
    readable_name,
    select_sites,
)

SOURCE = "GEN_PROGRAM_V1"  # dataset id of every program-generated row (see provenance/registry_defaults.json)
SITES_SOURCE = "OSM_HCMC_SITES"  # stores and pickup points located on real OSM features
OSM_SOURCE = "OSM_HCMC"
DEMO_PASSWORD = "demo123"
CALENDAR_FUTURE_DAYS = 60  # calendar rows after SIM_AS_OF so forecasts get future features
WEATHER_FUTURE_DAYS = 14  # simulated "weather forecast" rows after SIM_AS_OF

# Batch size range by area type (orders in one 45-minute window).
BATCH_SIZE_RANGE = {"residential": (22, 36), "market": (16, 28), "office": (12, 22)}
DAILY_ORDERS_RANGE = {"residential": (70, 110), "market": (50, 85), "office": (40, 70)}
MODE_PROBS = (("home", 0.55), ("pickup", 0.20), ("flexible", 0.25))


@dataclass(frozen=True)
class StoreRow:
    store_id: str
    chain_id: str
    name: str
    lat: float
    lng: float
    area_type: str
    opened_date: dt.date
    history_days: int
    is_new: bool


@dataclass(frozen=True)
class PickupRow:
    pickup_point_id: str
    store_id: str
    name: str
    lat: float
    lng: float
    is_counter: bool
    osm: str


def counter_point_id(store_id: str) -> str:
    """Same id as routing.models.counter_id: the routing adapter adds this point itself."""
    return f"{store_id}-counter"


def history_dates() -> list[dt.date]:
    return [SIM_AS_OF - dt.timedelta(days=HISTORY_DAYS - 1 - i) for i in range(HISTORY_DAYS)]


def _round_vnd(x: float) -> int:
    return int(round(x / 500.0) * 500)


def _sku_price(sku: SkuSpec, profile: ChainProfile) -> int:
    return _round_vnd(sku.unit_price * profile.price_multiplier)


def _category_group(category: str) -> str:
    if category in ("vegetable", "tofu"):
        return "plant"
    if category in ("meat", "seafood"):
        return "animal"
    return "other"


def _calendar_factor(day: CalendarDay, group: str, area: str, s: float) -> float:
    f = 1.0
    if not day.is_leap_month and day.lunar_month == 1 and day.lunar_day <= 3:
        f *= max(0.15, 1.0 - 0.65 * s)  # Tết: many customers away, short opening hours
    elif not day.is_leap_month and day.lunar_month == 1 and day.lunar_day <= 7:
        f *= 0.8
    elif 1 <= day.days_to_tet <= PRE_TET_DAYS:
        ramp = (PRE_TET_DAYS + 1 - day.days_to_tet) / PRE_TET_DAYS
        peak = 0.9 if group == "animal" else 0.55
        f *= 1.0 + peak * s * ramp
    elif day.is_ram or day.is_mung1:
        if group == "plant":
            f *= 1.0 + 0.35 * s  # vegetarian day
        elif group == "animal":
            f *= max(0.5, 1.0 - 0.18 * s)
    if day.is_holiday and not (day.lunar_month == 1 and day.lunar_day <= 5):
        f *= 0.45 if area == "office" else 1.1
    return f


def _rain_factor(rain_mm: float, area: str, sens: float) -> float:
    light, heavy = RAIN_FACTORS[area]
    if rain_mm >= HEAVY_RAIN_MM:
        base = heavy
    elif rain_mm >= 2.0:
        base = light
    else:
        return 1.0
    return max(0.3, 1.0 - (1.0 - base) * sens)


def _build_stores(profile: ChainProfile, sites: list[Site], rng: np.random.Generator) -> list[StoreRow]:
    stores: list[StoreRow] = []
    for i, area in enumerate(profile.area_types):
        site = sites[i]
        if site.area_type != area:
            raise ValueError(f"{profile.chain_id} CH{i + 1}: site area {site.area_type} != profile {area}")
        is_new = profile.new_store_index == i
        if is_new:
            opened = SIM_AS_OF - dt.timedelta(days=NEW_STORE_HISTORY_DAYS - 1)
            hist = NEW_STORE_HISTORY_DAYS
        else:
            opened = SIM_AS_OF - dt.timedelta(days=HISTORY_DAYS + int(rng.integers(30, 1500)))
            hist = HISTORY_DAYS
        store_id = f"{profile.letter.upper()}-CH{i + 1}"
        stores.append(
            StoreRow(store_id, profile.chain_id, f"CH{i + 1} {site.place}", site.lat, site.lng, area,
                     opened, hist, is_new)
        )
    return stores


def _simulate_sales(
    profile: ChainProfile,
    stores: list[StoreRow],
    cal: list[CalendarDay],
    rain: np.ndarray,
    rng: np.random.Generator,
) -> tuple[list[tuple], dict[tuple[str, str], float]]:
    """Return daily_sales rows and the mean daily units of the last 7 days per (store, sku)."""
    n_days = len(cal)
    t = np.arange(n_days)
    trend = 1.0 + profile.trend_per_year * (t - (n_days - 1)) / 365.0
    rows: list[tuple] = []
    recent_mean: dict[tuple[str, str], float] = {}
    for store in stores:
        area = store.area_type
        store_mult = AREA_VOLUME[area] * profile.volume_scale * float(rng.uniform(0.8, 1.25))
        dow = np.array([DOW_FACTORS[area][d.dow] for d in cal])
        rainf = np.array([_rain_factor(r, area, profile.rain_sensitivity) for r in rain])
        cal_f = {
            g: np.array([_calendar_factor(d, g, area, profile.lunar_sensitivity) for d in cal])
            for g in ("plant", "animal", "other")
        }
        first = n_days - store.history_days
        for sku in SKUS:
            mix = AREA_CATEGORY_MIX[area].get(sku.category, 1.0)
            fresh = profile.fresh_affinity if sku.is_fresh else 1.0
            base = sku.base_daily_units * mix * fresh * store_mult * float(rng.lognormal(0.0, 0.15))
            rate = profile.promo_rate * (0.6 if sku.is_fresh else 1.0)
            starts = rng.random(n_days) < rate
            promo = np.zeros(n_days, dtype=bool)
            for s in np.flatnonzero(starts):
                promo[s : s + PROMO_DAYS] = True
            mu = base * dow * rainf * cal_f[_category_group(sku.category)] * trend
            mu = np.where(promo, mu * PROMO_UPLIFT, mu)
            k = profile.dispersion_k
            units = rng.negative_binomial(k, k / (k + np.maximum(mu, 1e-6)))
            price = _sku_price(sku, profile)
            promo_price = _round_vnd(price * PROMO_PRICE_FACTOR)
            for i in range(first, n_days):
                rows.append(
                    (store.store_id, sku.sku_id, cal[i].date.isoformat(), int(units[i]),
                     float(promo_price if promo[i] else price), int(promo[i]), float(rain[i]), SOURCE)
                )
            recent_mean[(store.store_id, sku.sku_id)] = float(units[n_days - 7 :].mean())
    return rows, recent_mean


def _shortage_store(stores: list[StoreRow]) -> StoreRow:
    surplus = stores[SURPLUS_STORE_INDEX]
    others = [s for s in stores if s.store_id != surplus.store_id and not s.is_new]
    return min(others, key=lambda s: haversine_km(s.lat, s.lng, surplus.lat, surplus.lng))


def _inventory_lots(
    stores: list[StoreRow], recent_mean: dict[tuple[str, str], float], rng: np.random.Generator
) -> list[tuple]:
    surplus_id = stores[SURPLUS_STORE_INDEX].store_id
    shortage_id = _shortage_store(stores).store_id
    rows: list[tuple] = []
    for store in stores:
        for sku in SKUS:
            m = max(recent_mean[(store.store_id, sku.sku_id)], 0.5)
            lots: list[tuple[int, int]] = []  # (age_days, qty)
            if sku.is_fresh:
                life = sku.shelf_life_days
                for age in range(life):
                    if age == life - 1 and life > 1:
                        frac = rng.uniform(0.15, 0.45)  # oldest lot, expires tomorrow
                    elif age == 0:
                        frac = rng.uniform(0.7, 1.1)
                    else:
                        frac = rng.uniform(0.4, 0.8)
                    lots.append((age, int(round(m * frac))))
                if sku.category == "vegetable" and store.store_id == surplus_id:
                    # "Còn nhiều rau ở CH3": a large lot that expires tomorrow
                    lots = [(life - 1, int(round(m * rng.uniform(2.6, 3.4))))] + [
                        lot for lot in lots if lot[0] != life - 1
                    ]
                elif sku.category == "vegetable" and store.store_id == shortage_id:
                    lots = [(0, int(round(m * rng.uniform(0.05, 0.2))))]
            else:
                for _ in range(int(rng.integers(1, 3))):
                    lots.append((int(rng.integers(3, 46)), int(round(m * rng.uniform(4.0, 12.0)))))
            for age, qty in sorted(lots):
                if qty <= 0:
                    continue
                received = SIM_AS_OF - dt.timedelta(days=age)
                expires = received + dt.timedelta(days=sku.shelf_life_days)
                rows.append(
                    (store.store_id, sku.sku_id, qty, received.isoformat(), expires.isoformat(), SOURCE)
                )
    return rows


def _lobby_name(p: Point) -> str:
    return f"Sảnh {p.name}" if readable_name(p.name) else f"Sảnh tòa chung cư (OSM {p.osm})"


def _pickup_points(stores: list[StoreRow], sites: list[Site], rng: np.random.Generator) -> list[PickupRow]:
    """Counter at the store + 2–3 real OSM apartment buildings 0.4–1.2 km away (named ones preferred)."""
    points: list[PickupRow] = []
    for store, site in zip(stores, sites, strict=True):
        points.append(
            PickupRow(counter_point_id(store.store_id), store.store_id, f"Quầy nhận hàng tại {store.name}",
                      store.lat, store.lng, True, site.osm)
        )
        cands = lobby_candidates(store.lat, store.lng)
        named = [p for p in cands if readable_name(p.name)]
        pool = named if len(named) >= 3 else cands
        taken = [p.osm for p in points]
        k = int(rng.integers(2, 4))
        picked: list[Point] = []
        for i in rng.permutation(len(pool)):
            p = pool[int(i)]
            if p.osm not in taken and all(haversine_km(p.lat, p.lng, q.lat, q.lng) >= 0.15 for q in picked):
                picked.append(p)
            if len(picked) == k:
                break
        for j, p in enumerate(picked):
            points.append(
                PickupRow(f"{store.store_id}-PP{j + 1}", store.store_id, _lobby_name(p), p.lat, p.lng, False,
                          p.osm)
            )
    return points


def _travel_minutes(dist_km: float) -> int:
    speed = ASSUMPTIONS["speed_kmh"]
    detour = ASSUMPTIONS["detour_factor"]
    return math.ceil(dist_km * detour * 60.0 / speed)


@dataclass(frozen=True)
class _StoreGeo:
    """Real OSM buildings around one store, used as order destinations."""

    home: list[Point]  # HOME_RADIUS_KM from the store
    tight: list[Point]  # 2.6–3.3 km from the store
    near_point: dict[str, list[Point]]  # pickup_point_id -> buildings within 0.5 km (0.8 km for lobbies)


def _store_geo(store: StoreRow, points: list[PickupRow]) -> _StoreGeo:
    near = {}
    for p in points:
        radius = COUNTER_RADIUS_KM if p.is_counter else 0.8
        near[p.pickup_point_id] = buildings_within(p.lat, p.lng, 0.0, radius)
    return _StoreGeo(buildings_within(store.lat, store.lng, 0.3, 3.0),
                     buildings_within(store.lat, store.lng, 2.6, 3.3), near)


def _choose(rng: np.random.Generator, pool: list[Point]) -> Point:
    return pool[int(rng.integers(len(pool)))]


def _make_order(
    rng: np.random.Generator,
    store: StoreRow,
    points: list[PickupRow],
    geo: _StoreGeo,
    shift: int,
    tight: bool,
) -> tuple[float, float, int, int, int, int, str, str | None, str]:
    """(lat, lng, demand, earliest, latest, service, mode, pickup_point_id, osm) relative to batch start.

    The destination is a real OSM residential building (its OSM id is returned)."""
    demand = int(rng.integers(1, 4))
    if tight:
        # Express request far from the store: the window closes before a rider can arrive.
        dest = _choose(rng, geo.tight)
        travel = _travel_minutes(haversine_km(store.lat, store.lng, dest.lat, dest.lng))
        latest = int(travel * rng.uniform(0.35, 0.65))
        return dest.lat, dest.lng, demand, 0, latest, 3, "home", None, dest.osm

    mode = str(rng.choice([m for m, _ in MODE_PROBS], p=[p for _, p in MODE_PROBS]))
    lobbies = [p for p in points if not p.is_counter]
    pickup_id: str | None = None
    if mode == "pickup":
        point = points[0] if rng.random() < 0.3 else lobbies[int(rng.integers(len(lobbies)))]
        pickup_id = point.pickup_point_id
        pool = geo.near_point[point.pickup_point_id]
    elif mode == "flexible":
        # Customers offer "flexible" only when they live near a pickup lobby (within 0.8 km).
        point = lobbies[int(rng.integers(len(lobbies)))]
        pool = geo.near_point[point.pickup_point_id]
    else:
        pool = geo.home
    dest = _choose(rng, pool)
    travel = _travel_minutes(haversine_km(store.lat, store.lng, dest.lat, dest.lng))
    earliest = int(rng.choice(np.arange(0, 151, 15)))
    latest = min(shift, earliest + int(rng.integers(45, 91)))
    latest = min(shift, max(latest, travel + 10))
    service = 2 if mode == "pickup" else int(rng.integers(3, 7))
    return dest.lat, dest.lng, demand, earliest, latest, service, mode, pickup_id, dest.osm


def _online_orders(
    profile: ChainProfile,
    stores: list[StoreRow],
    points: list[PickupRow],
    rng: np.random.Generator,
    shift: int,
) -> list[tuple]:
    rows: list[tuple] = []
    window = dt.timedelta(minutes=SIM_BATCH_WINDOW_MINUTES)
    hourly = ASSUMPTIONS["hourly_sales_share"]
    for store in stores:
        pts = [p for p in points if p.store_id == store.store_id]
        geo = _store_geo(store, pts)
        # Historical orders over the last 14 days, hourly-distributed.
        shares = hourly[store.area_type]
        hours = np.array([int(h) for h in shares])
        probs = np.array([shares[h] for h in shares])
        probs = probs / probs.sum()
        lo, hi = DAILY_ORDERS_RANGE[store.area_type]
        for back in range(NEW_STORE_HISTORY_DAYS - 1, -1, -1):
            day = SIM_AS_OF - dt.timedelta(days=back)
            n = int(rng.poisson(rng.uniform(lo, hi) * profile.volume_scale * (0.6 if store.is_new else 1.0)))
            stamps = sorted(
                dt.datetime.combine(day, dt.time(int(h))) + dt.timedelta(seconds=int(rng.integers(0, 3600)))
                for h in rng.choice(hours, size=n, p=probs)
            )
            for seq, created in enumerate(stamps):
                lat, lng, demand, earliest, latest, service, mode, pp, osm = _make_order(
                    rng, store, pts, geo, shift, tight=rng.random() < 0.04
                )
                rows.append(
                    (f"{store.store_id}-H{day:%Y%m%d}-{seq + 1:04d}", store.store_id, created.isoformat(),
                     lat, lng, demand, earliest, latest, service, mode, pp, SOURCE, osm)
                )
        # The current batch: created in [SIM_BATCH_START - window, SIM_BATCH_START).
        lo, hi = BATCH_SIZE_RANGE[store.area_type]
        n_batch = int(np.clip(rng.integers(lo, hi + 1) * profile.volume_scale, 12, 40))
        if store.is_new:
            n_batch = int(rng.integers(12, 17))
        n_tight = 1 if n_batch < 18 else 2
        tight_flags = [True] * n_tight + [False] * (n_batch - n_tight)
        rng.shuffle(tight_flags)
        offsets = sorted(int(x) for x in rng.integers(0, int(window.total_seconds()), size=n_batch))
        for j, (off, tight) in enumerate(zip(offsets, tight_flags, strict=True)):
            created = SIM_BATCH_START - window + dt.timedelta(seconds=off)
            lat, lng, demand, earliest, latest, service, mode, pp, osm = _make_order(
                rng, store, pts, geo, shift, tight
            )
            rows.append(
                (f"{store.store_id}-B{j + 1:03d}", store.store_id, created.isoformat(), lat, lng, demand,
                 earliest, latest, service, mode, pp, SOURCE, osm)
            )
    return rows


def _users(profile: ChainProfile, stores: list[StoreRow], seed: int) -> list[tuple]:
    def salt(username: str) -> bytes:
        return hashlib.sha256(f"freshmesh:{seed}:{username}".encode()).digest()[:16]

    owner = f"owner_{profile.letter}"
    manager = f"manager_{profile.letter}1"
    return [
        (f"{profile.chain_id}-owner", profile.chain_id, owner, "owner", None,
         hash_password(DEMO_PASSWORD, salt=salt(owner))),
        (f"{profile.chain_id}-manager1", profile.chain_id, manager, "store_manager", stores[0].store_id,
         hash_password(DEMO_PASSWORD, salt=salt(manager))),
    ]


def _remove_db(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = path.with_name(path.name + suffix)
        if p.exists():
            p.unlink()


def _data_sources(weather_sources: dict[str, str], history: set[str]) -> list[tuple[str, str, str, str]]:
    """(table, column, dataset_id, note_vi) for data that has no row-level `source`."""
    weather_ids = sorted(set(weather_sources.values()))
    sales_weather = sorted({weather_sources[d] for d in history})
    rows = [("weather", "rain_mm", w, "Lượng mưa ngày TP.HCM") for w in weather_ids]
    rows += [("daily_sales", "rain_mm", w, "Lượng mưa ngày của dòng doanh số") for w in sales_weather]
    rows += [
        ("calendar", "is_holiday", "CALENDAR_VN", "Ngày lễ theo BLLĐ 2019 Điều 112 + thông báo hằng năm"),
        ("calendar", "lunar_month,lunar_day,is_tet,is_ram,is_mung1", "CALENDAR_VN", "Âm lịch (lunardate)"),
        ("stores", "lat,lng,name", OSM_SOURCE, "Tọa độ cửa hàng OSM; tên = địa danh OSM gần nhất"),
        ("pickup_points", "lat,lng,name", OSM_SOURCE, "Tòa chung cư OSM làm điểm nhận"),
        ("online_orders", "lat,lng", OSM_SOURCE, "Điểm giao = tâm tòa nhà ở OSM (đơn do chương trình sinh)"),
    ]
    return rows


def _write_chain_db(
    path: Path,
    profile: ChainProfile,
    stores: list[StoreRow],
    sites: list[Site],
    calendar: list[CalendarDay],
    weather: list[tuple[str, float]],
    data_sources: list[tuple[str, str, str, str]],
    sales: list[tuple],
    lots: list[tuple],
    points: list[PickupRow],
    orders: list[tuple],
    users: list[tuple],
) -> None:
    _remove_db(path)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(TABLES_DDL + views_ddl(SIM_AS_OF))
        with conn:
            conn.execute("INSERT INTO chains VALUES (?,?,?)", (profile.chain_id, profile.name, SOURCE))
            conn.executemany(
                "INSERT INTO stores VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(s.store_id, s.chain_id, s.name, s.lat, s.lng, s.area_type, s.opened_date.isoformat(),
                  s.history_days, int(s.is_new), SITES_SOURCE) for s in stores],
            )
            conn.executemany(
                "INSERT INTO skus VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [(k.sku_id, k.name, k.category, int(k.is_fresh), k.shelf_life_days, float(k.unit_cost),
                  float(_sku_price(k, profile)), float(k.salvage_price), k.moq, k.supplier_id,
                  k.cold_storage_units, SOURCE) for k in SKUS],
            )
            conn.executemany("INSERT INTO daily_sales VALUES (?,?,?,?,?,?,?,?)", sales)
            conn.executemany(
                "INSERT INTO calendar VALUES (?,?,?,?,?,?,?,?)",
                [(d.date.isoformat(), d.dow, d.lunar_month, d.lunar_day, int(d.is_tet), int(d.is_ram),
                  int(d.is_mung1), int(d.is_holiday)) for d in calendar],
            )
            conn.executemany("INSERT INTO weather VALUES (?,?)", weather)
            conn.executemany("INSERT INTO inventory_lots VALUES (?,?,?,?,?,?)", lots)
            conn.executemany(
                "INSERT INTO pickup_points VALUES (?,?,?,?,?,?,?,?)",
                [(p.pickup_point_id, p.store_id, p.name, p.lat, p.lng, 0, int(ASSUMPTIONS["shift_minutes"]),
                  SITES_SOURCE) for p in points],
            )
            conn.executemany("INSERT INTO online_orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                             [o[:12] for o in orders])
            conn.executemany("INSERT INTO users VALUES (?,?,?,?,?,?)", users)
            conn.executemany(
                "INSERT INTO assumptions VALUES (?,?,?,?)",
                [(key, json.dumps(value, ensure_ascii=False, sort_keys=True), ASSUMPTION_DESCRIPTIONS_VI[key],
                  SOURCE) for key, value in ASSUMPTIONS.items()],
            )
            conn.executemany("INSERT INTO data_sources VALUES (?,?,?,?)", data_sources)
            refs = [("stores", st.store_id, site.osm, OSM_SOURCE)
                    for st, site in zip(stores, sites, strict=True)]
            refs += [("pickup_points", p.pickup_point_id, p.osm, OSM_SOURCE) for p in points]
            refs += [("online_orders", o[0], o[12], OSM_SOURCE) for o in orders]
            conn.executemany("INSERT INTO osm_refs VALUES (?,?,?,?)", refs)
    finally:
        conn.close()


def calendar_dates() -> list[dt.date]:
    return history_dates() + [SIM_AS_OF + dt.timedelta(days=i) for i in range(1, CALENDAR_FUTURE_DAYS + 1)]


def history_inputs(seed: int) -> tuple[list[CalendarDay], np.ndarray, list[Site]]:
    """Calendar and real rain of the history window, and the store sites of all chains in CHAINS order
    (slice `len(profile.area_types)` per chain) — exactly what `generate_all(seed)` feeds `_build_stores`
    and `_simulate_sales`."""
    hist = history_dates()
    calendar = build_calendar(hist)
    rain, _ = real_rain(hist)
    by_chain = select_sites({p.chain_id: p.area_types for p in CHAINS}, np.random.default_rng([seed, 1]))
    return calendar, rain, [site for p in CHAINS for site in by_chain[p.chain_id]]


def generate_all(out_dir: Path | str, seed: int = 42) -> dict[str, Path]:
    """Create `<out_dir>/chains/<chain_id>.sqlite` for every chain and `<out_dir>/provenance/registry.json`.

    Offline: real inputs come from the committed snapshots in `data_real/`. Re-running overwrites; the
    same seed and snapshots give identical DB content."""
    from data_real import snapshot
    from provenance import write_registry

    out = Path(out_dir) / "chains"
    out.mkdir(parents=True, exist_ok=True)

    cal_dates = calendar_dates()
    calendar = build_calendar(cal_dates)
    weather_dates = cal_dates[: HISTORY_DAYS + WEATHER_FUTURE_DAYS]
    rain_all, weather_sources = real_rain(weather_dates)
    weather = [(d.isoformat(), float(r)) for d, r in zip(weather_dates, rain_all, strict=True)]
    hist_cal = calendar[:HISTORY_DAYS]
    hist_rain = rain_all[:HISTORY_DAYS]
    data_sources = _data_sources(weather_sources, {d.isoformat() for d in cal_dates[:HISTORY_DAYS]})

    wanted = {p.chain_id: p.area_types for p in CHAINS}
    sites_by_chain = select_sites(wanted, np.random.default_rng([seed, 1]))
    shift = int(ASSUMPTIONS["shift_minutes"])

    paths: dict[str, Path] = {}
    for ci, profile in enumerate(CHAINS):
        rng = np.random.default_rng([seed, 100 + ci])
        sites = sites_by_chain[profile.chain_id]
        stores = _build_stores(profile, sites, rng)
        sales, recent = _simulate_sales(profile, stores, hist_cal, hist_rain, rng)
        lots = _inventory_lots(stores, recent, rng)
        points = _pickup_points(stores, sites, rng)
        orders = _online_orders(profile, stores, points, rng, shift)
        users = _users(profile, stores, seed)
        path = out / f"{profile.chain_id}.sqlite"
        _write_chain_db(path, profile, stores, sites, calendar, weather, data_sources, sales, lots, points,
                        orders, users)
        paths[profile.chain_id] = path
    write_registry(out_dir, snapshot.registry_updates())
    return paths
