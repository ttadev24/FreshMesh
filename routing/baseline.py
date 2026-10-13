import math
from dataclasses import dataclass

from routing.config import RoutingConfig
from routing.geo import TravelPlane
from routing.models import Batch, DeliveryMode
from routing.validate import screen_orders


@dataclass(frozen=True)
class BaselineResult:
    travel_minutes: float
    road_km: float
    trips: int


def one_trip_per_order(batch: Batch, cfg: RoutingConfig = RoutingConfig()) -> BaselineResult:
    """Manual dispatch today: one round trip from the store per order.

    Each order goes to its closest allowed delivery point (home and/or pickup points).
    """
    plane = TravelPlane(batch.store.lat, batch.store.lng, cfg)
    screening = screen_orders(batch, plane, cfg)
    total = 0.0
    for r in screening.routable:
        options = [math.hypot(screening.lockers[i].x, screening.lockers[i].y) for i in r.allowed_lockers]
        if r.mode != DeliveryMode.PICKUP:
            options.append(math.hypot(r.x, r.y))
        total += 2 * min(options)
    return BaselineResult(total, plane.minutes_to_km(total), len(screening.routable))
