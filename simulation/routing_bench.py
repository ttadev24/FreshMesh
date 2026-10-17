"""Routing benchmark (spec §1.4 #4, §6): PACO / SA / ALNS vs "mỗi đơn một chuyến" on every store's demo batch.

* Batches are built exactly as the API builds them (``RoutingService.build_batch``: current 45-minute
  window, fleet 4 × 30 units, ``RoutingConfig()``), so PACO results share the API cache
  (``<data_dir>/cache/routing``) and the batch hash.
* PACO goes through the routing-PL HTTP service (``POST /solve``). SA is selectable there too
  (``solver = "sa"``) but the routing-PL SA binary aborts with ``std::out_of_range`` on FreshMesh instances
  (API and CLI, small and medium batches; see docs/experiments/routing-benchmark.md), so it is opt-in only.
* ALNS is not exposed by the service; it is run with ``docker exec <container> /app/backend/bin/test
  --solver alns`` (same binary, ALNS parameter file of the routing-PL repo) and cached the same way.
* Baseline = ``routing.baseline.one_trip_per_order`` on the same routable orders; its "vehicles" are trips
  (one dispatch per order). Each trip goes straight to its order from minute 0 and screening already removed
  orders unreachable even directly, so the baseline has no late stops by construction.
* Dispatcher baseline = ``routing.dispatch_baseline.zone_sweep`` (protocol frn-v1 §6, R1): bearing zones,
  nearest-neighbour trips, the batch's fleet reused trip after trip; "vehicles" are its trips.
* ``detour_factor`` 1,3 is the primary setting (``routing_benchmark.csv``); other values are sensitivity runs
  written to ``routing_benchmark_detour<factor×100>.csv``. A ``tag`` (``_v12``: frn-v1.2, the solver with the stop
  service time) names a separate result set. Every row records the solver build it was solved with.
* Result sets that hold a pre-registered verdict (R1: dispatcher rows present) are frozen: a run refuses to
  rewrite them unless ``overwrite_frozen`` is set.
* Solves run sequentially (the solver container is shared with the API).
"""

from __future__ import annotations

import csv
import json
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from api.config import FLEET_CAPACITY, FLEET_VEHICLES
from api.errors import ApiError
from api.provenance_view import ROUTING_TABLES
from api.repo import ChainRepo
from api.routing_service import RoutingService
from data_sim import CHAIN_IDS
from forecasting.service import data_sources
from routing.baseline import one_trip_per_order
from routing.client import SolverClient, SolverError, SolverResponse
from routing.config import RoutingConfig
from routing.dispatch_baseline import zone_sweep
from routing.models import Batch, RoutePlan

RESULTS_CSV = "routing_benchmark.csv"
BASELINE = "one_trip_per_order"
DISPATCHER = "zone_sweep"
PRIMARY_DETOUR = 1.3
DEFAULT_CONTAINER = "freshmesh-solver"
DEFAULT_METHODS = ("paco", "alns")  # SA is opt-in: the routing-PL SA binary crashes on these instances
ALNS_PARAMS = "/app/src/parameters/alns.param.yaml"
CSV_FIELDS = (
    "chain_id",
    "store_id",
    "method",
    "status",
    "n_orders",
    "n_routable",
    "at_risk",
    "road_km",
    "vehicles",
    "late_stops",
    "exceeds_fleet",
    "runtime_s",
    "wall_s",
    "cached",
    "batch_hash",
    "source",
    "solver_build",
)


class DockerExecSolver:
    """``Solver`` for routing-PL solvers that only exist in the container CLI (ALNS)."""

    def __init__(
        self, container: str = DEFAULT_CONTAINER, params: str = ALNS_PARAMS, timeout_s: float = 300.0
    ):
        self.container = container
        self.params = params
        self.timeout_s = timeout_s

    def solve(self, instance_text: str, solver: str = "alns", size: str = "small") -> SolverResponse:
        script = (
            "cat > /tmp/freshmesh_bench.txt && cd /app/src && /app/backend/bin/test "
            f"--solver {solver} --params {self.params} --instance-file /tmp/freshmesh_bench.txt "
            f"--size {size} --full-solution"
        )
        try:
            proc = subprocess.run(
                ["docker", "exec", "-i", self.container, "sh", "-c", script],
                input=instance_text,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SolverError(f"cannot reach solver: {exc}") from exc
        if proc.returncode != 0:
            raise SolverError(f"{solver} exited with code {proc.returncode}: {proc.stderr[:200]}")
        start = proc.stdout.find("{")
        if start < 0:
            raise SolverError(f"no JSON in {solver} output")
        data = json.loads(proc.stdout[start:])
        return SolverResponse(
            objective=float(data["objective"]),
            vehicles=int(data["vehicles"]),
            runtime=float(data["runtime"]),
            routes=data["routes"],
            raw_routes=data["raw_routes"],
            delivery_nodes=data["delivery_nodes"],
        )


def _plan_row(plan: RoutePlan) -> dict[str, Any]:
    return {
        "road_km": round(plan.road_km, 3),
        "vehicles": plan.vehicles_used,
        "late_stops": sum(1 for r in plan.routes for s in r.stops if s.late),
        "exceeds_fleet": int(plan.exceeds_fleet),
        "runtime_s": round(plan.runtime_s, 2),
    }


def benchmark_batch(
    services: dict[str, RoutingService], batch: Batch, cfg: RoutingConfig
) -> list[dict[str, Any]]:
    """One row per method (baseline first) for one batch; solver failures become ``status`` rows."""
    base = one_trip_per_order(batch, cfg)
    rows: list[dict[str, Any]] = [
        {
            "method": BASELINE,
            "status": "ok",
            "road_km": round(base.road_km, 3),
            "vehicles": base.trips,
            "late_stops": 0,
            "exceeds_fleet": int(base.trips > batch.num_vehicles),
            "runtime_s": 0.0,
            "wall_s": 0.0,
            "cached": 0,
            "batch_hash": "",
            "n_routable": base.trips,
        }
    ]
    zs = zone_sweep(batch, cfg)
    rows.append(
        {
            "method": DISPATCHER,
            "status": "ok",
            **_plan_row(zs),
            "wall_s": round(zs.runtime_s, 2),
            "cached": 0,
            "batch_hash": "",
            "n_routable": sum(len(r.stops) for r in zs.routes),
        }
    )
    for method, svc in services.items():
        t0 = time.perf_counter()
        try:
            plan, cached, key = svc.solve(batch)
        except ApiError as exc:
            rows.append(
                {
                    "method": method,
                    "status": f"error: {exc.code}",
                    "wall_s": round(time.perf_counter() - t0, 1),
                }
            )
            continue
        rows.append(
            {
                "method": method,
                "status": "ok",
                **_plan_row(plan),
                "wall_s": round(time.perf_counter() - t0, 1),
                "cached": int(cached),
                "batch_hash": key[:16],
                "n_routable": sum(len(r.stops) for r in plan.routes),
            }
        )
    return rows


def run_routing_benchmark(
    *,
    data_dir: Path,
    docs_dir: Path,
    solver_url: str,
    methods: Sequence[str] = DEFAULT_METHODS,
    chain_ids: Sequence[str] = CHAIN_IDS,
    container: str = DEFAULT_CONTAINER,
    progress: Callable[[str], None] | None = None,
    detour_factor: float = PRIMARY_DETOUR,
    tag: str = "",
    solver_build: str = "",
    overwrite_frozen: bool = False,
) -> list[dict[str, Any]]:
    """Benchmark every store of every chain; writes ``docs_dir/<results_name(detour_factor, tag)>``."""
    target = Path(docs_dir) / results_name(detour_factor, tag)
    if not overwrite_frozen and any(r["method"] == DISPATCHER for r in read_results(target)):
        raise ValueError(f"{target} holds a pre-registered R1 result; use another tag or overwrite_frozen")
    data_dir = Path(data_dir)
    cache = data_dir / "cache"
    http = SolverClient(solver_url, timeout_s=RoutingConfig().solver_timeout_s)
    services: dict[str, RoutingService] = {}
    for m in methods:
        client = DockerExecSolver(container) if m == "alns" else http
        services[m] = RoutingService(
            cache,
            client,
            cfg=RoutingConfig(solver=m, detour_factor=detour_factor),
            fleet_vehicles=FLEET_VEHICLES,
            fleet_capacity=FLEET_CAPACITY,
        )
    cfg = RoutingConfig(detour_factor=detour_factor)
    builder = RoutingService(
        cache, None, cfg=cfg, fleet_vehicles=FLEET_VEHICLES, fleet_capacity=FLEET_CAPACITY
    )
    out: list[dict[str, Any]] = []
    for chain_id in chain_ids:
        repo = ChainRepo(data_dir, chain_id)
        sources = ";".join(data_sources(chain_id, data_dir, ROUTING_TABLES))
        for store in repo.stores():
            batch, _ = builder.build_batch(repo, store.store_id)
            rows = benchmark_batch(services, batch, cfg)
            n_routable = rows[0]["n_routable"]
            for r in rows:
                r.update(
                    chain_id=chain_id,
                    store_id=store.store_id,
                    n_orders=len(batch.orders),
                    at_risk=len(batch.orders) - n_routable,
                    source=sources,
                    solver_build=solver_build,
                )
                out.append(r)
                if progress:
                    progress(
                        f"{store.store_id} {r['method']}: {r['status']} km={r.get('road_km')} "
                        f"veh={r.get('vehicles')} wall={r.get('wall_s')}s"
                    )
            _merge_write(target, out)
    return out


def results_name(detour_factor: float, tag: str = "") -> str:
    base = f"routing_benchmark{tag}"
    if detour_factor == PRIMARY_DETOUR:
        return f"{base}.csv"
    code = f"{detour_factor:g}".replace(".", "")  # 1.58 -> 158, 1.585 -> 1585 (no collision)
    return f"{base}_detour{code}.csv"


def _merge_write(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    """Replace the rows of the (store, method) pairs in ``rows``; keep every other row of the CSV."""
    done = {(r["store_id"], r["method"]) for r in rows}
    old = [r for r in read_results(path) if (r["store_id"], r["method"]) not in done]
    write_results(path, sorted([*old, *rows], key=lambda r: (r["chain_id"], r["store_id"])))


def write_results(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    tmp = Path(path).with_suffix(".csv.tmp")  # readers never see a half-written file
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(CSV_FIELDS))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_FIELDS})
    tmp.replace(path)


def read_results(path: Path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))
