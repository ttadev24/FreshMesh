"""FreshMesh chain data: one SQLite database per chain (tenant isolation = separate file).

Locations (OpenStreetMap), rain (Open-Meteo) and holidays are real public data (offline snapshots in
`data_real/`); sales, prices, stock and orders are program-generated (dataset id `SOURCE` =
"GEN_PROGRAM_V1"). Every row's `source` column holds a provenance dataset id (see `provenance`).

Public API:
    SIM_AS_OF, CHAIN_IDS, SIM_BATCH_START, SIM_BATCH_WINDOW_MINUTES, ASSUMPTIONS, VIEW_NAMES
    chain_db_path(data_dir, chain_id) -> Path
    open_chain_db(data_dir, chain_id, readonly=False) -> sqlite3.Connection
    generate_all(out_dir, seed) -> dict[chain_id, Path]
    SOURCE: dataset id of program-generated rows; SITES_SOURCE: id of stores/pickup points on real OSM sites
    batch_created_range() -> (from_iso, to_iso)   # created_at range of the current online batch
    assumptions_markdown() / assumptions_sections()
"""

import sqlite3
from datetime import timedelta
from pathlib import Path

from data_sim.assumptions import (
    ASSUMPTION_DESCRIPTIONS_VI,
    ASSUMPTIONS,
    SIM_AS_OF,
    SIM_BATCH_START,
    SIM_BATCH_WINDOW_MINUTES,
    assumptions_markdown,
    assumptions_sections,
)
from data_sim.catalog import CHAINS
from data_sim.generate import SITES_SOURCE, SOURCE, counter_point_id, generate_all
from data_sim.schema import VIEW_NAMES

CHAIN_IDS: tuple[str, ...] = tuple(c.chain_id for c in CHAINS)

__all__ = [
    "ASSUMPTIONS",
    "ASSUMPTION_DESCRIPTIONS_VI",
    "CHAIN_IDS",
    "SIM_AS_OF",
    "SIM_BATCH_START",
    "SIM_BATCH_WINDOW_MINUTES",
    "SITES_SOURCE",
    "SOURCE",
    "VIEW_NAMES",
    "assumptions_markdown",
    "assumptions_sections",
    "batch_created_range",
    "chain_db_path",
    "counter_point_id",
    "generate_all",
    "open_chain_db",
]


def chain_db_path(data_dir: Path | str, chain_id: str) -> Path:
    if chain_id not in CHAIN_IDS:
        raise ValueError(f"unknown chain_id: {chain_id!r}")
    return Path(data_dir) / "chains" / f"{chain_id}.sqlite"


def open_chain_db(data_dir: Path | str, chain_id: str, readonly: bool = False) -> sqlite3.Connection:
    """Open a chain DB with `sqlite3.Row` rows. `readonly=True` uses a `mode=ro` URI connection."""
    path = chain_db_path(data_dir, chain_id)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run `uv run python -m data_sim --out {data_dir}`")
    if readonly:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def batch_created_range() -> tuple[str, str]:
    """ISO bounds `[from, to)` of `online_orders.created_at` for the current batch.

    Minute 0 of the batch's earliest/latest windows is `SIM_BATCH_START` (= `to`).
    """
    start = SIM_BATCH_START - timedelta(minutes=SIM_BATCH_WINDOW_MINUTES)
    return start.isoformat(), SIM_BATCH_START.isoformat()
