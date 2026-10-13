"""Small synthetic chain DB (schema subset of the master plan) for forecasting tests."""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from forecasting.features import calendar_flags
from forecasting.service import TrainConfig, train_local
from provenance import write_registry

CHAIN = "CHAIN_T"
# Provenance of the fixture: row-level ids for sales/stores/skus, table-level ids for calendar/weather.
SALES_SOURCE = "test_sales"
TABLE_SOURCES = {"calendar": "test_calendar", "weather": "test_weather"}
FIXTURE_SOURCES = sorted([SALES_SOURCE, *TABLE_SOURCES.values()])
TEST_REGISTRY = {
    ds_id: {
        "id": ds_id,
        "name_vi": f"Bộ thử {ds_id}",
        "kind": "synthetic_code",
        "url": None,
        "license": None,
        "retrieved_at": None,
        "description_vi": "Dữ liệu cố định của bộ kiểm thử.",
    }
    for ds_id in FIXTURE_SOURCES
}
AS_OF = dt.date(2026, 9, 30)
N_DAYS = 200
NEW_STORE_DAYS = 14
STORES = [
    ("T_S1", "residential", N_DAYS, 0),
    ("T_S2", "market", N_DAYS, 0),
    ("T_S3", "office", N_DAYS, 0),
    ("T_NEW", "residential", NEW_STORE_DAYS, 1),
]
SKUS = [
    ("SKU_RAU", "vegetable", 1, 2, 30.0),
    ("SKU_THIT", "meat", 1, 1, 12.0),
    ("SKU_CA", "seafood", 1, 2, 6.0),
    ("SKU_GAO", "staple", 0, 180, 20.0),
    ("SKU_MI", "staple", 0, 180, 45.0),
    ("SKU_SUA", "dairy", 0, 30, 3.0),
]
AREA_MULT = {"residential": 1.0, "market": 1.4, "office": 0.7}
DOW_MULT = np.array([0.9, 0.85, 0.9, 0.95, 1.05, 1.35, 1.3])


def make_chain_db(data_dir: Path, *, chain_id: str = CHAIN, seed: int = 7) -> Path:
    rng = np.random.default_rng(seed)
    path = data_dir / "chains" / f"{chain_id}.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    start = AS_OF - dt.timedelta(days=N_DAYS - 1)
    days = [start + dt.timedelta(days=i) for i in range(N_DAYS)]
    rain = np.where(rng.random(N_DAYS) < 0.35, rng.gamma(2.0, 8.0, N_DAYS), 0.0)
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE chains(chain_id TEXT PRIMARY KEY, name TEXT, source TEXT);
        CREATE TABLE stores(store_id TEXT PRIMARY KEY, chain_id TEXT, name TEXT, lat REAL, lng REAL,
            area_type TEXT, opened_date TEXT, history_days INT, is_new INT, source TEXT);
        CREATE TABLE skus(sku_id TEXT PRIMARY KEY, name TEXT, category TEXT, is_fresh INT, shelf_life_days INT,
            unit_cost REAL, unit_price REAL, salvage_price REAL, moq INT, supplier_id TEXT,
            cold_storage_units REAL, source TEXT);
        CREATE TABLE daily_sales(store_id TEXT, sku_id TEXT, date TEXT, units INT, price REAL, promo INT,
            rain_mm REAL, source TEXT, PRIMARY KEY(store_id, sku_id, date));
        CREATE TABLE calendar(date TEXT PRIMARY KEY, dow INT, lunar_month INT, lunar_day INT, is_tet INT,
            is_ram INT, is_mung1 INT, is_holiday INT);
        CREATE TABLE weather(date TEXT PRIMARY KEY, rain_mm REAL);
        CREATE TABLE data_sources(table_name TEXT, dataset_id TEXT);
        """
    )
    con.executemany("INSERT INTO data_sources VALUES (?, ?)", sorted(TABLE_SOURCES.items()))
    write_registry(data_dir, TEST_REGISTRY)
    con.execute("INSERT INTO chains VALUES (?, ?, ?)", (chain_id, "Chuỗi thử", SALES_SOURCE))
    for sid, area, hist, is_new in STORES:
        opened = (AS_OF - dt.timedelta(days=hist - 1)).isoformat()
        con.execute(
            "INSERT INTO stores VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sid, chain_id, sid, 10.77, 106.69, area, opened, hist, is_new, SALES_SOURCE),
        )
    for sku, cat, fresh, shelf, _ in SKUS:
        con.execute(
            "INSERT INTO skus VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (sku, sku, cat, fresh, shelf, 10000.0, 15000.0, 3000.0, 1, "SUP", 1.0, SALES_SOURCE),
        )
    rows = []
    for i, day in enumerate(days):
        flags = calendar_flags(day)
        con.execute(
            "INSERT INTO calendar VALUES (?,?,?,?,?,?,?,?)", (day.isoformat(), day.weekday(), 0, 0, *flags)
        )
        con.execute("INSERT INTO weather VALUES (?, ?)", (day.isoformat(), float(rain[i])))
        for sid, area, hist, _ in STORES:
            if i < N_DAYS - hist:
                continue
            for sku, _cat, fresh, _shelf, base in SKUS:
                promo = int(rng.random() < 0.08)
                mu = base * AREA_MULT[area] * DOW_MULT[day.weekday()]
                mu *= 1.0 + 0.4 * flags[1]
                mu *= 1.6 if promo else 1.0
                mu *= 0.75 if (fresh and rain[i] > 10) else 1.0
                lam = rng.gamma(8.0, mu / 8.0)
                rows.append(
                    (
                        sid,
                        sku,
                        day.isoformat(),
                        int(rng.poisson(lam)),
                        15000.0,
                        promo,
                        float(rain[i]),
                        SALES_SOURCE,
                    )
                )
    con.executemany("INSERT INTO daily_sales VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


FAST_CONFIG = TrainConfig(hidden=(32, 16), epochs=6, batch_size=512, max_train_rows=60_000)


@pytest.fixture(scope="session")
def chain_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    data_dir = tmp_path_factory.mktemp("fc_data")
    make_chain_db(data_dir)
    return data_dir


@pytest.fixture(scope="session")
def trained_dir(chain_dir: Path):
    art = train_local(CHAIN, data_dir=chain_dir, seed=0, config=FAST_CONFIG)
    return chain_dir, art


FL_CHAINS = ("T_A", "T_B", "T_C")


@pytest.fixture(scope="session")
def fl_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Three small, mildly non-IID chains (different seeds) for federated-learning tests."""
    data_dir = tmp_path_factory.mktemp("fl_data")
    for i, chain_id in enumerate(FL_CHAINS):
        make_chain_db(data_dir, chain_id=chain_id, seed=11 + i)
    return data_dir
