"""Dispatcher-style baseline ``zone_sweep`` (protocol frn-v1 §6, criterion R1): how a store dispatcher plans
by hand. Orders are sorted by bearing around the store and swept into zones; a zone takes the next order
while the motorbike's capacity allows and its nearest-neighbour round trip still reaches every stop inside
its window, otherwise the zone is closed and handed to the first motorbike back at the store (the fleet is
the batch's; later trips leave later and can be late). Same screening and travel plane as the solver; an
order goes to its home, or to its nearest allowed pickup point when that is closer (or it must)."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from routing.config import RoutingConfig
from routing.geo import TravelPlane
from routing.models import Batch, DeliveryMode, RoutePlan, Stop, VehicleRoute
from routing.validate import RoutableOrder, Screening, screen_orders


@dataclass(frozen=True)
class _Point:
    order: RoutableOrder
    x: float
    y: float
    kind: str  # "home" | "pickup"
    pickup_point_id: str | None


@dataclass(frozen=True)
class _Trip:
    stops: list[Stop]
    minutes: float  # travel minutes of the round trip (waiting excluded)
    back_at: float  # minute the motorbike is back at the store


def _point(r: RoutableOrder, screening: Screening) -> _Point:
    home = (math.hypot(r.x, r.y), r.x, r.y, "home", None)
    lockers = [
        (math.hypot(lk.x, lk.y), lk.x, lk.y, "pickup", lk.point.point_id)
        for lk in (screening.lockers[i] for i in r.allowed_lockers)
    ]
    options = lockers if r.mode == DeliveryMode.PICKUP else [home, *lockers]
    _, x, y, kind, pid = min(options, key=lambda o: o[0])
    return _Point(r, x, y, kind, pid)


def _trip(points: list[_Point], start: float) -> _Trip:
    """Nearest-neighbour round trip from the store leaving at ``start`` (minutes)."""
    left, stops = list(points), []
    x, y, t, travel = 0.0, 0.0, start, 0.0
    while left:
        p = min(left, key=lambda q: math.hypot(q.x - x, q.y - y))
        left.remove(p)
        leg = math.hypot(p.x - x, p.y - y)
        travel += leg
        t = max(t + leg, p.order.earliest)
        stops.append(Stop(p.order.order.order_id, p.kind, p.pickup_point_id, round(t), t > p.order.latest))
        t += p.order.service
        x, y = p.x, p.y
    back = math.hypot(x, y)
    return _Trip(stops, travel + back, t + back)


def zone_sweep(batch: Batch, cfg: RoutingConfig = RoutingConfig()) -> RoutePlan:
    t0 = time.perf_counter()
    plane = TravelPlane(batch.store.lat, batch.store.lng, cfg)
    screening = screen_orders(batch, plane, cfg)
    points = sorted((_point(r, screening) for r in screening.routable), key=lambda p: math.atan2(p.y, p.x))
    free = [0.0] * batch.num_vehicles  # minute each motorbike is back at the store
    trips: list[_Trip] = []

    def close(zone: list[_Point]) -> None:
        v = min(range(len(free)), key=lambda i: free[i])
        trip = _trip(zone, free[v])
        free[v] = trip.back_at
        trips.append(trip)

    zone: list[_Point] = []
    for p in points:
        cand = [*zone, p]
        load = sum(q.order.order.demand for q in cand)
        if zone and (load > batch.vehicle_capacity or any(s.late for s in _trip(cand, min(free)).stops)):
            close(zone)
            zone = [p]
        else:
            zone = cand
    if zone:
        close(zone)
    minutes = sum(t.minutes for t in trips)
    return RoutePlan(
        store_id=batch.store.store_id,
        routes=[VehicleRoute(t.stops) for t in trips],
        travel_minutes=minutes,
        road_km=plane.minutes_to_km(minutes),
        vehicles_used=len(trips),  # trips, as for the one-trip baseline: each is one motorbike departure
        exceeds_fleet=False,  # the fleet is respected by sending trips one after another
        at_risk=screening.at_risk,
        solver="zone_sweep",
        runtime_s=time.perf_counter() - t0,
    )
