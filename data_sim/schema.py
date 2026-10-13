"""SQLite schema (master plan "DB schema") and the whitelisted read-only views."""

import datetime as dt

TABLES_DDL = """
CREATE TABLE chains (
    chain_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE stores (
    store_id TEXT PRIMARY KEY,
    chain_id TEXT NOT NULL REFERENCES chains(chain_id),
    name TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    area_type TEXT NOT NULL CHECK (area_type IN ('residential','market','office')),
    opened_date TEXT NOT NULL,
    history_days INT NOT NULL,
    is_new INT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE skus (
    sku_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    is_fresh INT NOT NULL,
    shelf_life_days INT NOT NULL,
    unit_cost REAL NOT NULL,
    unit_price REAL NOT NULL,
    salvage_price REAL NOT NULL,
    moq INT NOT NULL,
    supplier_id TEXT NOT NULL,
    cold_storage_units REAL NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE daily_sales (
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    sku_id TEXT NOT NULL REFERENCES skus(sku_id),
    date TEXT NOT NULL,
    units INT NOT NULL,
    price REAL NOT NULL,
    promo INT NOT NULL,
    rain_mm REAL NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (store_id, sku_id, date)
);
CREATE TABLE calendar (
    date TEXT PRIMARY KEY,
    dow INT NOT NULL,
    lunar_month INT NOT NULL,
    lunar_day INT NOT NULL,
    is_tet INT NOT NULL,
    is_ram INT NOT NULL,
    is_mung1 INT NOT NULL,
    is_holiday INT NOT NULL
);
CREATE TABLE weather (
    date TEXT PRIMARY KEY,
    rain_mm REAL NOT NULL
);
CREATE TABLE inventory_lots (
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    sku_id TEXT NOT NULL REFERENCES skus(sku_id),
    qty INT NOT NULL,
    received_date TEXT NOT NULL,
    expires_on TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE pickup_points (
    pickup_point_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    name TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    earliest INT NOT NULL,
    latest INT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE online_orders (
    order_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    created_at TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    demand INT NOT NULL,
    earliest INT NOT NULL,
    latest INT NOT NULL,
    service INT NOT NULL,
    delivery_mode TEXT NOT NULL CHECK (delivery_mode IN ('home','pickup','flexible')),
    pickup_point_id TEXT NULL REFERENCES pickup_points(pickup_point_id),
    source TEXT NOT NULL
);
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    chain_id TEXT NOT NULL REFERENCES chains(chain_id),
    username TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('owner','store_manager')),
    store_id TEXT NULL REFERENCES stores(store_id),
    password_hash TEXT NOT NULL
);
CREATE TABLE drafts (
    draft_id TEXT PRIMARY KEY,
    chain_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft','approved','rejected','dispatched')),
    created_by TEXT,
    created_at TEXT,
    decided_at TEXT,
    decided_by TEXT,
    source TEXT NOT NULL DEFAULT 'SIMULATED'
);
CREATE TABLE audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    actor TEXT,
    event TEXT NOT NULL,
    payload_json TEXT
);
CREATE TABLE assumptions (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    description_vi TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE INDEX idx_sales_date ON daily_sales(date);
CREATE INDEX idx_lots_store_sku ON inventory_lots(store_id, sku_id);
CREATE INDEX idx_orders_store_created ON online_orders(store_id, created_at);
"""

VIEW_NAMES: tuple[str, ...] = ("v_sales_daily", "v_stock", "v_stores", "v_skus", "v_online_orders")


def views_ddl(as_of: dt.date) -> str:
    """Whitelisted views for query_data. Every view exposes chain_id.

    `as_of` is a literal so `v_stock.days_to_expiry` never depends on the wall clock.
    """
    as_of_s = as_of.isoformat()
    return f"""
CREATE VIEW v_stores AS
SELECT chain_id, store_id, name, lat, lng, area_type, opened_date, history_days, is_new, source
FROM stores;

CREATE VIEW v_skus AS
SELECT c.chain_id, k.sku_id, k.name, k.category, k.is_fresh, k.shelf_life_days, k.unit_cost,
       k.unit_price, k.salvage_price, k.moq, k.supplier_id, k.cold_storage_units, k.source
FROM skus k CROSS JOIN chains c;

CREATE VIEW v_sales_daily AS
SELECT s.chain_id, d.store_id, s.name AS store_name, d.sku_id, k.name AS sku_name, k.category,
       d.date, d.units, d.price, d.units * d.price AS revenue, d.promo, d.rain_mm, d.source
FROM daily_sales d
JOIN stores s ON s.store_id = d.store_id
JOIN skus k ON k.sku_id = d.sku_id;

CREATE VIEW v_stock AS
SELECT s.chain_id, l.store_id, s.name AS store_name, l.sku_id, k.name AS sku_name, k.category,
       k.is_fresh, l.qty, l.received_date, l.expires_on,
       CAST(julianday(l.expires_on) - julianday('{as_of_s}') AS INTEGER) AS days_to_expiry,
       l.source
FROM inventory_lots l
JOIN stores s ON s.store_id = l.store_id
JOIN skus k ON k.sku_id = l.sku_id;

CREATE VIEW v_online_orders AS
SELECT s.chain_id, o.order_id, o.store_id, o.created_at,
       ROUND(o.lat, 3) AS lat, ROUND(o.lng, 3) AS lng,
       o.demand, o.earliest, o.latest, o.service, o.delivery_mode, o.pickup_point_id, o.source
FROM online_orders o
JOIN stores s ON s.store_id = o.store_id;
"""
