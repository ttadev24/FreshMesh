from routing.baseline import one_trip_per_order
from routing.dispatch_baseline import zone_sweep
from routing.models import Batch, DeliveryMode, Order, Store
from simulation.routing_r1 import verdict
from tests.routing.helpers import LAT0, LNG0, point_at

STORE = Store("S1", LAT0, LNG0)


def _orders(latest: float = 200) -> list[Order]:
    north = [Order(f"N{i}", *point_at(1.0 + 0.2 * i, 0.1 * i), 1, 0, latest, DeliveryMode.HOME) for i in range(3)]
    south = [Order(f"S{i}", *point_at(-1.0 - 0.2 * i, -0.1 * i), 1, 0, latest, DeliveryMode.HOME) for i in range(3)]
    return [*north, *south]


def test_zones_follow_bearing_and_capacity_and_beat_one_trip_per_order():
    plan = zone_sweep(Batch(STORE, _orders(), [], 2, 3))
    zones = [{s.order_id[0] for s in r.stops} for r in plan.routes]
    assert sorted(len(r.stops) for r in plan.routes) == [3, 3] and all(len(z) == 1 for z in zones)
    assert not any(s.late for r in plan.routes for s in r.stops)
    assert plan.road_km < one_trip_per_order(Batch(STORE, _orders(), [], 2, 3)).road_km
    assert plan.solver == "zone_sweep" and plan.vehicles_used == 2


def test_one_motorbike_makes_trips_one_after_another_and_late_stops_are_counted():
    plan = zone_sweep(Batch(STORE, _orders(latest=12), [], 1, 3))
    assert len(plan.routes) >= 2  # the zone closes before a stop would be late from the start time
    second = plan.routes[1].stops
    assert second[0].eta_min > plan.routes[0].stops[-1].eta_min  # leaves after the first trip is back
    assert any(s.late for r in plan.routes for s in r.stops)  # the later trip cannot make the window


def _row(store, method, km, late=0):
    return {"store_id": store, "method": method, "status": "ok", "road_km": km, "late_stops": late}


def test_r1_needs_14_of_18_shorter_batches_and_no_more_late_stops():
    rows = [r for i in range(18) for r in (_row(f"B{i}", "paco", 10), _row(f"B{i}", "zone_sweep", 9 if i < 4 else 12))]
    v = verdict(rows)
    assert v["paco_shorter_batches"] == 14 and v["pass"]
    late = [*rows, _row("B0", "paco", 10, late=1)]  # same key: the later row wins
    assert verdict(late)["late_stops"] == {"paco": 1, "zone_sweep": 0} and not verdict(late)["pass"]
    fewer = [r for r in rows if r["store_id"] != "B17"] + [_row("B17", "paco", 13), _row("B17", "zone_sweep", 12)]
    assert verdict(fewer)["paco_shorter_batches"] == 13 and not verdict(fewer)["pass"]
