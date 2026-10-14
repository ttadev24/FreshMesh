import sqlite3

import pytest

from data_sim import CHAIN_IDS, VIEW_NAMES, chain_db_path, open_chain_db
from provenance import load_registry, sources_for

EXPECTED_COLUMNS = {
    "chains": ["chain_id", "name", "source"],
    "stores": ["store_id", "chain_id", "name", "lat", "lng", "area_type", "opened_date", "history_days",
               "is_new", "source"],
    "skus": ["sku_id", "name", "category", "is_fresh", "shelf_life_days", "unit_cost", "unit_price",
             "salvage_price", "moq", "supplier_id", "cold_storage_units", "source"],
    "daily_sales": ["store_id", "sku_id", "date", "units", "price", "promo", "rain_mm", "source"],
    "calendar": ["date", "dow", "lunar_month", "lunar_day", "is_tet", "is_ram", "is_mung1", "is_holiday"],
    "weather": ["date", "rain_mm"],
    "inventory_lots": ["store_id", "sku_id", "qty", "received_date", "expires_on", "source"],
    "pickup_points": ["pickup_point_id", "store_id", "name", "lat", "lng", "earliest", "latest", "source"],
    "online_orders": ["order_id", "store_id", "created_at", "lat", "lng", "demand", "earliest", "latest",
                      "service", "delivery_mode", "pickup_point_id", "source"],
    "users": ["user_id", "chain_id", "username", "role", "store_id", "password_hash"],
    "drafts": ["draft_id", "chain_id", "kind", "payload_json", "status", "created_by", "created_at",
               "decided_at", "decided_by", "source"],
    "audit_log": ["audit_id", "chain_id", "ts", "actor", "event", "payload_json"],
    "assumptions": ["key", "value_json", "description_vi", "source"],
}


def _columns(conn, name):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({name})")]


@pytest.mark.parametrize("chain_id", CHAIN_IDS)
def test_tables_have_contract_columns(data_dir, chain_id):
    conn = open_chain_db(data_dir, chain_id, readonly=True)
    for table, cols in EXPECTED_COLUMNS.items():
        assert _columns(conn, table) == cols, table


@pytest.mark.parametrize("chain_id", CHAIN_IDS)
def test_views_expose_chain_id_and_only_own_chain(data_dir, chain_id):
    conn = open_chain_db(data_dir, chain_id, readonly=True)
    for view in VIEW_NAMES:
        cols = _columns(conn, view)
        assert "chain_id" in cols, view
        chains = {r[0] for r in conn.execute(f"SELECT DISTINCT chain_id FROM {view}")}
        assert chains == {chain_id}, view


def test_online_orders_view_rounds_coordinates_and_hides_nothing_personal(data_dir):
    conn = open_chain_db(data_dir, "CHAIN_A", readonly=True)
    cols = _columns(conn, "v_online_orders")
    assert not {"customer_name", "phone", "address"} & set(cols)
    for lat, lng in conn.execute("SELECT lat, lng FROM v_online_orders"):
        assert round(lat, 3) == lat and round(lng, 3) == lng


EXPECTED_SOURCES = {
    "chains": ["GEN_PROGRAM_V1"],
    "stores": ["OSM_HCMC_SITES", "OSM_HCMC"],
    "skus": ["AI_PARAMS_CATALOG"],
    "daily_sales": ["GEN_FROM_AI_PARAMS_V1", "WEATHER_OPENMETEO_ARCHIVE"],
    "calendar": ["CALENDAR_VN"],
    "weather": ["WEATHER_OPENMETEO_ARCHIVE", "WEATHER_OPENMETEO_FORECAST"],
    "inventory_lots": ["GEN_FROM_AI_PARAMS_V1"],
    "pickup_points": ["OSM_HCMC_SITES", "OSM_HCMC"],
    "online_orders": ["GEN_FROM_AI_PARAMS_V1", "OSM_HCMC"],
    "assumptions": ["AI_PARAMS_DEMAND", "AI_PARAMS_ELASTICITY", "AI_PARAMS_ORDERS", "GEN_PROGRAM_V1"],
}


@pytest.mark.parametrize("chain_id", CHAIN_IDS)
def test_every_source_is_a_registered_dataset_id(data_dir, chain_id):
    reg = load_registry(data_dir)
    conn = open_chain_db(data_dir, chain_id, readonly=True)
    for table, expected in EXPECTED_SOURCES.items():
        assert sources_for(conn, [table]) == expected, table
    for table, cols in EXPECTED_COLUMNS.items():
        if "source" in cols:
            for (src,) in conn.execute(f"SELECT DISTINCT source FROM {table}"):
                assert src in reg and src != "SIMULATED", (table, src)
    for (src,) in conn.execute("SELECT DISTINCT dataset_id FROM data_sources"):
        assert src in reg
    assert (data_dir / "provenance" / "registry.json").exists()


def test_readonly_connection_rejects_writes(data_dir):
    conn = open_chain_db(data_dir, "CHAIN_B", readonly=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM stores")


def test_open_returns_rows_by_name(data_dir):
    conn = open_chain_db(data_dir, "CHAIN_C")
    row = conn.execute("SELECT chain_id, source FROM chains").fetchone()
    assert row["chain_id"] == "CHAIN_C" and row["source"] == "GEN_PROGRAM_V1"


def test_chain_db_path_rejects_unknown_chain(tmp_path):
    assert chain_db_path(tmp_path, "CHAIN_A") == tmp_path / "chains" / "CHAIN_A.sqlite"
    with pytest.raises(ValueError):
        chain_db_path(tmp_path, "../etc/passwd")


def test_open_missing_db_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        open_chain_db(tmp_path, "CHAIN_A")
