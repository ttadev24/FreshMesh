import pytest

from routing.baseline import one_trip_per_order
from routing.models import Batch, DeliveryMode, Order, Store, counter_id
from tests.routing.helpers import LAT0, LNG0, point_at


def test_each_order_is_a_round_trip_to_its_delivery_point():
    orders = [
        Order("O1", *point_at(1.0, 0.0), 1, 0, 120, DeliveryMode.HOME),
        Order("O3", *point_at(0.0, 1.0), 1, 0, 120, DeliveryMode.PICKUP, 3.0, counter_id("S1")),
        Order("O9", *point_at(1.0, 0.0), 1, 0, -1, DeliveryMode.HOME),  # at risk: excluded
    ]
    result = one_trip_per_order(Batch(Store("S1", LAT0, LNG0), orders, [], 3, 10))
    # O1: 2 × 3.9 min; O3 is picked up at the store counter: 0 min
    assert result.travel_minutes == pytest.approx(7.8, rel=0.02)
    assert result.road_km == pytest.approx(2.6, rel=0.02)
    assert result.trips == 2
