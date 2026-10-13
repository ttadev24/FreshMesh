import math
from dataclasses import dataclass

from routing.config import RoutingConfig
from routing.geo import TravelPlane
from routing.models import AtRiskOrder, Batch, DeliveryMode, Order, PickupPoint, counter_id

INVALID_DEMAND = "invalid_demand"
OVER_CAPACITY = "over_capacity"
WINDOW_CLOSED = "window_closed"
UNREACHABLE = "unreachable_in_window"
UNKNOWN_PICKUP = "unknown_pickup_point"


class BatchTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class LockerNode:
    point: PickupPoint
    x: float
    y: float


@dataclass(frozen=True)
class RoutableOrder:
    order: Order
    x: float
    y: float
    mode: DeliveryMode
    allowed_lockers: tuple[int, ...]
    earliest: int
    latest: int
    service: int


@dataclass(frozen=True)
class Screening:
    routable: list[RoutableOrder]
    lockers: list[LockerNode]
    at_risk: list[AtRiskOrder]


def _minutes_from_depot(x: float, y: float) -> int:
    # routing-PL truncates travel time to int (Solver.cpp:36); the depot is (0, 0)
    return int(math.hypot(x, y))


def _build_lockers(batch: Batch, plane: TravelPlane) -> list[LockerNode]:
    store = batch.store
    points = [PickupPoint(counter_id(store.store_id), store.lat, store.lng), *batch.pickup_points]
    return [LockerNode(p, *plane.project(p.lat, p.lng)) for p in points]


def screen_orders(batch: Batch, plane: TravelPlane, cfg: RoutingConfig) -> Screening:
    """Split orders into routable ones and at-risk ones.

    Anything routing-PL cannot serve straight from the depot must be removed
    here: its decoder loops forever on such customers (Solver.cpp:54-76).
    """
    if len(batch.orders) > cfg.max_orders_per_batch:
        raise BatchTooLargeError(
            f"{len(batch.orders)} orders exceed the limit of {cfg.max_orders_per_batch} per batch"
        )
    if batch.num_vehicles < 1 or batch.vehicle_capacity < 1:
        raise ValueError("num_vehicles and vehicle_capacity must be >= 1")

    lockers = _build_lockers(batch, plane)
    locker_index = {l.point.point_id: i for i, l in enumerate(lockers)}
    reachable_lockers = {
        i for i, l in enumerate(lockers) if _minutes_from_depot(l.x, l.y) <= cfg.shift_minutes
    }

    routable: list[RoutableOrder] = []
    at_risk: list[AtRiskOrder] = []

    def reject(o: Order, reason: str) -> None:
        at_risk.append(AtRiskOrder(o.order_id, reason))

    for o in batch.orders:
        if o.demand < 1:
            reject(o, INVALID_DEMAND)
            continue
        if o.demand > batch.vehicle_capacity:
            reject(o, OVER_CAPACITY)
            continue
        earliest = max(0, math.ceil(o.earliest_min))
        latest = math.floor(o.latest_min)
        if latest < earliest:
            reject(o, WINDOW_CLOSED)
            continue

        x, y = plane.project(o.lat, o.lng)
        home_ok = _minutes_from_depot(x, y) <= latest

        if o.mode == DeliveryMode.HOME:
            if not home_ok:
                reject(o, UNREACHABLE)
                continue
            mode, allowed = DeliveryMode.HOME, ()
        elif o.mode == DeliveryMode.PICKUP:
            idx = locker_index.get(o.pickup_point_id or "")
            if idx is None:
                reject(o, UNKNOWN_PICKUP)
                continue
            if idx not in reachable_lockers:
                reject(o, UNREACHABLE)
                continue
            mode, allowed = DeliveryMode.PICKUP, (idx,)
        else:
            nearby = tuple(
                i
                for i in sorted(reachable_lockers)
                if plane.straight_km(o.lat, o.lng, lockers[i].point.lat, lockers[i].point.lng)
                <= cfg.pickup_radius_km
            )
            if home_ok and nearby:
                mode, allowed = DeliveryMode.FLEXIBLE, nearby
            elif home_ok:
                mode, allowed = DeliveryMode.HOME, ()
            elif nearby:
                mode, allowed = DeliveryMode.PICKUP, nearby
            else:
                reject(o, UNREACHABLE)
                continue

        routable.append(
            RoutableOrder(o, x, y, mode, allowed, earliest, latest, round(o.service_min))
        )

    return Screening(routable, lockers, at_risk)
