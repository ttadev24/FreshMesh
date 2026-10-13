"""Shared helpers for API tests: real generated data in a tmp dir and a deterministic fake PACO solver."""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path

from data_sim import CHAIN_IDS, chain_db_path, generate_all
from forecasting.service import TrainConfig, train_local
from provenance import write_registry
from routing.client import SolverError, SolverResponse

FAST_TRAIN = TrainConfig(epochs=2, max_train_rows=20_000)


# Fixture provenance: every table is stamped with a known test dataset id — row-level `source` where the table has
# that column, otherwise one `data_sources` entry — and the ids are registered in the data root's registry. The
# pipeline's own provenance rows are replaced, so tests assert exact provenance independently of how the data
# pipeline labels its DBs (and of which tables have a `source` column).
TABLE_IDS = {
    "chains": "test_osm_stores",
    "stores": "test_osm_stores",
    "pickup_points": "test_osm_stores",
    "skus": "test_catalog",
    "daily_sales": "test_sales",
    "inventory_lots": "test_sales",
    "online_orders": "test_orders",
    "calendar": "test_calendar",
    "weather": "test_weather",
}
OTHER_ID = "test_other"
TEST_DATASETS = {
    "test_osm_stores": ("Vị trí cửa hàng thử nghiệm", "public"),
    "test_catalog": ("Danh mục hàng thử nghiệm", "derived"),
    "test_sales": ("Bộ bán hàng thử nghiệm", "derived"),
    "test_orders": ("Đơn online thử nghiệm", "derived"),
    "test_calendar": ("Lịch thử nghiệm", "public"),
    "test_weather": ("Thời tiết thử nghiệm", "public"),
    OTHER_ID: ("Bảng khác thử nghiệm", "derived"),
}
FORECAST_SOURCES = ["test_calendar", "test_catalog", "test_osm_stores", "test_sales", "test_weather"]
ROUTING_SOURCES = ["test_orders", "test_osm_stores"]
_APP_TABLES = {"users", "drafts", "audit_log", "data_sources"}  # application records, not datasets


def _stamp_chain(con: sqlite3.Connection) -> None:
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    has_map = "data_sources" in tables
    if not has_map:
        con.execute("CREATE TABLE data_sources(table_name TEXT, dataset_id TEXT)")
    map_cols = {r[1]: r for r in con.execute("SELECT * FROM pragma_table_info('data_sources')")}
    con.execute("DELETE FROM data_sources")
    for table in tables:
        if table in _APP_TABLES or table.startswith("sqlite_"):
            continue
        ds_id = TABLE_IDS.get(table, OTHER_ID)
        cols = {r[1] for r in con.execute("SELECT * FROM pragma_table_info(?)", (table,))}
        if "source" in cols:
            con.execute(f'UPDATE "{table}" SET source = ?', (ds_id,))
            continue
        row = {"table_name": table, "dataset_id": ds_id}
        for name, info in map_cols.items():  # fill any other required column of the pipeline's schema
            if name not in row and info[3]:  # notnull
                row[name] = "*" if name == "column_name" else "dữ liệu kiểm thử"
        names = ", ".join(row)
        con.execute(
            f"INSERT INTO data_sources({names}) VALUES ({', '.join('?' * len(row))})", list(row.values())
        )


def stamp_provenance(data_dir: Path) -> None:
    for chain_id in CHAIN_IDS:
        con = sqlite3.connect(chain_db_path(data_dir, chain_id))
        try:
            with con:
                _stamp_chain(con)
        finally:
            con.close()
    write_registry(
        data_dir,
        {
            ds_id: {
                "id": ds_id,
                "name_vi": name,
                "kind": kind,
                "url": "https://example.test/" + ds_id,
                "license": "CC-BY-4.0",
                "retrieved_at": "2026-10-01",
                "description_vi": f"{name} (dữ liệu cố định của bộ kiểm thử).",
            }
            for ds_id, (name, kind) in TEST_DATASETS.items()
        },
    )


def build_data(data_dir: Path) -> Path:
    """Generate the 3 chains (seed 42), stamp fixture provenance and train small local models for each."""
    generate_all(data_dir, seed=42)
    stamp_provenance(data_dir)
    for chain_id in CHAIN_IDS:
        train_local(chain_id, data_dir=data_dir, config=FAST_TRAIN)
    return data_dir


class FakeSolver:
    """Parses the routing-PL instance text and returns a feasible-looking answer without any network.

    Customers are served in index order, a new vehicle starts when capacity would be exceeded; pickup-only
    customers (type 2) go to their first allowed locker.
    """

    def __init__(self) -> None:
        self.calls = 0

    def solve(self, instance_text: str, solver: str = "paco", size: str = "small") -> SolverResponse:
        self.calls += 1
        lines = instance_text.splitlines()
        n, m = map(int, lines[0].split())
        _, cap = map(int, lines[1].split())
        demand = [int(x) for x in lines[2 : 2 + n]]
        nodes = [tuple(map(float, ln.split())) for ln in lines[2 + n : 2 + n + 1 + n + m]]
        matrix = [ln.split() for ln in lines[2 + n + 1 + n + m :]]
        delivery = []
        for c in range(1, n + 1):
            ctype = int(nodes[c][5])
            if ctype == 2:
                delivery.append(n + 1 + matrix[c - 1].index("1"))
            else:
                delivery.append(c)
        routes, raw, current, load = [], [], [], 0
        for c in range(1, n + 1):
            if current and load + demand[c - 1] > cap:
                routes.append(current)
                current, load = [], 0
            current.append(c)
            load += demand[c - 1]
        if current:
            routes.append(current)
        objective = 0.0
        for r in routes:
            pts = [(0.0, 0.0)] + [nodes[delivery[c - 1]][:2] for c in r] + [(0.0, 0.0)]
            objective += sum(math.dist(a, b) for a, b in zip(pts, pts[1:], strict=False))
            raw.append([0, *r, 0])
        tokens = [
            ["0", *[str(c) if delivery[c - 1] == c else f"{c}({delivery[c - 1]})" for c in r], "0"]
            for r in routes
        ]
        return SolverResponse(objective, len(routes), 0.05, tokens, raw, delivery)

    def health(self) -> bool:
        return True


class BrokenSolver:
    """Solver that always fails like an unreachable container."""

    def solve(self, instance_text: str, solver: str = "paco", size: str = "small") -> SolverResponse:
        raise SolverError("cannot reach solver: connection refused")

    def health(self) -> bool:
        return False
