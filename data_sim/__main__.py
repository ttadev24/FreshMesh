import argparse
import sqlite3
from pathlib import Path

from data_sim import SOURCE, generate_all
from provenance import label_vi, load_registry, sources_for

TABLES = ("stores", "pickup_points", "daily_sales", "inventory_lots", "online_orders", "weather", "calendar")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build FreshMesh chain databases: real public locations/weather/holidays + "
        f"program-generated sales, stock and orders ({SOURCE})"
    )
    parser.add_argument("--out", type=Path, default=Path("data"), help="data root (default: data)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    paths = generate_all(args.out, args.seed)
    registry = load_registry(args.out)
    print("Nguồn dữ liệu theo bảng (chi tiết: `uv run python -m provenance show`):")
    for chain_id, path in paths.items():
        conn = sqlite3.connect(path)
        try:
            n_stores = conn.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
            n_sales = conn.execute("SELECT COUNT(*) FROM daily_sales").fetchone()[0]
            n_orders = conn.execute("SELECT COUNT(*) FROM online_orders").fetchone()[0]
            by_table = {t: sources_for(conn, [t]) for t in TABLES}
        finally:
            conn.close()
        print(f"{chain_id}: {path} stores={n_stores} daily_sales={n_sales} online_orders={n_orders}")
        for table, ids in by_table.items():
            print(f"    {table}: " + "; ".join(f"{i} — {label_vi(i, registry)}" for i in ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
