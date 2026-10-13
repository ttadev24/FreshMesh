"""Measure routing-PL PACO runtime on simulated batches of 25/50/100 orders.

Usage: uv run python scripts/probe_solver.py [--url http://localhost:8000] [--runs 3]
"""
import argparse
import math
import os
import random
import statistics
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from routing.client import SolverClient
from routing.models import Batch, DeliveryMode, Order, PickupPoint, Store
from routing.planner import optimize_routes, solver_size

LAT0, LNG0 = 10.7340, 106.7210


def _offset(rng: random.Random, radius_km: float) -> tuple[float, float]:
    r = radius_km * math.sqrt(rng.random())
    a = rng.random() * 2 * math.pi
    return (
        LAT0 + r * math.cos(a) / 110.574,
        LNG0 + r * math.sin(a) / (111.320 * math.cos(math.radians(LAT0))),
    )


def simulated_batch(n: int, seed: int) -> Batch:
    rng = random.Random(seed)
    points = [PickupPoint(f"PP{i}", *_offset(rng, 2.5)) for i in range(4)]
    modes = [DeliveryMode.HOME, DeliveryMode.FLEXIBLE, DeliveryMode.PICKUP]
    orders = []
    for i in range(n):
        mode = rng.choice(modes)
        start = rng.choice([0, 30, 60])
        orders.append(
            Order(
                f"D{i:03d}", *_offset(rng, 4.0), rng.randint(1, 3), start, start + 120, mode,
                3.0, rng.choice(points).point_id if mode == DeliveryMode.PICKUP else None,
            )
        )
    return Batch(Store("PROBE", LAT0, LNG0), orders, points, num_vehicles=max(4, n // 4), vehicle_capacity=12)


def _default_url() -> str:
    url = os.environ.get("FRESHMESH_SOLVER_URL")
    if url:
        return url
    port = os.environ.get("FRESHMESH_SOLVER_PORT")
    if port:
        return f"http://localhost:{port}"
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("FRESHMESH_SOLVER_URL="):
                return line.split("=", 1)[1].strip()
    return "http://localhost:8000"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=_default_url())
    p.add_argument("--runs", type=int, default=3)
    args = p.parse_args()
    client = SolverClient(args.url)
    print("| orders | size | wall s (median) | solver s (median) | km (median) | vehicles |")
    print("|---|---|---|---|---|---|")
    for n in (25, 50, 100):
        walls, solver_s, kms, vehicles = [], [], [], []
        for run in range(args.runs):
            t0 = time.perf_counter()
            plan = optimize_routes(simulated_batch(n, seed=run), client)
            walls.append(time.perf_counter() - t0)
            solver_s.append(plan.runtime_s)
            kms.append(plan.road_km)
            vehicles.append(plan.vehicles_used)
        print(
            f"| {n} | {solver_size(n)} | {statistics.median(walls):.1f} | "
            f"{statistics.median(solver_s):.1f} | {statistics.median(kms):.1f} | {statistics.median(vehicles):.0f} |"
        )


if __name__ == "__main__":
    main()
