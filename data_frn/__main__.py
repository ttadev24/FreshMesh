"""``uv run --group bench python -m data_frn download|audit [--data data] [--docs docs/experiments]``."""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m data_frn", description=__doc__)
    commands = ["download", "audit", "forecast", "forecast-report", "inventory", "inventory-report", "elasticity"]
    parser.add_argument("command", choices=commands)
    parser.add_argument("--shelf-life", type=int, default=2)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--docs", type=Path, default=Path("docs/experiments"))
    parser.add_argument("--history", choices=["recovered", "observed"], default="recovered")
    parser.add_argument("--cities", type=int, nargs="+", default=None)
    parser.add_argument("--protocol", choices=["frn-v1", "frn-v1.1"], default="frn-v1")
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
        from data_frn.sums_io import sums_path

        paths = {h: sums_path(args.docs / f"frn_forecast_sums_{h}.csv") for h in ("recovered", "observed")}
        print(forecast_report({h: p for h, p in paths.items() if p}, args.docs))
    elif args.command == "elasticity":
        from data_frn.elasticity import run as elasticity_run

        print(elasticity_run(args.data, args.docs, cities=args.cities))
    elif args.command == "inventory":
        from data_frn.inventory_bench import run as inventory_run

        print(inventory_run(args.data, args.docs, shelf_life=args.shelf_life, cities=args.cities,
                            version=args.protocol))  # fmt: skip
    else:
        from data_frn.inventory_report import write_report as inventory_report
        from data_frn.inventory_report_v11 import write_report as inventory_report_v11
        from data_frn.sums_io import sums_path

        found: dict[str, dict] = {"sums_": {}, "v11_sums_": {}}
        for tag, life in ((t, n) for t in found for n in (1, 2, 3)):
            if p := sums_path(args.docs / f"frn_inventory_{tag}L{life}.csv"):
                found[tag][life] = p
        print(inventory_report(found["sums_"], args.docs))
        if found["v11_sums_"]:  # amendment frn-v1.1, reported after (never instead of) frn-v1
            print(inventory_report_v11(found["sums_"], found["v11_sums_"], args.docs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
