"""Shared fixtures for agent tests: a small two-chain SQLite DB with the query_data views."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE stores(store_id TEXT PRIMARY KEY, chain_id TEXT, name TEXT, lat REAL, lng REAL, area_type TEXT,
                    is_new INT, source TEXT);
CREATE TABLE skus(sku_id TEXT PRIMARY KEY, chain_id TEXT, name TEXT, category TEXT, is_fresh INT,
                  unit_cost REAL, unit_price REAL, source TEXT);
CREATE TABLE daily_sales(store_id TEXT, sku_id TEXT, date TEXT, units INT, price REAL, source TEXT);
CREATE TABLE inventory_lots(store_id TEXT, sku_id TEXT, qty INT, expires_on TEXT, source TEXT);
CREATE TABLE online_orders(order_id TEXT PRIMARY KEY, store_id TEXT, created_at TEXT, lat REAL, lng REAL,
                           demand INT, delivery_mode TEXT, customer_name TEXT, phone TEXT, source TEXT);
CREATE TABLE users(user_id TEXT PRIMARY KEY, chain_id TEXT, username TEXT, password_hash TEXT);
CREATE VIEW v_stores AS SELECT store_id, chain_id, name, round(lat, 3) AS lat, round(lng, 3) AS lng,
    area_type, is_new, source FROM stores;
CREATE VIEW v_skus AS SELECT sku_id, chain_id, name, category, is_fresh, unit_cost, unit_price, source FROM skus;
CREATE VIEW v_sales_daily AS SELECT d.store_id, s.chain_id, d.sku_id, d.date, d.units, d.price, d.source
    FROM daily_sales d JOIN stores s ON s.store_id = d.store_id;
CREATE VIEW v_stock AS SELECT i.store_id, s.chain_id, i.sku_id, i.qty, i.expires_on, i.source
    FROM inventory_lots i JOIN stores s ON s.store_id = i.store_id;
CREATE VIEW v_online_orders AS SELECT o.order_id, o.store_id, s.chain_id, o.created_at,
    round(o.lat, 3) AS lat, round(o.lng, 3) AS lng, o.demand, o.delivery_mode, o.source
    FROM online_orders o JOIN stores s ON s.store_id = o.store_id;
"""


def make_chain_db(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany(
        "INSERT INTO stores VALUES (?,?,?,?,?,?,?,'test_fixture')",
        [
            ("A1", "CHAIN_A", "CH Quận 1", 10.7765, 106.7009, "market", 0),
            ("A2", "CHAIN_A", "CH Quận 3", 10.7843, 106.6844, "residential", 1),
            ("B1", "CHAIN_B", "CH Bình Thạnh", 10.8106, 106.7091, "office", 0),
        ],
    )
    con.executemany(
        "INSERT INTO skus VALUES (?,?,?,?,?,?,?,'test_fixture')",
        [
            ("RAU1", "CHAIN_A", "Rau muống", "rau", 1, 8000, 12000),
            ("THIT1", "CHAIN_A", "Thịt heo", "thit", 1, 90000, 120000),
            ("RAU1B", "CHAIN_B", "Rau muống", "rau", 1, 8500, 12500),
        ],
    )
    con.executemany(
        "INSERT INTO daily_sales VALUES (?,?,?,?,?,'test_fixture')",
        [
            ("A1", "RAU1", "2026-09-29", 40, 12000),
            ("A1", "RAU1", "2026-09-30", 50, 12000),
            ("A2", "THIT1", "2026-09-30", 12, 120000),
            ("B1", "RAU1B", "2026-09-30", 999, 12500),
        ],
    )
    con.executemany(
        "INSERT INTO inventory_lots VALUES (?,?,?,?,'test_fixture')",
        [
            ("A1", "RAU1", 30, "2026-10-01"),
            ("B1", "RAU1B", 77, "2026-10-01"),
        ],
    )
    con.executemany(
        "INSERT INTO online_orders VALUES (?,?,?,?,?,?,?,?,?,'test_fixture')",
        [
            ("O1", "A1", "2026-09-30T09:00", 10.771234, 106.701234, 2, "home", "Nguyễn Văn A", "0901234567"),
            ("O2", "B1", "2026-09-30T09:10", 10.812345, 106.712345, 1, "pickup", "Trần Thị B", "0912345678"),
        ],
    )
    con.execute("INSERT INTO users VALUES ('u1','CHAIN_A','owner_a','pbkdf2$secret')")
    con.commit()
    con.close()
    return path


# ---------------------------------------------------------------- programmable fake LLM

from agent.llm import LLMRequest, LLMResponse, ToolCall  # noqa: E402


def tool_response(text, *calls):
    """calls: (id, name, args) tuples."""
    content = [{"type": "text", "text": text}] if text else []
    tool_calls = [ToolCall(i, n, a) for i, n, a in calls]
    content += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.args} for c in tool_calls]
    return LLMResponse(text, tool_calls, "tool_use", content)


def text_response(text, stop_reason="end_turn"):
    return LLMResponse(text, [], stop_reason, [{"type": "text", "text": text}])


class SequenceClient:
    """Returns pre-programmed responses in order (or computed by a callable) and records requests."""

    name = "sequence"

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[LLMRequest] = []

    def complete(self, request, on_text=None):
        self.requests.append(request)
        nxt = self.responses.pop(0)
        return nxt(request) if callable(nxt) else nxt
