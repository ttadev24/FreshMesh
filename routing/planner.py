import math
import re
from typing import Protocol

from routing.client import SolverError, SolverResponse
from routing.config import RoutingConfig
from routing.geo import TravelPlane
from routing.instance import build_instance
from routing.models import Batch, RoutePlan, Stop, VehicleRoute
from routing.validate import Screening, screen_orders

_TOKEN = re.compile(r"^(\d+)(?:\((\d+)\))?$")


class Solver(Protocol):
    def solve(self, instance_text: str, solver: str = ..., size: str = ...) -> SolverResponse: ...


def solver_size(n_orders: int) -> str:
    """Pick the routing-PL parameter block tuned for this instance size."""
    if n_orders <= 25:
        return "small"
    if n_orders <= 50:
        return "medium"
    return "large"


def _map_routes(resp: SolverResponse, screening: Screening, cfg: RoutingConfig) -> list[VehicleRoute]:
    orders = screening.routable
    n = len(orders)
    seen: set[int] = set()
    routes: list[VehicleRoute] = []
    for raw in resp.routes:
        stops: list[Stop] = []
        time, cx, cy = 0, 0.0, 0.0
        for token in raw:
            if token == "0":
                continue
            m = _TOKEN.match(token)
            if not m:
                raise SolverError(f"inconsistent solver output: bad token {token!r}")
            cust = int(m.group(1))
            node = int(m.group(2)) if m.group(2) else cust
            if not 1 <= cust <= n or cust in seen:
                raise SolverError(f"inconsistent solver output: customer {cust}")
            if cust - 1 >= len(resp.delivery_nodes) or resp.delivery_nodes[cust - 1] != node:
                raise SolverError(f"inconsistent solver output: delivery node of customer {cust}")
            seen.add(cust)
            r = orders[cust - 1]
            if node == cust:
                kind, point_id, tx, ty = "home", None, r.x, r.y
                earliest, latest = r.earliest, r.latest
            else:
                locker = screening.lockers[node - n - 1]
                kind, point_id, tx, ty = "pickup", locker.point.point_id, locker.x, locker.y
                earliest, latest = 0, cfg.shift_minutes
            arr = time + int(math.hypot(tx - cx, ty - cy))
            eta = max(arr, earliest)
            stops.append(Stop(r.order.order_id, kind, point_id, eta, eta > latest))
            time, cx, cy = eta + r.service, tx, ty
        if stops:
            routes.append(VehicleRoute(stops))
    if len(seen) != n:
        missing = sorted(set(range(1, n + 1)) - seen)
        raise SolverError(f"inconsistent solver output: customers {missing} not routed")
    return routes


def optimize_routes(batch: Batch, client: Solver, cfg: RoutingConfig = RoutingConfig()) -> RoutePlan:
    plane = TravelPlane(batch.store.lat, batch.store.lng, cfg)
    screening = screen_orders(batch, plane, cfg)
    if not screening.routable:
        return RoutePlan(batch.store.store_id, [], 0.0, 0.0, 0, False, screening.at_risk, cfg.solver, 0.0)

    text = build_instance(screening, batch.num_vehicles, batch.vehicle_capacity, cfg.shift_minutes)
    resp = client.solve(text, solver=cfg.solver, size=solver_size(len(screening.routable)))
    routes = _map_routes(resp, screening, cfg)
    return RoutePlan(
        store_id=batch.store.store_id,
        routes=routes,
        travel_minutes=resp.objective,
        road_km=plane.minutes_to_km(resp.objective),
        vehicles_used=len(routes),
        exceeds_fleet=len(routes) > batch.num_vehicles,
        at_risk=screening.at_risk,
        solver=cfg.solver,
        runtime_s=resp.runtime,
    )
