# FreshMesh Plan 1: Adapter định tuyến PACO — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Biến một đợt đơn online (tọa độ lat/lng, khung giờ, lựa chọn nhận hàng) của một cửa hàng thành lộ trình giao hàng do solver PACO của routing-PL tính, kèm so sánh với baseline "mỗi đơn một chuyến", chạy được bằng CLI.

**Architecture:** Package Python `routing/` gồm các phần: chiếu tọa độ sang mặt phẳng "phút di chuyển", lọc đơn không phục vụ được, sinh instance text đúng định dạng routing-PL, gọi `POST /solve` của container routing-PL qua HTTP, rồi ánh xạ kết quả về đơn hàng. Submodule `routing/routing-PL` giữ nguyên, không sửa. Unit test không cần Docker (HTTP được giả lập). Một integration test gọi container thật.

**Tech Stack:** Python ≥ 3.12, uv, httpx, pyproj, pytest; Docker Compose (container routing-PL, Python 3.13 + C++ build sẵn bên trong).

**Spec:** `docs/superpowers/specs/2026-10-12-freshmesh-design.md` (mục 6 Định tuyến, mục 2.3 luồng 3, mục 11 Kiểm thử)

**Vị trí trong lộ trình:** Spec được chia thành nhiều plan, mỗi plan tự chạy và test được:
1. **Plan 1 (file này): adapter định tuyến + container solver.** Làm đầu tiên vì là rủi ro tích hợp lớn nhất (bài báo Q1).
2. Plan 2: `data_sim/` (bộ sinh dữ liệu giả lập).
3. Plan 3: `forecasting/` local + conformal.
4. Plan 4: `decision/plan_inventory` + CLI luồng 1.
5. Các plan sau: agent/API/UI, FL, markdown/transfer, polish.

Mỗi plan được viết khi plan trước đã xong, để dựa trên interface có thật.

## Global Constraints

- Hệ tọa độ phẳng: UTM zone 48N (`EPSG:32648`).
- Hệ số đường vòng đô thị: `1.3`.
- Tối đa `100` đơn mỗi đợt; đợt gom `30–60` phút.
- Submodule `routing/routing-PL` **không được sửa**; chỉ gọi qua HTTP API của container.
- Mọi kết quả gắn `source = "SIMULATED"`.
- Ánh xạ lựa chọn nhận hàng: tận nhà → type `1`; điểm nhận → type `2`; linh hoạt → type `3`; tủ/điểm nhận trong instance là type `4`; depot type `0`.
- Văn bản hiển thị cho người dùng bằng tiếng Việt; identifier và code bằng tiếng Anh.
- Python `>=3.12` cho FreshMesh (Python 3.13 chỉ cần trong container solver).
- **Giả định của plan này (spec chưa nêu):** tốc độ xe máy nội đô trung bình `20 km/h`. Giá trị nằm trong `RoutingConfig.speed_kmh`, sửa được, và phải ghi trong `docs/data-assumptions.md` khi plan 2 tạo file đó.
- **Sự thật về solver (đã kiểm chứng trong mã C++ của routing-PL, commit `32488ce`):**
  - Thời gian di chuyển = khoảng cách Euclid trong đơn vị tọa độ, ép kiểu `int` (`Solver.cpp:36`). Do đó tọa độ phải tính bằng **phút di chuyển**: `x_min = x_km × 1.3 × 60 / speed_kmh`.
  - Mỗi xe bắt đầu ở `time = 0` → khung giờ tính bằng phút **kể từ đầu đợt**.
  - `earliest/latest/service_time/demand` được đọc là `int` (`InstanceParser.cpp:36`).
  - Với tủ, solver dùng khung giờ **của tủ**, không dùng khung giờ của khách.
  - Bộ giải mã **lặp vô hạn** nếu một khách không phục vụ được ngay cả khi đi thẳng từ depot (demand > capacity hoặc không kịp khung giờ) (`Solver.cpp:54-76`). Vì vậy mọi đơn phải được lọc trước khi gửi.
  - Parser ném lỗi nếu khách type 2/3 không có tủ nào, hoặc khách type 1 có tủ (`InstanceParser.cpp:75-79`).
  - Solver **không cộng service time** khi tính thời gian đến.
- **Khác biệt so với spec mục 6 (ghi nhận, không sửa submodule):**
  - Spec ghi gọi `POST /solve/manual`, nhưng `backend/utils.py` của routing-PL gán mọi tủ cho mọi khách, kể cả type 1, nên parser sẽ ném lỗi. Plan này tự sinh instance và gọi `POST /solve` với `instance_content`.
  - API chỉ cho phép `paco` và `sa` (`service.py:31`) và có timeout cứng 300 giây. ALNS/GA chỉ chạy được qua CLI trong container; phần benchmark ALNS để lại cho plan polish.

## Review Focus

1. Solver trả `success=false`, timeout hoặc mất kết nối → `SolverError` có thông báo rõ; CLI in lỗi tiếng Việt, thoát mã 2; **không bao giờ** bịa ra lộ trình. (Task 4, Task 6)
2. Đơn không phục vụ được (khung giờ đã đóng, vượt tải, không kịp từ depot, điểm nhận không tồn tại) → nằm trong `at_risk` kèm lý do, **không** được gửi tới solver (tránh vòng lặp vô hạn). (Task 2)
3. Đợt có 0 đơn, hoặc mọi đơn đều `at_risk` → trả về plan rỗng, không gọi solver. (Task 5)
4. Hai đơn trùng tọa độ, hoặc đơn nằm ngay tại cửa hàng → vẫn ánh xạ đúng đơn và ETA. (Task 5)
5. Output solver thiếu đơn hoặc lệch `delivery_nodes` → `SolverError("inconsistent solver output ...")`, không im lặng bỏ qua. (Task 5)

---

## File Structure

```
freshmesh/
├─ pyproject.toml                 # Task 1: project, deps, pytest config
├─ docker-compose.yml             # Task 6: container solver routing-PL
├─ routing/
│  ├─ __init__.py                 # Task 1
│  ├─ config.py                   # Task 1: RoutingConfig
│  ├─ geo.py                      # Task 1: TravelPlane (lat/lng → phút di chuyển)
│  ├─ models.py                   # Task 2: Store, PickupPoint, Order, Batch, kết quả
│  ├─ validate.py                 # Task 2: screen_orders → Screening
│  ├─ instance.py                 # Task 3: build_instance → text routing-PL
│  ├─ client.py                   # Task 4: SolverClient (HTTP)
│  ├─ planner.py                  # Task 5: optimize_routes, solver_size
│  ├─ baseline.py                 # Task 5: one_trip_per_order
│  ├─ cli.py                      # Task 6: CLI + định dạng tiếng Việt
│  ├─ examples/batch_q7.json      # Task 6: đợt đơn mẫu (SIMULATED)
│  └─ routing-PL/                 # submodule, KHÔNG SỬA
├─ scripts/probe_solver.py        # Task 7: đo runtime solver
├─ docs/solver-probe.md           # Task 7: kết quả đo
└─ tests/
   ├─ __init__.py
   └─ routing/
      ├─ __init__.py
      ├─ helpers.py               # point_at(): tạo lat/lng theo km lệch
      ├─ test_geo.py
      ├─ test_validate.py
      ├─ test_instance.py
      ├─ test_client.py
      ├─ test_planner.py
      ├─ test_baseline.py
      ├─ test_cli.py
      └─ test_integration.py      # marker integration
```

---

### Task 1: Khởi tạo project + chiếu tọa độ sang "phút di chuyển"

**Files:**
- Create: `pyproject.toml`, `routing/__init__.py`, `routing/config.py`, `routing/geo.py`
- Create: `tests/__init__.py`, `tests/routing/__init__.py`, `tests/routing/helpers.py`
- Test: `tests/routing/test_geo.py`

**Interfaces:**
- Consumes: không có.
- Produces:
  - `RoutingConfig(speed_kmh=20.0, detour_factor=1.3, max_orders_per_batch=100, pickup_radius_km=1.0, shift_minutes=240, solver="paco", solver_timeout_s=320.0)` (frozen dataclass).
  - `TravelPlane(origin_lat: float, origin_lng: float, cfg: RoutingConfig)`, với các phương thức:
    - `.project(lat, lng) -> tuple[float, float]`: tọa độ tính bằng phút, gốc tại origin.
    - `.straight_km(lat1, lng1, lat2, lng2) -> float`
    - `.minutes_to_km(minutes: float) -> float`
  - `tests.routing.helpers.point_at(km_north: float, km_east: float) -> tuple[float, float]`, gốc `LAT0=10.7340, LNG0=106.7210`.

- [ ] **Step 1: Tạo `pyproject.toml`**

```toml
[project]
name = "freshmesh"
version = "0.1.0"
description = "FreshMesh: decision support for fresh-goods replenishment and delivery"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "pyproj>=3.6",
]

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-m 'not integration'"
markers = ["integration: needs the routing-PL solver container (FRESHMESH_SOLVER_URL)"]
```

Run: `cd /home/tta/projects/freshmesh && uv sync`
Expected: tạo `.venv/` và `uv.lock`, không lỗi.

- [ ] **Step 2: Tạo package rỗng và helper cho test**

`routing/__init__.py`, `tests/__init__.py`, `tests/routing/__init__.py`: file rỗng.

`tests/routing/helpers.py`:
```python
import math

LAT0 = 10.7340
LNG0 = 106.7210


def point_at(km_north: float, km_east: float) -> tuple[float, float]:
    """Return (lat, lng) offset from (LAT0, LNG0) by the given kilometres."""
    lat = LAT0 + km_north / 110.574
    lng = LNG0 + km_east / (111.320 * math.cos(math.radians(LAT0)))
    return lat, lng
```

- [ ] **Step 3: Viết test thất bại**

`tests/routing/test_geo.py`:
```python
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
```

- [ ] **Step 4: Chạy test để thấy thất bại**

Run: `uv run pytest tests/routing/test_geo.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'routing.config'`

- [ ] **Step 5: Viết code**

`routing/config.py`:
```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingConfig:
    speed_kmh: float = 20.0          # assumption: average urban motorbike speed
    detour_factor: float = 1.3       # spec §6: road distance ≈ 1.3 × straight line
    max_orders_per_batch: int = 100  # spec §6
    pickup_radius_km: float = 1.0    # flexible orders may use pickup points within this radius
    shift_minutes: int = 240         # horizon of one batch; depot and pickup point window
    solver: str = "paco"
    solver_timeout_s: float = 320.0  # routing-PL service.py kills the solver at 300 s
```

`routing/geo.py`:
```python
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
```

- [ ] **Step 6: Chạy test để thấy thành công**

Run: `uv run pytest tests/routing/test_geo.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock routing/__init__.py routing/config.py routing/geo.py tests/
git commit -m "feat(routing): project lat/lng to travel-minute plane (UTM 48N)"
```

---

### Task 2: Model dữ liệu + lọc đơn trước khi gọi solver

**Files:**
- Create: `routing/models.py`, `routing/validate.py`
- Test: `tests/routing/test_validate.py`

**Interfaces:**
- Consumes: `RoutingConfig`, `TravelPlane` (Task 1); `point_at` (helpers).
- Produces:
  - `DeliveryMode(IntEnum)`: `HOME=1, PICKUP=2, FLEXIBLE=3`.
  - Dataclass `Store(store_id, lat, lng)`, `PickupPoint(point_id, lat, lng)`.
  - Dataclass `Order(order_id, lat, lng, demand: int, earliest_min: float, latest_min: float, mode: DeliveryMode, service_min: float = 3.0, pickup_point_id: str | None = None)`.
  - Dataclass `Batch(store: Store, orders: list[Order], pickup_points: list[PickupPoint], num_vehicles: int, vehicle_capacity: int)`.
  - Dataclass `AtRiskOrder(order_id: str, reason: str)`.
  - Dataclass `Stop(order_id, kind: str, pickup_point_id: str | None, eta_min: int, late: bool)`; `VehicleRoute(stops: list[Stop])`.
  - Dataclass `RoutePlan(store_id, routes: list[VehicleRoute], travel_minutes: float, road_km: float, vehicles_used: int, exceeds_fleet: bool, at_risk: list[AtRiskOrder], solver: str, runtime_s: float, source: str = "SIMULATED")`.
  - `counter_id(store_id: str) -> str`, trả về `f"{store_id}-counter"`.
  - Dataclass `LockerNode(point: PickupPoint, x: float, y: float)`.
  - Dataclass `RoutableOrder(order: Order, x: float, y: float, mode: DeliveryMode, allowed_lockers: tuple[int, ...], earliest: int, latest: int, service: int)`.
  - Dataclass `Screening(routable: list[RoutableOrder], lockers: list[LockerNode], at_risk: list[AtRiskOrder])`.
  - `screen_orders(batch: Batch, plane: TravelPlane, cfg: RoutingConfig) -> Screening`.
  - `BatchTooLargeError(ValueError)`.
  - Hằng lý do: `INVALID_DEMAND="invalid_demand"`, `OVER_CAPACITY="over_capacity"`, `WINDOW_CLOSED="window_closed"`, `UNREACHABLE="unreachable_in_window"`, `UNKNOWN_PICKUP="unknown_pickup_point"`.

Quy tắc lọc (theo thứ tự, áp dụng cho từng đơn):
1. `len(orders) > cfg.max_orders_per_batch` → ném `BatchTooLargeError` (cả đợt). Nếu `num_vehicles < 1` hoặc `vehicle_capacity < 1` → ném `ValueError`.
2. `demand < 1` → `INVALID_DEMAND`. `demand > vehicle_capacity` → `OVER_CAPACITY`.
3. `earliest = max(0, ceil(earliest_min))`, `latest = floor(latest_min)`. Nếu `latest < earliest` → `WINDOW_CLOSED`.
4. Danh sách tủ: phần tử `0` luôn là quầy của cửa hàng (`counter_id`, tọa độ cửa hàng), sau đó là `batch.pickup_points` theo đúng thứ tự. Một tủ "tới được" khi `int(khoảng cách phút từ depot) <= cfg.shift_minutes`.
5. `HOME`: nếu `int(khoảng cách phút từ depot tới nhà) > latest` → `UNREACHABLE`.
6. `PICKUP`: nếu `pickup_point_id` không có trong danh sách tủ → `UNKNOWN_PICKUP`; nếu tủ không tới được → `UNREACHABLE`; còn lại `allowed_lockers = (index,)`.
7. `FLEXIBLE`: tủ ứng viên là các tủ tới được có `straight_km(order, tủ) <= cfg.pickup_radius_km`. Nhà tới được (như quy tắc 5) và có tủ → `FLEXIBLE`; chỉ nhà tới được → chuyển thành `HOME`; chỉ có tủ → chuyển thành `PICKUP`; không có cả hai → `UNREACHABLE`.
8. `service = round(service_min)`.

- [ ] **Step 1: Viết test thất bại**

`tests/routing/test_validate.py`:
```python
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
```

- [ ] **Step 2: Chạy test để thấy thất bại**

Run: `uv run pytest tests/routing/test_validate.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'routing.models'`

- [ ] **Step 3: Viết `routing/models.py`**

```python
from dataclasses import dataclass
from enum import IntEnum


class DeliveryMode(IntEnum):
    HOME = 1      # routing-PL customer type 1
    PICKUP = 2    # type 2: pickup point / locker only
    FLEXIBLE = 3  # type 3: solver chooses home or pickup point


@dataclass(frozen=True)
class Store:
    store_id: str
    lat: float
    lng: float


@dataclass(frozen=True)
class PickupPoint:
    point_id: str
    lat: float
    lng: float


@dataclass(frozen=True)
class Order:
    order_id: str
    lat: float
    lng: float
    demand: int
    earliest_min: float  # minutes from batch start
    latest_min: float
    mode: DeliveryMode
    service_min: float = 3.0
    pickup_point_id: str | None = None  # required when mode is PICKUP


@dataclass(frozen=True)
class Batch:
    store: Store
    orders: list[Order]
    pickup_points: list[PickupPoint]
    num_vehicles: int
    vehicle_capacity: int


@dataclass(frozen=True)
class AtRiskOrder:
    order_id: str
    reason: str


@dataclass(frozen=True)
class Stop:
    order_id: str
    kind: str  # "home" | "pickup"
    pickup_point_id: str | None
    eta_min: int
    late: bool


@dataclass(frozen=True)
class VehicleRoute:
    stops: list[Stop]


@dataclass(frozen=True)
class RoutePlan:
    store_id: str
    routes: list[VehicleRoute]
    travel_minutes: float
    road_km: float
    vehicles_used: int
    exceeds_fleet: bool
    at_risk: list[AtRiskOrder]
    solver: str
    runtime_s: float
    source: str = "SIMULATED"


def counter_id(store_id: str) -> str:
    return f"{store_id}-counter"
```

- [ ] **Step 4: Viết `routing/validate.py`**

```python
import math
from dataclasses import dataclass

from routing.config import RoutingConfig
from routing.geo import TravelPlane
from routing.models import AtRiskOrder, Batch, DeliveryMode, Order, PickupPoint, counter_id

INVALID_DEMAND = "invalid_demand"
OVER_CAPACITY = "over_capacity"
WINDOW_CLOSED = "window_closed"
UNREACHABLE = "unreachable_in_window"
UNKNOWN_PICKUP = "unknown_pickup_point"


class BatchTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class LockerNode:
    point: PickupPoint
    x: float
    y: float


@dataclass(frozen=True)
class RoutableOrder:
    order: Order
    x: float
    y: float
    mode: DeliveryMode
    allowed_lockers: tuple[int, ...]
    earliest: int
    latest: int
    service: int


@dataclass(frozen=True)
class Screening:
    routable: list[RoutableOrder]
    lockers: list[LockerNode]
    at_risk: list[AtRiskOrder]


def _minutes_from_depot(x: float, y: float) -> int:
    # routing-PL truncates travel time to int (Solver.cpp:36); the depot is (0, 0)
    return int(math.hypot(x, y))


def _build_lockers(batch: Batch, plane: TravelPlane) -> list[LockerNode]:
    store = batch.store
    points = [PickupPoint(counter_id(store.store_id), store.lat, store.lng), *batch.pickup_points]
    return [LockerNode(p, *plane.project(p.lat, p.lng)) for p in points]


def screen_orders(batch: Batch, plane: TravelPlane, cfg: RoutingConfig) -> Screening:
    """Split orders into routable ones and at-risk ones.

    Anything routing-PL cannot serve straight from the depot must be removed
    here: its decoder loops forever on such customers (Solver.cpp:54-76).
    """
    if len(batch.orders) > cfg.max_orders_per_batch:
        raise BatchTooLargeError(
            f"{len(batch.orders)} orders exceed the limit of {cfg.max_orders_per_batch} per batch"
        )
    if batch.num_vehicles < 1 or batch.vehicle_capacity < 1:
        raise ValueError("num_vehicles and vehicle_capacity must be >= 1")

    lockers = _build_lockers(batch, plane)
    locker_index = {l.point.point_id: i for i, l in enumerate(lockers)}
    reachable_lockers = {
        i for i, l in enumerate(lockers) if _minutes_from_depot(l.x, l.y) <= cfg.shift_minutes
    }

    routable: list[RoutableOrder] = []
    at_risk: list[AtRiskOrder] = []

    def reject(o: Order, reason: str) -> None:
        at_risk.append(AtRiskOrder(o.order_id, reason))

    for o in batch.orders:
        if o.demand < 1:
            reject(o, INVALID_DEMAND)
            continue
        if o.demand > batch.vehicle_capacity:
            reject(o, OVER_CAPACITY)
            continue
        earliest = max(0, math.ceil(o.earliest_min))
        latest = math.floor(o.latest_min)
        if latest < earliest:
            reject(o, WINDOW_CLOSED)
            continue

        x, y = plane.project(o.lat, o.lng)
        home_ok = _minutes_from_depot(x, y) <= latest

        if o.mode == DeliveryMode.HOME:
            if not home_ok:
                reject(o, UNREACHABLE)
                continue
            mode, allowed = DeliveryMode.HOME, ()
        elif o.mode == DeliveryMode.PICKUP:
            idx = locker_index.get(o.pickup_point_id or "")
            if idx is None:
                reject(o, UNKNOWN_PICKUP)
                continue
            if idx not in reachable_lockers:
                reject(o, UNREACHABLE)
                continue
            mode, allowed = DeliveryMode.PICKUP, (idx,)
        else:
            nearby = tuple(
                i
                for i in sorted(reachable_lockers)
                if plane.straight_km(o.lat, o.lng, lockers[i].point.lat, lockers[i].point.lng)
                <= cfg.pickup_radius_km
            )
            if home_ok and nearby:
                mode, allowed = DeliveryMode.FLEXIBLE, nearby
            elif home_ok:
                mode, allowed = DeliveryMode.HOME, ()
            elif nearby:
                mode, allowed = DeliveryMode.PICKUP, nearby
            else:
                reject(o, UNREACHABLE)
                continue

        routable.append(
            RoutableOrder(o, x, y, mode, allowed, earliest, latest, round(o.service_min))
        )

    return Screening(routable, lockers, at_risk)
```

- [ ] **Step 5: Chạy test để thấy thành công**

Run: `uv run pytest tests/routing/test_validate.py -v`
Expected: 10 passed

- [ ] **Step 6: Commit**

```bash
git add routing/models.py routing/validate.py tests/routing/test_validate.py
git commit -m "feat(routing): screen orders the solver cannot serve before calling it"
```

---

### Task 3: Sinh instance text đúng định dạng routing-PL

**Files:**
- Create: `routing/instance.py`
- Test: `tests/routing/test_instance.py`

**Interfaces:**
- Consumes: `Screening`, `RoutableOrder`, `LockerNode` (Task 2); `DeliveryMode`, `Order`, `PickupPoint` (Task 2).
- Produces: `build_instance(screening: Screening, num_vehicles: int, vehicle_capacity: int, shift_minutes: int) -> str`.

Định dạng (theo `src/data/readme.txt` và `backend/utils.py` của routing-PL), các dòng lần lượt là:
1. Header: `<n_customers> <n_lockers>`
2. `<num_vehicles> <capacity>`
3. Mỗi khách một dòng demand.
4. Dòng depot: `x y 0 shift 0 0`.
5. Mỗi khách một dòng: `x y earliest latest service type`.
6. Mỗi tủ một dòng: `x y 0 shift 0 4`.
7. Ma trận gán tủ, mỗi khách một dòng, mỗi tủ một cột. Khách type 1 có toàn bộ giá trị là 0.

Tọa độ in 4 chữ số thập phân.

- [ ] **Step 1: Viết test thất bại**

`tests/routing/test_instance.py`:
```python
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
```

- [ ] **Step 2: Chạy test để thấy thất bại**

Run: `uv run pytest tests/routing/test_instance.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'routing.instance'`

- [ ] **Step 3: Viết code**

`routing/instance.py`:
```python
from routing.validate import Screening


def build_instance(
    screening: Screening, num_vehicles: int, vehicle_capacity: int, shift_minutes: int
) -> str:
    """Render a routing-PL instance (see routing-PL src/data/readme.txt).

    Node ids inside the solver: depot 0, customers 1..n, lockers n+1..n+m.
    """
    orders = screening.routable
    lockers = screening.lockers
    lines = [f"{len(orders)} {len(lockers)}", f"{num_vehicles} {vehicle_capacity}"]
    lines += [str(r.order.demand) for r in orders]
    lines.append(f"0.0000 0.0000 0 {shift_minutes} 0 0")
    lines += [
        f"{r.x:.4f} {r.y:.4f} {r.earliest} {r.latest} {r.service} {int(r.mode)}" for r in orders
    ]
    lines += [f"{l.x:.4f} {l.y:.4f} 0 {shift_minutes} 0 4" for l in lockers]
    for r in orders:
        allowed = set(r.allowed_lockers)
        lines.append(" ".join("1" if i in allowed else "0" for i in range(len(lockers))))
    return "\n".join(lines)
```

- [ ] **Step 4: Chạy test để thấy thành công**

Run: `uv run pytest tests/routing/test_instance.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add routing/instance.py tests/routing/test_instance.py
git commit -m "feat(routing): render routing-PL instance text with per-order locker matrix"
```

---

### Task 4: HTTP client gọi solver

**Files:**
- Create: `routing/client.py`
- Test: `tests/routing/test_client.py`

**Interfaces:**
- Consumes: không có (độc lập).
- Produces:
  - `SolverError(RuntimeError)`.
  - Dataclass `SolverResponse(objective: float, vehicles: int, runtime: float, routes: list[list[str]], raw_routes: list[list[int]], delivery_nodes: list[int])`.
  - `SolverClient(base_url: str, timeout_s: float = 320.0, transport: httpx.BaseTransport | None = None)`, với các phương thức:
    - `.solve(instance_text: str, solver: str = "paco", size: str = "small") -> SolverResponse`
    - `.health() -> bool`

- [ ] **Step 1: Viết test thất bại**

`tests/routing/test_client.py`:
```python
import json

import httpx
import pytest

from routing.client import SolverClient, SolverError

OK = {
    "objective": 12.5,
    "vehicles": 1,
    "runtime": 0.4,
    "routes": [["0", "1", "2(3)", "0"]],
    "raw_routes": [[0, 1, 3, 0]],
    "delivery_nodes": [1, 3],
    "success": True,
    "error_message": "",
}


def client_returning(status=200, body=None, exc=None, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if exc is not None:
            raise exc
        return httpx.Response(status, json=body if body is not None else OK)

    return SolverClient("http://solver", transport=httpx.MockTransport(handler))


def test_solve_posts_instance_and_parses_response():
    seen = []
    resp = client_returning(seen=seen).solve("2 1\n...", solver="paco", size="medium")
    payload = json.loads(seen[0].content)
    assert seen[0].url.path == "/solve"
    assert payload == {"instance_content": "2 1\n...", "solver": "paco", "size": "medium"}
    assert resp.objective == 12.5
    assert resp.routes == [["0", "1", "2(3)", "0"]]
    assert resp.delivery_nodes == [1, 3]


def test_solver_failure_flag_raises_with_message():
    body = dict(OK, success=False, error_message="Solver timed out after 5 minutes")
    with pytest.raises(SolverError, match="timed out"):
        client_returning(body=body).solve("x")


def test_http_error_status_raises():
    with pytest.raises(SolverError, match="HTTP 500"):
        client_returning(status=500, body={"detail": "boom"}).solve("x")


def test_timeout_raises():
    with pytest.raises(SolverError, match="timeout"):
        client_returning(exc=httpx.ReadTimeout("slow")).solve("x")


def test_connection_error_raises():
    with pytest.raises(SolverError, match="cannot reach"):
        client_returning(exc=httpx.ConnectError("refused")).solve("x")


def test_health():
    assert client_returning(body={"status": "ok"}).health() is True
    assert client_returning(exc=httpx.ConnectError("refused")).health() is False
```

- [ ] **Step 2: Chạy test để thấy thất bại**

Run: `uv run pytest tests/routing/test_client.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'routing.client'`

- [ ] **Step 3: Viết code**

`routing/client.py`:
```python
from dataclasses import dataclass

import httpx


class SolverError(RuntimeError):
    pass


@dataclass(frozen=True)
class SolverResponse:
    objective: float
    vehicles: int
    runtime: float
    routes: list[list[str]]
    raw_routes: list[list[int]]
    delivery_nodes: list[int]


class SolverClient:
    """Client for the routing-PL FastAPI service (POST /solve)."""

    def __init__(
        self,
        base_url: str,
        timeout_s: float = 320.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self._http = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport)

    def solve(self, instance_text: str, solver: str = "paco", size: str = "small") -> SolverResponse:
        payload = {"instance_content": instance_text, "solver": solver, "size": size}
        try:
            resp = self._http.post("/solve", json=payload)
        except httpx.TimeoutException as e:
            raise SolverError(f"solver timeout: {e}") from e
        except httpx.HTTPError as e:
            raise SolverError(f"cannot reach solver: {e}") from e
        if resp.status_code != 200:
            raise SolverError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if not data.get("success"):
            raise SolverError(data.get("error_message") or "solver reported failure")
        return SolverResponse(
            objective=float(data["objective"]),
            vehicles=int(data["vehicles"]),
            runtime=float(data["runtime"]),
            routes=data["routes"],
            raw_routes=data["raw_routes"],
            delivery_nodes=data["delivery_nodes"],
        )

    def health(self) -> bool:
        try:
            return self._http.get("/health").status_code == 200
        except httpx.HTTPError:
            return False
```

- [ ] **Step 4: Chạy test để thấy thành công**

Run: `uv run pytest tests/routing/test_client.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add routing/client.py tests/routing/test_client.py
git commit -m "feat(routing): HTTP client for routing-PL /solve with typed errors"
```

---

### Task 5: `optimize_routes` (ánh xạ kết quả) + baseline mỗi đơn một chuyến

**Files:**
- Create: `routing/planner.py`, `routing/baseline.py`
- Test: `tests/routing/test_planner.py`, `tests/routing/test_baseline.py`

**Interfaces:**
- Consumes: `RoutingConfig`, `TravelPlane` (Task 1); models + `screen_orders`, `Screening` (Task 2); `build_instance` (Task 3); `SolverResponse`, `SolverError` (Task 4).
- Produces:
  - `solver_size(n_orders: int) -> str`: `"small"` nếu ≤ 25, `"medium"` nếu ≤ 50, ngược lại `"large"`.
  - `optimize_routes(batch: Batch, client, cfg: RoutingConfig = RoutingConfig()) -> RoutePlan`. `client` là bất kỳ object nào có `solve(instance_text, solver, size) -> SolverResponse`.
  - Dataclass `BaselineResult(travel_minutes: float, road_km: float, trips: int)`.
  - `one_trip_per_order(batch: Batch, cfg: RoutingConfig = RoutingConfig()) -> BaselineResult`.

Ánh xạ kết quả:
- Mỗi chuỗi trong `routes` có dạng `"0"` (depot), `"<c>"` (giao tận nhà khách `c`) hoặc `"<c>(<node>)"` (khách `c` nhận ở node tủ).
- Khách `c` (đánh số từ 1) tương ứng `screening.routable[c-1]`. Node tủ `node` tương ứng `screening.lockers[node - n - 1]`.
- Kiểm tra chéo: node của mỗi khách phải bằng `delivery_nodes[c-1]`, và mọi khách xuất hiện đúng một lần. Sai lệch → `SolverError("inconsistent solver output: ...")`.
- ETA (tính lại, **có cộng service time**, khác solver): mỗi xe bắt đầu `time=0` tại (0,0); `arr = time + int(dist)`; `eta = max(arr, earliest)` (với tủ thì earliest = 0); `late = eta > latest` (với tủ thì latest = `shift_minutes`); sau đó `time = eta + service`.

- [ ] **Step 1: Viết test thất bại cho planner**

`tests/routing/test_planner.py`:
```python
import pytest

from routing.client import SolverError, SolverResponse
from routing.config import RoutingConfig
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
    assert plan.source == "SIMULATED"


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
```

- [ ] **Step 2: Viết test thất bại cho baseline**

`tests/routing/test_baseline.py`:
```python
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
```

- [ ] **Step 3: Chạy test để thấy thất bại**

Run: `uv run pytest tests/routing/test_planner.py tests/routing/test_baseline.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'routing.planner'`

- [ ] **Step 4: Viết `routing/planner.py`**

```python
import math
import re
from typing import Protocol

from routing.client import SolverError, SolverResponse
from routing.config import RoutingConfig
from routing.geo import TravelPlane
from routing.instance import build_instance
from routing.models import Batch, RoutePlan, Stop, VehicleRoute
from routing.validate import Screening, screen_orders

_TOKEN = re.compile(r"^(\d+)(?:\((\d+)\))?$")


class Solver(Protocol):
    def solve(self, instance_text: str, solver: str = ..., size: str = ...) -> SolverResponse: ...


def solver_size(n_orders: int) -> str:
    """Pick the routing-PL parameter block tuned for this instance size."""
    if n_orders <= 25:
        return "small"
    if n_orders <= 50:
        return "medium"
    return "large"


def _map_routes(resp: SolverResponse, screening: Screening, cfg: RoutingConfig) -> list[VehicleRoute]:
    orders = screening.routable
    n = len(orders)
    seen: set[int] = set()
    routes: list[VehicleRoute] = []
    for raw in resp.routes:
        stops: list[Stop] = []
        time, cx, cy = 0, 0.0, 0.0
        for token in raw:
            if token == "0":
                continue
            m = _TOKEN.match(token)
            if not m:
                raise SolverError(f"inconsistent solver output: bad token {token!r}")
            cust = int(m.group(1))
            node = int(m.group(2)) if m.group(2) else cust
            if not 1 <= cust <= n or cust in seen:
                raise SolverError(f"inconsistent solver output: customer {cust}")
            if cust - 1 >= len(resp.delivery_nodes) or resp.delivery_nodes[cust - 1] != node:
                raise SolverError(f"inconsistent solver output: delivery node of customer {cust}")
            seen.add(cust)
            r = orders[cust - 1]
            if node == cust:
                kind, point_id, tx, ty = "home", None, r.x, r.y
                earliest, latest = r.earliest, r.latest
            else:
                locker = screening.lockers[node - n - 1]
                kind, point_id, tx, ty = "pickup", locker.point.point_id, locker.x, locker.y
                earliest, latest = 0, cfg.shift_minutes
            arr = time + int(math.hypot(tx - cx, ty - cy))
            eta = max(arr, earliest)
            stops.append(Stop(r.order.order_id, kind, point_id, eta, eta > latest))
            time, cx, cy = eta + r.service, tx, ty
        if stops:
            routes.append(VehicleRoute(stops))
    if len(seen) != n:
        missing = sorted(set(range(1, n + 1)) - seen)
        raise SolverError(f"inconsistent solver output: customers {missing} not routed")
    return routes


def optimize_routes(batch: Batch, client: Solver, cfg: RoutingConfig = RoutingConfig()) -> RoutePlan:
    plane = TravelPlane(batch.store.lat, batch.store.lng, cfg)
    screening = screen_orders(batch, plane, cfg)
    if not screening.routable:
        return RoutePlan(batch.store.store_id, [], 0.0, 0.0, 0, False, screening.at_risk, cfg.solver, 0.0)

    text = build_instance(screening, batch.num_vehicles, batch.vehicle_capacity, cfg.shift_minutes)
    resp = client.solve(text, solver=cfg.solver, size=solver_size(len(screening.routable)))
    routes = _map_routes(resp, screening, cfg)
    return RoutePlan(
        store_id=batch.store.store_id,
        routes=routes,
        travel_minutes=resp.objective,
        road_km=plane.minutes_to_km(resp.objective),
        vehicles_used=len(routes),
        exceeds_fleet=len(routes) > batch.num_vehicles,
        at_risk=screening.at_risk,
        solver=cfg.solver,
        runtime_s=resp.runtime,
    )
```

- [ ] **Step 5: Viết `routing/baseline.py`**

```python
import math
from dataclasses import dataclass

from routing.config import RoutingConfig
from routing.geo import TravelPlane
from routing.models import Batch, DeliveryMode
from routing.validate import screen_orders


@dataclass(frozen=True)
class BaselineResult:
    travel_minutes: float
    road_km: float
    trips: int


def one_trip_per_order(batch: Batch, cfg: RoutingConfig = RoutingConfig()) -> BaselineResult:
    """Manual dispatch today: one round trip from the store per order.

    Each order goes to its closest allowed delivery point (home and/or pickup points).
    """
    plane = TravelPlane(batch.store.lat, batch.store.lng, cfg)
    screening = screen_orders(batch, plane, cfg)
    total = 0.0
    for r in screening.routable:
        options = [math.hypot(screening.lockers[i].x, screening.lockers[i].y) for i in r.allowed_lockers]
        if r.mode != DeliveryMode.PICKUP:
            options.append(math.hypot(r.x, r.y))
        total += 2 * min(options)
    return BaselineResult(total, plane.minutes_to_km(total), len(screening.routable))
```

- [ ] **Step 6: Chạy test để thấy thành công**

Run: `uv run pytest tests/routing/test_planner.py tests/routing/test_baseline.py -v`
Expected: 9 passed

- [ ] **Step 7: Chạy toàn bộ test**

Run: `uv run pytest -v`
Expected: 31 passed, 0 failed

- [ ] **Step 8: Commit**

```bash
git add routing/planner.py routing/baseline.py tests/routing/test_planner.py tests/routing/test_baseline.py
git commit -m "feat(routing): optimize_routes maps PACO output to orders; add one-trip baseline"
```

---

### Task 6: CLI tiếng Việt + đợt đơn mẫu + container solver

**Files:**
- Create: `routing/cli.py`, `routing/examples/batch_q7.json`, `docker-compose.yml`
- Modify: `README.md` (thêm mục "Chạy adapter định tuyến")
- Test: `tests/routing/test_cli.py`, `tests/routing/test_integration.py`

**Interfaces:**
- Consumes: `optimize_routes` (Task 5), `one_trip_per_order`, `BaselineResult` (Task 5), `SolverClient`, `SolverError` (Task 4), models (Task 2).
- Produces:
  - `batch_from_dict(d: dict) -> Batch`, với `mode` là chuỗi `"home" | "pickup" | "flexible"`.
  - `format_plan(plan: RoutePlan, baseline: BaselineResult) -> str`.
  - `main(argv: list[str] | None = None, client_factory=SolverClient) -> int`. Exit 0 khi thành công, 1 khi input lỗi, 2 khi solver lỗi.
  - Lệnh: `uv run python -m routing.cli routing/examples/batch_q7.json [--solver-url URL] [--json]`.

- [ ] **Step 1: Tạo đợt đơn mẫu `routing/examples/batch_q7.json`**

Toàn bộ tọa độ là giả lập, xung quanh khu Q.7 TP.HCM.
```json
{
  "source": "SIMULATED",
  "store": {"store_id": "Q7-01", "lat": 10.7340, "lng": 106.7210},
  "num_vehicles": 3,
  "vehicle_capacity": 8,
  "pickup_points": [
    {"point_id": "PP-SKYGARDEN", "lat": 10.7290, "lng": 106.7070},
    {"point_id": "PP-HUNGVUONG", "lat": 10.7275, "lng": 106.7110}
  ],
  "orders": [
    {"order_id": "D001", "lat": 10.7380, "lng": 106.7225, "demand": 2, "earliest_min": 0,  "latest_min": 60,  "mode": "home"},
    {"order_id": "D002", "lat": 10.7295, "lng": 106.7080, "demand": 1, "earliest_min": 0,  "latest_min": 240, "mode": "pickup", "pickup_point_id": "PP-SKYGARDEN"},
    {"order_id": "D003", "lat": 10.7268, "lng": 106.7115, "demand": 1, "earliest_min": 0,  "latest_min": 120, "mode": "flexible"},
    {"order_id": "D004", "lat": 10.7412, "lng": 106.7190, "demand": 3, "earliest_min": 30, "latest_min": 90,  "mode": "home"},
    {"order_id": "D005", "lat": 10.7320, "lng": 106.7300, "demand": 1, "earliest_min": 0,  "latest_min": 45,  "mode": "home"},
    {"order_id": "D006", "lat": 10.7282, "lng": 106.7105, "demand": 2, "earliest_min": 0,  "latest_min": 240, "mode": "pickup", "pickup_point_id": "PP-HUNGVUONG"},
    {"order_id": "D007", "lat": 10.7355, "lng": 106.7150, "demand": 1, "earliest_min": 15, "latest_min": 75,  "mode": "flexible"},
    {"order_id": "D008", "lat": 10.7250, "lng": 106.7240, "demand": 2, "earliest_min": 0,  "latest_min": 120, "mode": "home"},
    {"order_id": "D009", "lat": 10.7340, "lng": 106.7210, "demand": 1, "earliest_min": 0,  "latest_min": 240, "mode": "pickup", "pickup_point_id": "Q7-01-counter"},
    {"order_id": "D010", "lat": 10.7400, "lng": 106.7280, "demand": 2, "earliest_min": 0,  "latest_min": 100, "mode": "home"},
    {"order_id": "D011", "lat": 10.7300, "lng": 106.7060, "demand": 1, "earliest_min": 0,  "latest_min": 90,  "mode": "flexible"},
    {"order_id": "D012", "lat": 10.7600, "lng": 106.7600, "demand": 1, "earliest_min": 0,  "latest_min": 10,  "mode": "home"}
  ]
}
```

D012 được cố ý đặt ở xa với khung giờ rất ngắn, để demo cảnh báo "đơn có nguy cơ".

- [ ] **Step 2: Viết test thất bại cho CLI**

`tests/routing/test_cli.py`:
```python
import json
from pathlib import Path

from routing.cli import batch_from_dict, main
from routing.client import SolverError, SolverResponse
from routing.models import DeliveryMode

EXAMPLE = Path(__file__).resolve().parents[2] / "routing" / "examples" / "batch_q7.json"


def test_batch_from_dict_parses_modes_and_points():
    batch = batch_from_dict(json.loads(EXAMPLE.read_text()))
    assert batch.store.store_id == "Q7-01"
    assert len(batch.orders) == 12
    assert batch.orders[1].mode == DeliveryMode.PICKUP
    assert batch.orders[1].pickup_point_id == "PP-SKYGARDEN"
    assert batch.orders[2].mode == DeliveryMode.FLEXIBLE
    assert [p.point_id for p in batch.pickup_points] == ["PP-SKYGARDEN", "PP-HUNGVUONG"]


class EchoSolver:
    """Returns one route visiting every customer in input order (always consistent)."""

    def __init__(self, url, **_):
        pass

    def solve(self, instance_text, solver="paco", size="small"):
        lines = instance_text.splitlines()
        n, m = map(int, lines[0].split())
        matrix = lines[-n:] if m else []
        tokens, nodes = ["0"], []
        for c in range(1, n + 1):
            ctype = int(lines[2 + n + c].split()[5])
            row = matrix[c - 1].split()
            if ctype == 2:
                node = n + 1 + row.index("1")
                tokens.append(f"{c}({node})")
            else:
                node = c
                tokens.append(str(c))
            nodes.append(node)
        tokens.append("0")
        return SolverResponse(30.0, 1, 0.2, [tokens], [], nodes)


class BrokenSolver:
    def __init__(self, url, **_):
        pass

    def solve(self, *a, **k):
        raise SolverError("cannot reach solver: refused")


def test_main_prints_vietnamese_summary(capsys):
    code = main([str(EXAMPLE)], client_factory=EchoSolver)
    out = capsys.readouterr().out
    assert code == 0
    assert "SIMULATED" in out
    assert "Quãng đường ước tính" in out
    assert "mỗi đơn một chuyến" in out
    assert "D012" in out and "Đơn có nguy cơ" in out


def test_main_json_output(capsys):
    code = main([str(EXAMPLE), "--json"], client_factory=EchoSolver)
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["plan"]["source"] == "SIMULATED"
    assert data["baseline"]["trips"] == 11


def test_main_solver_failure_exits_2_without_route(capsys):
    code = main([str(EXAMPLE)], client_factory=BrokenSolver)
    captured = capsys.readouterr()
    assert code == 2
    assert "Không gọi được solver" in captured.err
    assert "Xe 1" not in captured.out


def test_main_bad_input_exits_1(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    assert main([str(bad)], client_factory=EchoSolver) == 1
    assert "Dữ liệu đợt đơn không hợp lệ" in capsys.readouterr().err
```

- [ ] **Step 3: Chạy test để thấy thất bại**

Run: `uv run pytest tests/routing/test_cli.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'routing.cli'`

- [ ] **Step 4: Viết `routing/cli.py`**

```python
import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from routing.baseline import BaselineResult, one_trip_per_order
from routing.client import SolverClient, SolverError
from routing.config import RoutingConfig
from routing.models import Batch, DeliveryMode, Order, PickupPoint, RoutePlan, Store
from routing.planner import optimize_routes

_MODES = {"home": DeliveryMode.HOME, "pickup": DeliveryMode.PICKUP, "flexible": DeliveryMode.FLEXIBLE}
_REASONS_VI = {
    "invalid_demand": "số lượng không hợp lệ",
    "over_capacity": "vượt tải một xe",
    "window_closed": "khung giờ đã qua",
    "unreachable_in_window": "không kịp giao trong khung giờ",
    "unknown_pickup_point": "điểm nhận không tồn tại",
}


def batch_from_dict(d: dict) -> Batch:
    s = d["store"]
    return Batch(
        store=Store(s["store_id"], float(s["lat"]), float(s["lng"])),
        orders=[
            Order(
                o["order_id"], float(o["lat"]), float(o["lng"]), int(o["demand"]),
                float(o["earliest_min"]), float(o["latest_min"]), _MODES[o["mode"]],
                float(o.get("service_min", 3.0)), o.get("pickup_point_id"),
            )
            for o in d["orders"]
        ],
        pickup_points=[
            PickupPoint(p["point_id"], float(p["lat"]), float(p["lng"]))
            for p in d.get("pickup_points", [])
        ],
        num_vehicles=int(d["num_vehicles"]),
        vehicle_capacity=int(d["vehicle_capacity"]),
    )


def format_plan(plan: RoutePlan, baseline: BaselineResult) -> str:
    lines = [
        f"FreshMesh — lộ trình đợt giao (dữ liệu: {plan.source})",
        f"Cửa hàng: {plan.store_id} | Solver: {plan.solver.upper()} | Thời gian giải: {plan.runtime_s:.1f}s",
        f"Xe dùng: {plan.vehicles_used}"
        + (" (VƯỢT số xe hiện có)" if plan.exceeds_fleet else ""),
        f"Quãng đường ước tính: {plan.road_km:.1f} km (đã gồm hệ số đường vòng)",
    ]
    if baseline.road_km > 0:
        saving = 100 * (1 - plan.road_km / baseline.road_km)
        lines.append(
            f"So với mỗi đơn một chuyến: {baseline.road_km:.1f} km → tiết kiệm {saving:.0f}%"
        )
    for i, route in enumerate(plan.routes, start=1):
        parts = []
        for s in route.stops:
            where = "tận nhà" if s.kind == "home" else f"điểm nhận {s.pickup_point_id}"
            flag = " ⚠ trễ" if s.late else ""
            parts.append(f"{s.order_id} ({where}, ETA +{s.eta_min}'){flag}")
        lines.append(f"Xe {i}: " + " → ".join(parts))
    if plan.at_risk:
        lines.append("Đơn có nguy cơ (không đưa vào lộ trình, cần bạn xử lý):")
        lines += [f"  - {r.order_id}: {_REASONS_VI.get(r.reason, r.reason)}" for r in plan.at_risk]
    lines.append("Giả định: tốc độ trung bình và hệ số đường vòng là ước tính; bạn duyệt trước khi gửi cho shipper.")
    return "\n".join(lines)


def main(argv: list[str] | None = None, client_factory=SolverClient) -> int:
    parser = argparse.ArgumentParser(prog="routing.cli", description="Tính lộ trình giao cho một đợt đơn")
    parser.add_argument("batch", type=Path)
    parser.add_argument("--solver-url", default=os.environ.get("FRESHMESH_SOLVER_URL", "http://localhost:8000"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    cfg = RoutingConfig()

    try:
        batch = batch_from_dict(json.loads(args.batch.read_text(encoding="utf-8")))
        baseline = one_trip_per_order(batch, cfg)
    except (OSError, KeyError, ValueError, TypeError) as e:
        print(f"Dữ liệu đợt đơn không hợp lệ: {e}", file=sys.stderr)
        return 1

    try:
        plan = optimize_routes(batch, client_factory(args.solver_url, timeout_s=cfg.solver_timeout_s), cfg)
    except SolverError as e:
        print(f"Không gọi được solver: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"plan": asdict(plan), "baseline": asdict(baseline)}, ensure_ascii=False, indent=2))
    else:
        print(format_plan(plan, baseline))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Chạy test CLI để thấy thành công**

Run: `uv run pytest tests/routing/test_cli.py -v`
Expected: 5 passed. Nếu `test_main_json_output` báo `trips` khác 11, in `plan.at_risk` ra để xem đơn nào bị loại. Chỉ D012 được phép nằm trong `at_risk`. Nếu có đơn khác bị loại, sửa tọa độ hoặc khung giờ trong JSON mẫu (không sửa test), vì mỗi đơn trừ D012 đều phải phục vụ được.

- [ ] **Step 6: Tạo `docker-compose.yml` ở gốc repo**

```yaml
services:
  solver:
    build:
      context: ./routing/routing-PL
    image: freshmesh-solver:routing-pl-32488ce
    container_name: freshmesh-solver
    ports:
      - "8000:8000"   # routing-PL FastAPI (/solve, /health)
      - "8501:8501"   # routing-PL Streamlit (internal solver comparison)
    restart: unless-stopped
```

Run: `docker compose up -d --build solver` (chạy nền; lần build đầu mất vài phút)
Run: `curl -s http://localhost:8000/health`
Expected: `{"status":"ok"}`

- [ ] **Step 7: Viết integration test**

`tests/routing/test_integration.py`:
```python
import json
import os
from pathlib import Path

import pytest

from routing.cli import batch_from_dict
from routing.client import SolverClient
from routing.planner import optimize_routes

pytestmark = pytest.mark.integration

EXAMPLE = Path(__file__).resolve().parents[2] / "routing" / "examples" / "batch_q7.json"
URL = os.environ.get("FRESHMESH_SOLVER_URL", "http://localhost:8000")


def test_example_batch_against_real_solver():
    client = SolverClient(URL)
    assert client.health(), f"solver not reachable at {URL}; run: docker compose up -d solver"
    batch = batch_from_dict(json.loads(EXAMPLE.read_text()))
    plan = optimize_routes(batch, client)
    routed = [s.order_id for r in plan.routes for s in r.stops]
    assert sorted(routed) == sorted(o.order_id for o in batch.orders if o.order_id != "D012")
    assert [r.order_id for r in plan.at_risk] == ["D012"]
    assert plan.road_km > 0
```

Run: `uv run pytest -m integration -v`
Expected: 1 passed

Run: `uv run pytest -v`
Expected: 36 passed, 1 deselected (integration test bị loại mặc định qua `addopts`)

- [ ] **Step 8: Chạy CLI thật**

Run: `uv run python -m routing.cli routing/examples/batch_q7.json`
Expected:
- Có các dòng tiêu đề với `SIMULATED`, `Solver: PACO`, `Quãng đường ước tính`, dòng so sánh "mỗi đơn một chuyến", ít nhất một dòng `Xe 1:`.
- D012 nằm trong "Đơn có nguy cơ".
- Ghi lại % tiết kiệm vào commit message bên dưới.

- [ ] **Step 9: Cập nhật README**

Thêm vào cuối `README.md`:
````markdown
## Chạy adapter định tuyến (PACO)

```bash
git submodule update --init          # lấy routing-PL
uv sync
docker compose up -d --build solver  # container solver ở cổng 8000
uv run python -m routing.cli routing/examples/batch_q7.json
uv run pytest                        # unit test (không cần Docker)
uv run pytest -m integration         # cần container solver
```

Dữ liệu trong `routing/examples/` là **giả lập** (SIMULATED).
````

- [ ] **Step 10: Commit**

```bash
git add routing/cli.py routing/examples/batch_q7.json docker-compose.yml README.md tests/routing/test_cli.py tests/routing/test_integration.py
git commit -m "feat(routing): Vietnamese CLI, sample Q7 batch, solver container (PACO saves <X>% km vs one-trip)"
```

(Thay `<X>` bằng số đo được ở Step 8.)

---

### Task 7: Đo runtime solver theo kích thước đợt

**Files:**
- Create: `scripts/probe_solver.py`, `docs/solver-probe.md`

**Interfaces:**
- Consumes: `SolverClient` (Task 4), `optimize_routes`, `solver_size` (Task 5), models (Task 2), `RoutingConfig` (Task 1).
- Produces: `docs/solver-probe.md` (bảng runtime). Nếu cần, giảm `RoutingConfig.max_orders_per_batch`.

- [ ] **Step 1: Viết script**

`scripts/probe_solver.py`:
```python
"""Measure routing-PL PACO runtime on simulated batches of 25/50/100 orders.

Usage: uv run python scripts/probe_solver.py [--url http://localhost:8000] [--runs 3]
"""
import argparse
import math
import random
import statistics
import time

from routing.client import SolverClient
from routing.models import Batch, DeliveryMode, Order, PickupPoint, Store
from routing.planner import optimize_routes, solver_size

LAT0, LNG0 = 10.7340, 106.7210


def _offset(rng: random.Random, radius_km: float) -> tuple[float, float]:
    r = radius_km * math.sqrt(rng.random())
    a = rng.random() * 2 * math.pi
    return (
        LAT0 + r * math.cos(a) / 110.574,
        LNG0 + r * math.sin(a) / (111.320 * math.cos(math.radians(LAT0))),
    )


def simulated_batch(n: int, seed: int) -> Batch:
    rng = random.Random(seed)
    points = [PickupPoint(f"PP{i}", *_offset(rng, 2.5)) for i in range(4)]
    modes = [DeliveryMode.HOME, DeliveryMode.FLEXIBLE, DeliveryMode.PICKUP]
    orders = []
    for i in range(n):
        mode = rng.choice(modes)
        start = rng.choice([0, 30, 60])
        orders.append(
            Order(
                f"D{i:03d}", *_offset(rng, 4.0), rng.randint(1, 3), start, start + 120, mode,
                3.0, rng.choice(points).point_id if mode == DeliveryMode.PICKUP else None,
            )
        )
    return Batch(Store("PROBE", LAT0, LNG0), orders, points, num_vehicles=max(2, n // 8), vehicle_capacity=12)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8000")
    p.add_argument("--runs", type=int, default=3)
    args = p.parse_args()
    client = SolverClient(args.url)
    print("| orders | size | wall s (median) | solver s (median) | km (median) | vehicles |")
    print("|---|---|---|---|---|---|")
    for n in (25, 50, 100):
        walls, solver_s, kms, vehicles = [], [], [], []
        for run in range(args.runs):
            t0 = time.perf_counter()
            plan = optimize_routes(simulated_batch(n, seed=run), client)
            walls.append(time.perf_counter() - t0)
            solver_s.append(plan.runtime_s)
            kms.append(plan.road_km)
            vehicles.append(plan.vehicles_used)
        print(
            f"| {n} | {solver_size(n)} | {statistics.median(walls):.1f} | "
            f"{statistics.median(solver_s):.1f} | {statistics.median(kms):.1f} | {statistics.median(vehicles):.0f} |"
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Chạy script với container đang bật**

Run: `uv run python scripts/probe_solver.py --runs 3` (chạy nền; có thể mất vài phút)
Expected: bảng 3 dòng, không có exception.

- [ ] **Step 3: Ghi kết quả và quyết định giới hạn**

Tạo `docs/solver-probe.md` gồm:
- Bảng in ra ở Step 2.
- Thông số máy (`nproc`, RAM) và commit routing-PL (`32488ce`).
- Kết luận theo **quy tắc cố định** sau:
  - Nếu wall time median với 100 đơn ≤ 120 giây: giữ `max_orders_per_batch = 100`.
  - Nếu lớn hơn: đặt `max_orders_per_batch` bằng kích thước lớn nhất trong {25, 50} có median ≤ 120 giây, sửa giá trị mặc định trong `routing/config.py`, rồi chạy lại `uv run pytest -v` (test `test_batch_over_limit_raises` đọc giới hạn từ config nên vẫn đúng).

Lý do ngưỡng 120 giây: đợt gom 30 phút phải trả lộ trình đủ sớm, và service của routing-PL tự ngắt ở 300 giây.

- [ ] **Step 4: Commit**

```bash
git add scripts/probe_solver.py docs/solver-probe.md routing/config.py
git commit -m "chore(routing): probe PACO runtime by batch size and record limits"
```

---

## Self-review (đã chạy khi viết plan)

- **Đối chiếu spec mục 6:** UTM 48N (Task 1), hệ số 1.3 (Task 1), gom theo đợt và ≤ 100 đơn (Task 2, Task 7), mỗi cửa hàng là một depot (Task 5), ánh xạ type 1/2/3 (Task 2–3), quầy cửa hàng làm điểm nhận (Task 2), giới hạn và cache khi demo (giới hạn ở Task 7; **cache để lại cho plan API/UI**, vì cache chỉ có ý nghĩa khi có server), benchmark solver (baseline thủ công ở Task 5–6; **SA/ALNS để lại cho plan polish**, lý do ghi ở Global Constraints).
- **Mục 2.3 luồng 3:** CLI tạo ra lộ trình, km, số xe, đơn có nguy cơ trễ. Bản đồ và nút xác nhận thuộc plan UI.
- **Nhất quán tên:** `screen_orders`, `Screening`, `RoutableOrder`, `LockerNode`, `build_instance`, `SolverClient.solve`, `SolverResponse`, `optimize_routes`, `solver_size`, `one_trip_per_order`, `BaselineResult`, `batch_from_dict`, `format_plan`, `main`: dùng giống nhau ở mọi task.
- **Số lượng test:** geo 4 + validate 10 + instance 2 + client 6 + planner 8 + baseline 1 + cli 5 = 36 unit test, cộng 1 integration test.
