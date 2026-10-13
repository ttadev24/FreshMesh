import math

import pytest

from routing.config import RoutingConfig
from routing.geo import TravelPlane
from tests.routing.helpers import LAT0, LNG0, point_at


def test_origin_projects_to_zero():
    plane = TravelPlane(LAT0, LNG0, RoutingConfig())
    x, y = plane.project(LAT0, LNG0)
    assert x == pytest.approx(0.0, abs=1e-6)
    assert y == pytest.approx(0.0, abs=1e-6)


def test_one_km_north_is_3_9_travel_minutes_with_defaults():
    # 1 km * 1.3 detour * 60 / 20 km/h = 3.9 minutes
    plane = TravelPlane(LAT0, LNG0, RoutingConfig())
    x, y = plane.project(*point_at(1.0, 0.0))
    assert math.hypot(x, y) == pytest.approx(3.9, rel=0.02)


def test_straight_km_ignores_detour_factor():
    plane = TravelPlane(LAT0, LNG0, RoutingConfig())
    km = plane.straight_km(LAT0, LNG0, *point_at(0.0, 2.0))
    assert km == pytest.approx(2.0, rel=0.02)


def test_minutes_to_km_uses_speed():
    plane = TravelPlane(LAT0, LNG0, RoutingConfig(speed_kmh=30.0))
    assert plane.minutes_to_km(60.0) == pytest.approx(30.0)
