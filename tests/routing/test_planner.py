import pytest

from routing.client import SolverError, SolverResponse
from routing.models import Batch, DeliveryMode, Order, Store, counter_id
from routing.planner import optimize_routes, solver_size
from tests.routing.helpers import LAT0, LNG0, point_at

STORE = Store("S1", LAT0, LNG0)


def _order(oid, km_n, km_e, mode=DeliveryMode.HOME, pickup=None, latest=120):
    return Order(oid, *point_at(km_n, km_e), 1, 0, latest, mode, 3.0, pickup)


# O1 and O4 share coordinates; O2 sits exactly at the store; O3 picks up at the counter.
ORDERS = [
    _order("O1", 1.0, 0.0),
    _order("O2", 0.0, 0.0),
    _order("O3", 0.0, 1.0, DeliveryMode.PICKUP, counter_id("S1")),
    _order("O4", 1.0, 0.0),
]
GOOD = SolverResponse(
    objective=15.6,
    vehicles=2,
    runtime=0.3,
    routes=[["0", "2", "1", "4", "0"], ["0", "3(5)", "0"]],
    raw_routes=[[0, 2, 1, 4, 0], [0, 5, 0]],
    delivery_nodes=[1, 2, 5, 4],
)


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def solve(self, instance_text, solver="paco", size="small"):
        self.calls.append((instance_text, solver, size))
        return self.response


def batch(orders=ORDERS, vehicles=3):
    return Batch(STORE, list(orders), [], num_vehicles=vehicles, vehicle_capacity=10)


def test_solver_size_thresholds():
    assert [solver_size(n) for n in (1, 25, 26, 50, 51, 100)] == [
        "small", "small", "medium", "medium", "large", "large",
    ]


def test_maps_routes_back_to_orders_with_etas():
    client = FakeClient(GOOD)
    plan = optimize_routes(batch(), client)
    assert client.calls[0][1:] == ("paco", "small")
    first, second = plan.routes
    assert [s.order_id for s in first.stops] == ["O2", "O1", "O4"]
    assert [s.kind for s in first.stops] == ["home", "home", "home"]
    # O2 at store: eta 0, +3 service; O1 1 km ≈ 3.9 min → int 3 → eta 6; O4 same coords → eta 9
    assert [s.eta_min for s in first.stops] == [0, 6, 9]
    assert not any(s.late for s in first.stops)
    assert [(s.order_id, s.kind, s.pickup_point_id) for s in second.stops] == [
        ("O3", "pickup", counter_id("S1"))
    ]
    assert plan.travel_minutes == pytest.approx(15.6)
    assert plan.road_km == pytest.approx(5.2)  # 15.6 min at 20 km/h
    assert plan.vehicles_used == 2
    assert plan.exceeds_fleet is False
    assert plan.source == "Chưa rõ nguồn dữ liệu"


def test_flags_fleet_overflow():
    plan = optimize_routes(batch(vehicles=1), FakeClient(GOOD))
    assert plan.exceeds_fleet is True


def test_empty_batch_returns_empty_plan_without_calling_solver():
    client = FakeClient(GOOD)
    plan = optimize_routes(batch(orders=[]), client)
    assert client.calls == []
    assert plan.routes == [] and plan.travel_minutes == 0.0 and plan.vehicles_used == 0


def test_all_at_risk_returns_plan_with_reasons_without_calling_solver():
    client = FakeClient(GOOD)
    plan = optimize_routes(batch(orders=[_order("O9", 1.0, 0.0, latest=-1)]), client)
    assert client.calls == []
    assert [(r.order_id, r.reason) for r in plan.at_risk] == [("O9", "window_closed")]


def test_missing_order_in_output_raises():
    bad = SolverResponse(15.6, 2, 0.3, [["0", "2", "1", "0"], ["0", "3(5)", "0"]], [], [1, 2, 5, 4])
    with pytest.raises(SolverError, match="inconsistent"):
        optimize_routes(batch(), FakeClient(bad))


def test_delivery_node_mismatch_raises():
    bad = SolverResponse(15.6, 2, 0.3, GOOD.routes, GOOD.raw_routes, [1, 2, 3, 4])
    with pytest.raises(SolverError, match="inconsistent"):
        optimize_routes(batch(), FakeClient(bad))


def test_late_flag_when_eta_after_window():
    # O1 window closes at minute 4 but it is visited after O2's 3-minute service: eta 6 > 4
    orders = [_order("O1", 1.0, 0.0, latest=4), _order("O2", 0.0, 0.0)]
    resp = SolverResponse(7.8, 1, 0.1, [["0", "2", "1", "0"]], [[0, 2, 1, 0]], [1, 2])
    plan = optimize_routes(batch(orders=orders), FakeClient(resp))
    assert [(s.order_id, s.late) for s in plan.routes[0].stops] == [("O2", False), ("O1", True)]
