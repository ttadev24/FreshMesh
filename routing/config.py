from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingConfig:
    speed_kmh: float = 20.0          # assumption: average urban motorbike speed
    detour_factor: float = 1.3       # spec §6: road distance ≈ 1.3 × straight line
    max_orders_per_batch: int = 50   # adjusted from 100 based on probe_solver benchmark (100 orders > 120s)
    pickup_radius_km: float = 1.0    # flexible orders may use pickup points within this radius
    shift_minutes: int = 240         # horizon of one batch; depot and pickup point window
    solver: str = "paco"
    solver_timeout_s: float = 320.0  # routing-PL service.py kills the solver at 300 s
