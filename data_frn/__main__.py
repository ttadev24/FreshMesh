"""``uv run --group bench python -m data_frn download|audit [--data data] [--docs docs/experiments]``."""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m data_frn", description=__doc__)
    parser.add_argument(
        "command", choices=["download", "audit", "forecast", "forecast-report", "inventory", "inventory-report"]
    )
    parser.add_argument("--shelf-life", type=int, default=2)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--docs", type=Path, default=Path("docs/experiments"))
    parser.add_argument("--history", choices=["recovered", "observed"], default="recovered")
    parser.add_argument("--cities", type=int, nargs="+", default=None)
    args = parser.parse_args(argv)
    if args.command == "download":
        from data_frn.download import ensure_files

        for split, path in ensure_files(args.data).items():
            print(f"{split}: {path} (sha256 verified)")
    elif args.command == "audit":
        from data_frn.audit import audit, write_report

        print(write_report(audit(args.data), args.docs))
    elif args.command == "forecast":
        from data_frn.forecast_bench import run

        print(run(args.data, args.docs, history=args.history, cities=args.cities))
    elif args.command == "forecast-report":
        from data_frn.forecast_report import write_report as forecast_report

        paths = {h: args.docs / f"frn_forecast_sums_{h}.csv" for h in ("recovered", "observed")}
        print(forecast_report({h: p for h, p in paths.items() if p.exists()}, args.docs))
    elif args.command == "inventory":
        from data_frn.inventory_bench import run as inventory_run

        print(inventory_run(args.data, args.docs, shelf_life=args.shelf_life, cities=args.cities))
    else:
        from data_frn.inventory_report import write_report as inventory_report

        paths = {life: args.docs / f"frn_inventory_sums_L{life}.csv" for life in (1, 2, 3)}
        print(inventory_report({life: p for life, p in paths.items() if p.exists()}, args.docs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
