from routing.instance import build_instance
from routing.models import DeliveryMode, Order, PickupPoint
from routing.validate import LockerNode, RoutableOrder, Screening


def _order(oid, mode):
    return Order(oid, 0.0, 0.0, 1, 0, 0, mode)


def test_instance_text_matches_routing_pl_format():
    screening = Screening(
        routable=[
            RoutableOrder(_order("A", DeliveryMode.HOME), 3.0, 4.0, DeliveryMode.HOME, (), 0, 60, 3),
            RoutableOrder(_order("B", DeliveryMode.PICKUP), 1.0, 1.0, DeliveryMode.PICKUP, (1,), 0, 240, 3),
        ],
        lockers=[
            LockerNode(PickupPoint("S1-counter", 0.0, 0.0), 0.0, 0.0),
            LockerNode(PickupPoint("P1", 0.0, 0.0), 2.0, 0.0),
        ],
        at_risk=[],
    )
    # demands come from the order objects: A=1, B=1
    text = build_instance(screening, num_vehicles=2, vehicle_capacity=10, shift_minutes=240)
    assert text.splitlines() == [
        "2 2",
        "2 10",
        "1",
        "1",
        "0.0000 0.0000 0 240 0 0",
        "3.0000 4.0000 0 60 3 1",
        "1.0000 1.0000 0 240 3 2",
        "0.0000 0.0000 0 240 0 4",
        "2.0000 0.0000 0 240 0 4",
        "0 0",
        "0 1",
    ]


def test_flexible_order_marks_every_allowed_locker():
    screening = Screening(
        routable=[
            RoutableOrder(_order("C", DeliveryMode.FLEXIBLE), 1.0, 2.0, DeliveryMode.FLEXIBLE, (0, 2), 5, 50, 2),
        ],
        lockers=[
            LockerNode(PickupPoint("S1-counter", 0.0, 0.0), 0.0, 0.0),
            LockerNode(PickupPoint("P1", 0.0, 0.0), 2.0, 0.0),
            LockerNode(PickupPoint("P2", 0.0, 0.0), 0.0, 2.0),
        ],
        at_risk=[],
    )
    lines = build_instance(screening, 1, 5, 240).splitlines()
    assert lines[0] == "1 3"
    assert lines[4] == "1.0000 2.0000 5 50 2 3"
    assert lines[-1] == "1 0 1"
