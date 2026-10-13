from dataclasses import dataclass
from enum import IntEnum


class DeliveryMode(IntEnum):
    HOME = 1      # routing-PL customer type 1
    PICKUP = 2    # type 2: pickup point / locker only
    FLEXIBLE = 3  # type 3: solver chooses home or pickup point


@dataclass(frozen=True)
class Store:
    store_id: str
    lat: float
    lng: float


@dataclass(frozen=True)
class PickupPoint:
    point_id: str
    lat: float
    lng: float


@dataclass(frozen=True)
class Order:
    order_id: str
    lat: float
    lng: float
    demand: int
    earliest_min: float  # minutes from batch start
    latest_min: float
    mode: DeliveryMode
    service_min: float = 3.0
    pickup_point_id: str | None = None  # required when mode is PICKUP


@dataclass(frozen=True)
class Batch:
    store: Store
    orders: list[Order]
    pickup_points: list[PickupPoint]
    num_vehicles: int
    vehicle_capacity: int


@dataclass(frozen=True)
class AtRiskOrder:
    order_id: str
    reason: str


@dataclass(frozen=True)
class Stop:
    order_id: str
    kind: str  # "home" | "pickup"
    pickup_point_id: str | None
    eta_min: int
    late: bool


@dataclass(frozen=True)
class VehicleRoute:
    stops: list[Stop]


@dataclass(frozen=True)
class RoutePlan:
    store_id: str
    routes: list[VehicleRoute]
    travel_minutes: float
    road_km: float
    vehicles_used: int
    exceeds_fleet: bool
    at_risk: list[AtRiskOrder]
    solver: str
    runtime_s: float
    source: str = "Chưa rõ nguồn dữ liệu"


def counter_id(store_id: str) -> str:
    return f"{store_id}-counter"
