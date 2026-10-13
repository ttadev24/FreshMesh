"""Store coordinates: routing-PL instance customers mapped onto Ho Chi Minh City.

Mapping (documented in docs/data-assumptions.md):
the Solomon-style instance `R101_co_100.txt` has customer coordinates on a plane (x 2..67, y 3..77).
x is mapped linearly onto longitude [LNG_MIN, LNG_MAX] and y onto latitude [LAT_MIN, LAT_MAX]
(about 17 km × 14 km, inner HCMC). Stores are picked from those customer points in a
seed-determined order, keeping at least MIN_STORE_SPACING_KM between any two stores.
"""

import math
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTANCE_PATH = REPO_ROOT / "routing" / "routing-PL" / "src" / "data" / "100" / "R101_co_100.txt"

LAT_MIN, LAT_MAX = 10.72, 10.84
LNG_MIN, LNG_MAX = 106.62, 106.78
MIN_STORE_SPACING_KM = 1.2

KM_PER_DEG_LAT = 110.574

# Approximate centroids, used only to give stores a readable name.
DISTRICTS: tuple[tuple[str, float, float], ...] = (
    ("Quận 1", 10.776, 106.700),
    ("Quận 3", 10.784, 106.684),
    ("Quận 4", 10.758, 106.705),
    ("Quận 5", 10.754, 106.663),
    ("Quận 6", 10.746, 106.635),
    ("Quận 7", 10.734, 106.722),
    ("Quận 8", 10.724, 106.628),
    ("Quận 10", 10.773, 106.668),
    ("Quận 11", 10.763, 106.643),
    ("Phú Nhuận", 10.800, 106.680),
    ("Bình Thạnh", 10.810, 106.709),
    ("Gò Vấp", 10.838, 106.665),
    ("Tân Bình", 10.801, 106.652),
    ("Tân Phú", 10.790, 106.628),
    ("Thảo Điền", 10.803, 106.735),
    ("An Phú", 10.789, 106.752),
    ("Bình Trưng", 10.786, 106.772),
)


def km_per_deg_lng(lat: float) -> float:
    return 111.320 * math.cos(math.radians(lat))


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def offset_latlng(lat: float, lng: float, dist_km: float, bearing_rad: float) -> tuple[float, float]:
    """Point at `dist_km` from (lat, lng) in direction `bearing_rad` (0 = north), flat-earth approx."""
    return (
        lat + dist_km * math.cos(bearing_rad) / KM_PER_DEG_LAT,
        lng + dist_km * math.sin(bearing_rad) / km_per_deg_lng(lat),
    )


def read_instance_customers(path: Path = INSTANCE_PATH) -> list[tuple[float, float]]:
    """Customer (x, y) coordinates of a routing-PL instance (depot and lockers excluded)."""
    lines = [ln.split() for ln in path.read_text().splitlines() if ln.strip()]
    n_customers, n_lockers = int(lines[0][0]), int(lines[0][1])
    coord_start = 2 + n_customers
    rows = lines[coord_start : coord_start + 1 + n_customers + n_lockers]
    customers = [r for r in rows if int(r[5]) in (1, 2, 3)]
    return [(float(r[0]), float(r[1])) for r in customers]


def map_to_hcmc(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    return [
        (
            round(LAT_MIN + (y - y0) / (y1 - y0) * (LAT_MAX - LAT_MIN), 6),
            round(LNG_MIN + (x - x0) / (x1 - x0) * (LNG_MAX - LNG_MIN), 6),
        )
        for x, y in points
    ]


def pick_store_locations(n_stores: int, rng: np.random.Generator) -> list[tuple[float, float]]:
    candidates = map_to_hcmc(read_instance_customers())
    chosen: list[tuple[float, float]] = []
    for idx in rng.permutation(len(candidates)):
        lat, lng = candidates[int(idx)]
        if all(haversine_km(lat, lng, a, b) >= MIN_STORE_SPACING_KM for a, b in chosen):
            chosen.append((lat, lng))
            if len(chosen) == n_stores:
                return chosen
    raise ValueError(f"cannot place {n_stores} stores with spacing {MIN_STORE_SPACING_KM} km")


def district_name(lat: float, lng: float) -> str:
    return min(DISTRICTS, key=lambda d: haversine_km(lat, lng, d[1], d[2]))[0]
