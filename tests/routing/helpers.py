import math

LAT0 = 10.7340
LNG0 = 106.7210


def point_at(km_north: float, km_east: float) -> tuple[float, float]:
    """Return (lat, lng) offset from (LAT0, LNG0) by the given kilometres."""
    lat = LAT0 + km_north / 110.574
    lng = LNG0 + km_east / (111.320 * math.cos(math.radians(LAT0)))
    return lat, lng
