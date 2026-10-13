"""CLI: ``uv run python -m simulation sim30 --chain CHAIN_A [--seed N]`` and ``... routing-benchmark``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from api.config import REPO_ROOT, default_solver_url
from data_sim import CHAIN_IDS
from simulation import report, routing_bench, sim30

DOCS_DIR = REPO_ROOT / "docs" / "experiments"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m simulation", description="FreshMesh experiments (SIMULATED data)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sim30", help="30-day inventory simulation (docs/experiments/sim30-protocol.md)")
    s.add_argument("--chain", choices=[*CHAIN_IDS, "all"], default="all")
    s.add_argument(
        "--seed",
        type=int,
        action="append",
        help=f"simulation seed (repeatable); default = confirmatory seeds {sim30.CONFIRMATORY_SEEDS}; "
        f"non-confirmatory seeds (e.g. dev seed {sim30.DEV_SEED}) are printed, never written",
    )
    s.add_argument("--policy", action="append", choices=sim30.ALL_POLICIES, help="default: all arms")
    s.add_argument("--days", type=int, default=sim30.N_DAYS)
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--data-dir", type=Path, default=Path("data"))
    s.add_argument("--docs-dir", type=Path, default=DOCS_DIR)

    r = sub.add_parser("routing-benchmark", help="PACO / SA / ALNS vs one trip per order on the demo batches")
    r.add_argument("--chain", choices=[*CHAIN_IDS, "all"], default="all")
    r.add_argument(
        "--method",
        action="append",
        choices=("paco", "sa", "alns"),
        help="default: paco alns (sa is opt-in: it crashes on these instances)",
    )
    r.add_argument("--solver-url", default=None, help="default: FRESHMESH_SOLVER_URL / .env")
    r.add_argument("--container", default=routing_bench.DEFAULT_CONTAINER, help="solver container (ALNS)")
    r.add_argument("--data-dir", type=Path, default=Path("data"))
    r.add_argument("--docs-dir", type=Path, default=DOCS_DIR)

    sub.add_parser("summary", help="print experiment_summary(docs/experiments) as JSON")
    args = p.parse_args(argv)

    if args.cmd == "sim30":
        chains = list(CHAIN_IDS) if args.chain == "all" else [args.chain]
        seeds = args.seed or list(sim30.CONFIRMATORY_SEEDS)
        rows = sim30.run_sim30(
            chains,
            seeds,
            data_dir=args.data_dir,
            docs_dir=args.docs_dir,
            policies=args.policy or sim30.ALL_POLICIES,
            n_days=args.days,
            workers=args.workers,
            progress=print,
        )
        for row in rows:
            print(
                f"{row['chain_id']} seed {row['seed']} {row['policy']:<31} waste {row['waste_pct']:5.1f}%  "
                f"stockout {row['stockout_pct']:5.1f}%  profit {row['net_profit_vnd'] / 1e6:8.1f} M đ"
            )
        if any(row["seed"] in sim30.CONFIRMATORY_SEEDS and row["days"] == sim30.N_DAYS for row in rows):
            summary = report.write_sim30_report(args.docs_dir)
            print(json.dumps(summary["overall_pass"]))
        return 0
    if args.cmd == "routing-benchmark":
        chains = list(CHAIN_IDS) if args.chain == "all" else [args.chain]
        routing_bench.run_routing_benchmark(
            data_dir=args.data_dir,
            docs_dir=args.docs_dir,
            solver_url=args.solver_url or default_solver_url(),
            methods=args.method or routing_bench.DEFAULT_METHODS,
            chain_ids=chains,
            container=args.container,
            progress=print,
        )
        summary = report.write_routing_report(args.docs_dir)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(report.experiment_summary(DOCS_DIR), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
