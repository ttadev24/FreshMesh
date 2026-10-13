import pytest

from data_sim import CHAIN_IDS, SIM_BATCH_START, batch_created_range, counter_point_id, open_chain_db
from data_sim.locations import haversine_km
from routing.config import RoutingConfig
from routing.geo import TravelPlane
from routing.models import Batch, DeliveryMode, Order, PickupPoint, Store, counter_id
from routing.validate import screen_orders

MODES = {"home": DeliveryMode.HOME, "pickup": DeliveryMode.PICKUP, "flexible": DeliveryMode.FLEXIBLE}


def _batch(conn, store_id):
    lo, hi = batch_created_range()
    store = conn.execute("SELECT * FROM stores WHERE store_id=?", (store_id,)).fetchone()
    orders = conn.execute(
        "SELECT * FROM online_orders WHERE store_id=? AND created_at >= ? AND created_at < ? ORDER BY order_id",
        (store_id, lo, hi),
    ).fetchall()
    points = conn.execute(
        "SELECT * FROM pickup_points WHERE store_id=? AND pickup_point_id != ?", (store_id, counter_id(store_id))
    ).fetchall()
    return store, orders, points


def test_counter_id_matches_routing():
    assert counter_point_id("A-CH1") == counter_id("A-CH1")


def test_batch_window_bounds():
    lo, hi = batch_created_range()
    assert hi == SIM_BATCH_START.isoformat() and lo < hi


@pytest.mark.parametrize("chain_id", CHAIN_IDS)
def test_batch_orders_are_well_formed(data_dir, chain_id):
    cfg = RoutingConfig()
    conn = open_chain_db(data_dir, chain_id, readonly=True)
    all_points = {r["pickup_point_id"]: r for r in conn.execute("SELECT * FROM pickup_points")}
    for (store_id,) in conn.execute("SELECT store_id FROM stores").fetchall():
        store, orders, lobbies = _batch(conn, store_id)
        assert 12 <= len(orders) <= min(40, cfg.max_orders_per_batch)
        assert 2 <= len(lobbies) <= 3
        assert counter_id(store_id) in all_points
        for o in orders:
            assert 1 <= o["demand"] <= 3
            assert 0 <= o["earliest"] <= o["latest"] <= cfg.shift_minutes
            assert o["service"] >= 1
            assert haversine_km(store["lat"], store["lng"], o["lat"], o["lng"]) < 4.5
            if o["delivery_mode"] == "pickup":
                assert all_points[o["pickup_point_id"]]["store_id"] == store_id
            else:
                assert o["pickup_point_id"] is None
        modes = {o["delivery_mode"] for o in orders}
        assert "home" in modes and len(modes) >= 2


@pytest.mark.parametrize("chain_id", CHAIN_IDS)
def test_batch_screening_mostly_routable_with_some_at_risk(data_dir, chain_id):
    """Feed each store's current batch through the real routing adapter screening (no solver)."""
    cfg = RoutingConfig()
    conn = open_chain_db(data_dir, chain_id, readonly=True)
    for (store_id,) in conn.execute("SELECT store_id FROM stores").fetchall():
        store, orders, lobbies = _batch(conn, store_id)
        batch = Batch(
            store=Store(store_id, store["lat"], store["lng"]),
            orders=[
                Order(o["order_id"], o["lat"], o["lng"], o["demand"], o["earliest"], o["latest"],
                      MODES[o["delivery_mode"]], o["service"], o["pickup_point_id"])
                for o in orders
            ],
            pickup_points=[PickupPoint(p["pickup_point_id"], p["lat"], p["lng"]) for p in lobbies],
            num_vehicles=4,
            vehicle_capacity=15,
        )
        screening = screen_orders(batch, TravelPlane(store["lat"], store["lng"], cfg), cfg)
        assert len(screening.routable) >= 0.85 * len(orders), store_id
        assert 1 <= len(screening.at_risk) <= 3, store_id
        assert {a.reason for a in screening.at_risk} == {"unreachable_in_window"}
        assert any(r.mode == DeliveryMode.FLEXIBLE for r in screening.routable) or not any(
            o["delivery_mode"] == "flexible" for o in orders
        )


@pytest.mark.parametrize("chain_id", CHAIN_IDS)
def test_historical_orders_hourly_distributed(data_dir, chain_id):
    conn = open_chain_db(data_dir, chain_id, readonly=True)
    lo, _ = batch_created_range()
    hours = dict(conn.execute(
        "SELECT CAST(substr(created_at, 12, 2) AS INT) h, COUNT(*) FROM online_orders WHERE created_at < ? "
        "GROUP BY h", (lo,)
    ).fetchall())
    assert min(hours) >= 6 and max(hours) <= 21
    assert len(hours) >= 14
    days = conn.execute(
        "SELECT COUNT(DISTINCT substr(created_at,1,10)) FROM online_orders WHERE created_at < ?", (lo,)
    ).fetchone()[0]
    assert days == 14
