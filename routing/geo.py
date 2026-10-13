import math

from pyproj import Transformer

from routing.config import RoutingConfig

# HCMC lies in UTM zone 48N (spec §6).
_TO_UTM48N = Transformer.from_crs("EPSG:4326", "EPSG:32648", always_xy=True)


def _utm_km(lat: float, lng: float) -> tuple[float, float]:
    x, y = _TO_UTM48N.transform(lng, lat)
    return x / 1000.0, y / 1000.0


class TravelPlane:
    """Plane where Euclidean distance equals travel minutes.

    routing-PL uses Euclidean distance directly as travel time, so coordinates
    are scaled by detour_factor * 60 / speed_kmh and centred on the store.
    """

    def __init__(self, origin_lat: float, origin_lng: float, cfg: RoutingConfig):
        self._cfg = cfg
        self._origin = _utm_km(origin_lat, origin_lng)
        self._minutes_per_km = cfg.detour_factor * 60.0 / cfg.speed_kmh

    def project(self, lat: float, lng: float) -> tuple[float, float]:
        x, y = _utm_km(lat, lng)
        return (
            (x - self._origin[0]) * self._minutes_per_km,
            (y - self._origin[1]) * self._minutes_per_km,
        )

    def straight_km(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        x1, y1 = _utm_km(lat1, lng1)
        x2, y2 = _utm_km(lat2, lng2)
        return math.hypot(x2 - x1, y2 - y1)

    def minutes_to_km(self, minutes: float) -> float:
        """Road kilometres (detour already included) covered in `minutes`."""
        return minutes * self._cfg.speed_kmh / 60.0
