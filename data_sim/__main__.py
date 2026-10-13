import argparse
import sqlite3
from pathlib import Path

from data_sim import SOURCE, generate_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate FreshMesh simulated chain databases")
    parser.add_argument("--out", type=Path, default=Path("data"), help="data root (default: data)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    paths = generate_all(args.out, args.seed)
    print(f"Dữ liệu giả lập ({SOURCE}) — simulated data, not real sales:")
    for chain_id, path in paths.items():
        conn = sqlite3.connect(path)
        try:
            n_stores = conn.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
            n_sales = conn.execute("SELECT COUNT(*) FROM daily_sales").fetchone()[0]
            n_orders = conn.execute("SELECT COUNT(*) FROM online_orders").fetchone()[0]
        finally:
            conn.close()
        print(
            f"{chain_id} [{SOURCE}]: {path} stores={n_stores} daily_sales={n_sales} online_orders={n_orders}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
