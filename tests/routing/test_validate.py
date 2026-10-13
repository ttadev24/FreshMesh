import pytest

from routing.config import RoutingConfig
from routing.geo import TravelPlane
from routing.models import Batch, DeliveryMode, Order, PickupPoint, Store, counter_id
from routing.validate import (
    INVALID_DEMAND,
    OVER_CAPACITY,
    UNKNOWN_PICKUP,
    UNREACHABLE,
    WINDOW_CLOSED,
    BatchTooLargeError,
    screen_orders,
)
from tests.routing.helpers import LAT0, LNG0, point_at

CFG = RoutingConfig()
STORE = Store("S1", LAT0, LNG0)


def order(oid, km_n, km_e, mode=DeliveryMode.HOME, demand=1, earliest=0, latest=120, pickup=None):
    lat, lng = point_at(km_n, km_e)
    return Order(oid, lat, lng, demand, earliest, latest, mode, 3.0, pickup)


def screen(orders, pickup_points=(), capacity=10):
    batch = Batch(STORE, list(orders), list(pickup_points), num_vehicles=2, vehicle_capacity=capacity)
    return screen_orders(batch, TravelPlane(LAT0, LNG0, CFG), CFG)


def reasons(screening):
    return {r.order_id: r.reason for r in screening.at_risk}


def test_counter_is_always_locker_zero():
    p1 = PickupPoint("P1", *point_at(0.0, 1.0))
    s = screen([], [p1])
    assert [l.point.point_id for l in s.lockers] == [counter_id("S1"), "P1"]
    assert (s.lockers[0].x, s.lockers[0].y) == pytest.approx((0.0, 0.0), abs=1e-6)


def test_reachable_home_order_is_routable_with_int_window():
    s = screen([order("O1", 1.0, 0.0, earliest=-5.5, latest=90.7)])
    assert s.at_risk == []
    r = s.routable[0]
    assert (r.mode, r.allowed_lockers, r.earliest, r.latest, r.service) == (DeliveryMode.HOME, (), 0, 90, 3)


def test_closed_window_is_at_risk():
    s = screen([order("O1", 1.0, 0.0, earliest=-30, latest=-1)])
    assert reasons(s) == {"O1": WINDOW_CLOSED}
    assert s.routable == []


def test_home_too_far_for_window_is_at_risk():
    # 10 km ≈ 39 travel minutes > latest 20
    s = screen([order("O1", 10.0, 0.0, latest=20)])
    assert reasons(s) == {"O1": UNREACHABLE}


def test_demand_rules():
    s = screen([order("O1", 1.0, 0.0, demand=0), order("O2", 1.0, 0.0, demand=11)], capacity=10)
    assert reasons(s) == {"O1": INVALID_DEMAND, "O2": OVER_CAPACITY}


def test_pickup_order_uses_named_point_or_reports_unknown():
    p1 = PickupPoint("P1", *point_at(0.0, 1.0))
    s = screen(
        [
            order("O1", 0.5, 0.0, mode=DeliveryMode.PICKUP, pickup="P1"),
            order("O2", 0.5, 0.0, mode=DeliveryMode.PICKUP, pickup=counter_id("S1")),
            order("O3", 0.5, 0.0, mode=DeliveryMode.PICKUP, pickup="NOPE"),
        ],
        [p1],
    )
    by_id = {r.order.order_id: r for r in s.routable}
    assert by_id["O1"].allowed_lockers == (1,)
    assert by_id["O2"].allowed_lockers == (0,)
    assert reasons(s) == {"O3": UNKNOWN_PICKUP}


def test_flexible_keeps_both_options_when_both_reachable():
    # order 3 km north; P1 0.5 km from the order; the counter is 3 km away (outside radius)
    p1 = PickupPoint("P1", *point_at(3.0, 0.5))
    s = screen([order("O1", 3.0, 0.0, mode=DeliveryMode.FLEXIBLE)], [p1])
    r = s.routable[0]
    assert (r.mode, r.allowed_lockers) == (DeliveryMode.FLEXIBLE, (1,))


def test_flexible_becomes_pickup_when_home_unreachable():
    p1 = PickupPoint("P1", *point_at(3.0, 0.5))
    # 3 km ≈ 11.7 min > latest 5, but the pickup point window is the whole shift
    s = screen([order("O1", 3.0, 0.0, mode=DeliveryMode.FLEXIBLE, latest=5)], [p1])
    r = s.routable[0]
    assert (r.mode, r.allowed_lockers) == (DeliveryMode.PICKUP, (1,))


def test_flexible_becomes_home_when_no_point_in_radius():
    s = screen([order("O1", 3.0, 0.0, mode=DeliveryMode.FLEXIBLE)])
    r = s.routable[0]
    assert (r.mode, r.allowed_lockers) == (DeliveryMode.HOME, ())


def test_batch_over_limit_raises():
    orders = [order(f"O{i}", 0.1, 0.0) for i in range(CFG.max_orders_per_batch + 1)]
    with pytest.raises(BatchTooLargeError):
        screen(orders)
