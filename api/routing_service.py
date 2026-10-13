"""Online-batch routing for the API: batch from the DB → PACO solver → map-ready JSON, with a cache.

* Batch = orders of the store created in the current window ``data_sim.batch_created_range()``
  (minute 0 = ``SIM_BATCH_START``), at most ``RoutingConfig.max_orders_per_batch`` orders: if more,
  the most urgent (smallest ``latest``) are routed and the rest are reported as deferred.
* ``now_minute`` shifts every window (orders whose window already closed become at-risk ``window_closed``).
* The counter pickup point ``<store_id>-counter`` is added by the routing adapter itself, so it is not
  passed in ``Batch.pickup_points`` (it is still listed in the map nodes).
* Results are cached by a SHA-256 of the batch + routing config: in-process LRU + JSON files under
  ``<data_dir>/cache/routing``. A per-hash lock prevents solving the same batch twice concurrently.
* Solver failures raise ``ApiError`` with a Vietnamese message; no route is ever invented.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from api.errors import ApiError
from api.repo import ChainRepo
from data_sim import SIM_BATCH_START, SOURCE, batch_created_range, counter_point_id
from routing.baseline import one_trip_per_order
from routing.client import SolverClient, SolverError
from routing.config import RoutingConfig
from routing.models import (
    AtRiskOrder,
    Batch,
    DeliveryMode,
    Order,
    PickupPoint,
    RoutePlan,
    Stop,
    Store,
    VehicleRoute,
)
from routing.planner import Solver, optimize_routes

log = logging.getLogger(__name__)

REASONS_VI = {
    "invalid_demand": "số lượng không hợp lệ",
    "over_capacity": "vượt tải một xe",
    "window_closed": "khung giờ đã qua",
    "unreachable_in_window": "không kịp giao trong khung giờ",
    "unknown_pickup_point": "điểm nhận không tồn tại",
}
_MODES = {"home": DeliveryMode.HOME, "pickup": DeliveryMode.PICKUP, "flexible": DeliveryMode.FLEXIBLE}
ROUTING_ASSUMPTIONS_VI = [
    "Dữ liệu giả lập (SIMULATED).",
    "Tốc độ xe máy trung bình 20 km/h, quãng đường thực ≈ 1,3 × đường chim bay (ước tính).",
    "Bản đồ nối các điểm dừng bằng đường thẳng theo thứ tự giao, không phải đường phố thật.",
    "Bạn duyệt trước khi gửi lộ trình cho shipper.",
]
LRU_SIZE = 64


def batch_hash(batch: Batch, cfg: RoutingConfig) -> str:
    body = json.dumps(
        {"batch": dataclasses.asdict(batch), "cfg": dataclasses.asdict(cfg)}, sort_keys=True, default=str
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def plan_from_dict(d: dict[str, Any]) -> RoutePlan:
    return RoutePlan(
        store_id=d["store_id"],
        routes=[
            VehicleRoute(
                [
                    Stop(s["order_id"], s["kind"], s["pickup_point_id"], int(s["eta_min"]), bool(s["late"]))
                    for s in r["stops"]
                ]
            )
            for r in d["routes"]
        ],
        travel_minutes=float(d["travel_minutes"]),
        road_km=float(d["road_km"]),
        vehicles_used=int(d["vehicles_used"]),
        exceeds_fleet=bool(d["exceeds_fleet"]),
        at_risk=[AtRiskOrder(a["order_id"], a["reason"]) for a in d["at_risk"]],
        solver=d["solver"],
        runtime_s=float(d["runtime_s"]),
        source=d.get("source", SOURCE),
    )


def solver_error_to_api(exc: Exception) -> ApiError:
    text = str(exc)
    if "cannot reach" in text or "timeout" in text:
        return ApiError(
            503,
            "solver_unavailable",
            "Không kết nối được bộ giải lộ trình PACO (container solver). Chưa có lộ trình nào được tạo; "
            "hãy kiểm tra `docker compose up -d solver` rồi thử lại.",
        )
    return ApiError(
        502,
        "solver_error",
        "Bộ giải lộ trình PACO trả lỗi nên không có lộ trình nào được tạo "
        "(hệ thống không dùng lộ trình giả). Vui lòng thử lại sau.",
    )


class RoutingService:
    def __init__(
        self,
        cache_dir: Path,
        solver: Solver | None,
        *,
        cfg: RoutingConfig | None = None,
        fleet_vehicles: int = 4,
        fleet_capacity: int = 30,
    ):
        self.cache_dir = Path(cache_dir) / "routing"
        self.solver = solver
        self.cfg = cfg or RoutingConfig()
        self.fleet_vehicles = fleet_vehicles
        self.fleet_capacity = fleet_capacity
        self._lru: OrderedDict[str, RoutePlan] = OrderedDict()
        self._lru_lock = threading.Lock()
        self._locks: dict[str, list[Any]] = {}  # batch hash -> [lock, number of callers using it]
        self.in_flight = 0  # solves currently running (the solver does not answer /health while busy)

    # ------------------------------------------------------------ cache + solve

    def _cache_get(self, key: str) -> RoutePlan | None:
        with self._lru_lock:
            if key in self._lru:
                self._lru.move_to_end(key)
                return self._lru[key]
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            try:
                plan = plan_from_dict(json.loads(path.read_text(encoding="utf-8"))["plan"])
            except (OSError, ValueError, KeyError, TypeError):
                log.warning("ignoring unreadable routing cache file %s", path)
                return None
            self._cache_put(key, plan, persist=False)
            return plan
        return None

    def _cache_put(self, key: str, plan: RoutePlan, *, persist: bool = True) -> None:
        with self._lru_lock:
            self._lru[key] = plan
            self._lru.move_to_end(key)
            while len(self._lru) > LRU_SIZE:
                self._lru.popitem(last=False)
        if persist:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_dir / f"{key}.json.tmp"
            tmp.write_text(
                json.dumps({"plan": dataclasses.asdict(plan)}, ensure_ascii=False), encoding="utf-8"
            )
            tmp.replace(self.cache_dir / f"{key}.json")

    def solve(self, batch: Batch) -> tuple[RoutePlan, bool, str]:
        """(plan, cached, batch_hash). Raises ApiError on solver failure."""
        key = batch_hash(batch, self.cfg)
        hit = self._cache_get(key)
        if hit is not None:
            return hit, True, key
        with self._lru_lock:
            entry = self._locks.setdefault(key, [threading.Lock(), 0])
            entry[1] += 1  # waiters on this hash; the entry is dropped when the last one leaves
        try:
            return self._solve_locked(batch, key, entry[0])
        finally:
            with self._lru_lock:
                entry[1] -= 1
                if entry[1] == 0:
                    self._locks.pop(key, None)

    def _solve_locked(self, batch: Batch, key: str, lock: threading.Lock) -> tuple[RoutePlan, bool, str]:
        with lock:
            hit = self._cache_get(key)
            if hit is not None:
                return hit, True, key
            if self.solver is None:
                raise solver_error_to_api(SolverError("cannot reach solver: not configured"))
            t0 = time.perf_counter()
            with self._lru_lock:
                self.in_flight += 1
            try:
                plan = optimize_routes(batch, self.solver, self.cfg)
            except SolverError as exc:
                log.warning("solver failed for batch %s: %s", key[:12], exc)
                raise solver_error_to_api(exc) from None
            finally:
                with self._lru_lock:
                    self.in_flight -= 1
            log.info(
                "solved batch %s (%d orders) in %.1fs", key[:12], len(batch.orders), time.perf_counter() - t0
            )
            self._cache_put(key, plan)
            return plan, False, key

    def router(self, batch: Batch) -> RoutePlan:
        """Callable for decision.transfer_stock (same cache)."""
        return self.solve(batch)[0]

    # ------------------------------------------------------------ online batch

    def build_batch(
        self, repo: ChainRepo, store_id: str, now_minute: int = 0
    ) -> tuple[Batch, dict[str, Any]]:
        store = repo.store(store_id)
        created_from, created_to = batch_created_range()
        rows = repo.batch_orders(store_id, created_from, created_to)
        limit = self.cfg.max_orders_per_batch
        deferred: list[str] = []
        if len(rows) > limit:
            ranked = sorted(rows, key=lambda r: (r["latest"], r["created_at"], r["order_id"]))
            keep = {r["order_id"] for r in ranked[:limit]}
            deferred = sorted(r["order_id"] for r in rows if r["order_id"] not in keep)
            rows = [r for r in rows if r["order_id"] in keep]
        points = repo.pickup_points(store_id)
        counter = counter_point_id(store_id)
        orders = [
            Order(
                order_id=r["order_id"],
                lat=r["lat"],
                lng=r["lng"],
                demand=int(r["demand"]),
                earliest_min=float(max(0, r["earliest"] - now_minute)),
                latest_min=float(r["latest"] - now_minute),
                mode=_MODES[r["delivery_mode"]],
                service_min=float(r["service"]),
                pickup_point_id=r["pickup_point_id"],
            )
            for r in rows
        ]
        batch = Batch(
            store=Store(store_id, store.lat, store.lng),
            orders=orders,
            pickup_points=[
                PickupPoint(p["pickup_point_id"], p["lat"], p["lng"])
                for p in points
                if p["pickup_point_id"] != counter
            ],
            num_vehicles=self.fleet_vehicles,
            vehicle_capacity=self.fleet_capacity,
        )
        meta = {
            "store": store,
            "rows": rows,
            "points": points,
            "created_from": created_from,
            "created_to": created_to,
            "deferred": deferred,
            "now_minute": now_minute,
        }
        return batch, meta

    def plan_for_store(self, repo: ChainRepo, store_id: str, now_minute: int = 0) -> dict[str, Any]:
        batch, meta = self.build_batch(repo, store_id, now_minute)
        store = meta["store"]
        if not batch.orders:
            raise ApiError(
                404, "empty_batch", f"Cửa hàng {store_id} không có đơn online nào trong đợt giao hiện tại."
            )
        plan, cached, key = self.solve(batch)
        baseline = one_trip_per_order(batch, self.cfg)
        coords = {r["order_id"]: (r["lat"], r["lng"]) for r in meta["rows"]}
        point_coords = {p["pickup_point_id"]: (p["lat"], p["lng"]) for p in meta["points"]}
        counter = counter_point_id(store_id)
        point_coords.setdefault(counter, (store.lat, store.lng))
        demand = {o.order_id: o.demand for o in batch.orders}
        home = [store.lat, store.lng]

        routes = []
        for i, vr in enumerate(plan.routes, start=1):
            stops = []
            for s in vr.stops:
                lat, lng = point_coords[s.pickup_point_id] if s.kind == "pickup" else coords[s.order_id]
                stops.append(
                    {
                        "order_id": s.order_id,
                        "kind": s.kind,
                        "pickup_point_id": s.pickup_point_id,
                        "eta_min": s.eta_min,
                        "late": s.late,
                        "lat": lat,
                        "lng": lng,
                        "demand": demand[s.order_id],
                    }
                )
            path = [home]
            for st in stops:
                if path[-1] != [st["lat"], st["lng"]]:
                    path.append([st["lat"], st["lng"]])
            path.append(home)
            routes.append(
                {
                    "index": i,
                    "vehicle_label": f"Xe {i}",
                    "stops": stops,
                    "path": path,
                    "n_stops": len(stops),
                    "units": sum(st["demand"] for st in stops),
                    "late_stops": sum(1 for st in stops if st["late"]),
                }
            )
        at_risk = [
            {
                "order_id": a.order_id,
                "reason": a.reason,
                "reason_vi": REASONS_VI.get(a.reason, a.reason),
                "lat": coords[a.order_id][0],
                "lng": coords[a.order_id][1],
            }
            for a in plan.at_risk
        ]
        late = sum(r["late_stops"] for r in routes)
        if plan.exceeds_fleet or late:
            level = "Thấp"
            why = (
                f"Lộ trình cần {plan.vehicles_used} xe (đội có {batch.num_vehicles} xe) và có "
                f"{late} điểm dừng dự kiến trễ."
            )
        elif at_risk:
            level = "Trung bình"
            why = f"Mọi đơn trong lộ trình kịp khung giờ nhưng {len(at_risk)} đơn không thể đưa vào lộ trình."
        else:
            level = "Cao"
            why = "Mọi đơn của đợt đều được xếp vào lộ trình và kịp khung giờ trong ước tính."
        km = round(plan.road_km, 1)
        baseline_km = round(baseline.road_km, 1)
        saving_pct = round(100 * (1 - plan.road_km / baseline.road_km), 1) if baseline.road_km > 0 else None
        return {
            "route_plan_id": key[:16],
            "batch_hash": key,
            "store_id": store_id,
            "store": {"store_id": store_id, "name": store.name, "lat": store.lat, "lng": store.lng},
            "batch": {
                "batch_start": SIM_BATCH_START.isoformat(),
                "created_from": meta["created_from"],
                "created_to": meta["created_to"],
                "now_minute": now_minute,
                "n_orders": len(batch.orders),
                "deferred_order_ids": meta["deferred"],
            },
            "fleet": {"num_vehicles": batch.num_vehicles, "vehicle_capacity": batch.vehicle_capacity},
            "solver": plan.solver,
            "runtime_s": round(plan.runtime_s, 1),
            "travel_minutes": round(plan.travel_minutes, 1),
            "road_km": km,
            "km": km,
            "vehicles_used": plan.vehicles_used,
            "vehicles": plan.vehicles_used,
            "exceeds_fleet": plan.exceeds_fleet,
            "baseline_km": baseline_km,
            "baseline_trips": baseline.trips,
            "saving_km": round(baseline_km - km, 1),
            "saving_pct": saving_pct,
            "orders_routed": sum(len(r["stops"]) for r in routes),
            "orders_at_risk": len(at_risk),
            "routes": routes,
            "at_risk": at_risk,
            "orders": [
                {
                    "order_id": r["order_id"],
                    "lat": r["lat"],
                    "lng": r["lng"],
                    "delivery_mode": r["delivery_mode"],
                    "demand": r["demand"],
                    "earliest": r["earliest"],
                    "latest": r["latest"],
                    "pickup_point_id": r["pickup_point_id"],
                }
                for r in meta["rows"]
            ],
            "pickup_points": [
                {**p, "is_counter": p["pickup_point_id"] == counter}
                for p in meta["points"]
            ],
            "cached": cached,
            "late_stops": late,
            "confidence": level,
            "confidence_reason": why
            + " Giờ đến dựa trên tốc độ trung bình và hệ số đường vòng ước tính, chưa dùng bản đồ đường phố.",
            "assumptions_vi": [
                *ROUTING_ASSUMPTIONS_VI,
                f"Đội giao mỗi cửa hàng: {batch.num_vehicles} xe máy, mỗi xe chở tối đa "
                f"{batch.vehicle_capacity} đơn vị hàng (giả định của API).",
            ],
            "source": SOURCE,
        }


def make_solver_client(url: str, cfg: RoutingConfig | None = None) -> SolverClient:
    return SolverClient(url, timeout_s=(cfg or RoutingConfig()).solver_timeout_s)
