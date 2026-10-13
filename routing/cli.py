import argparse
import json
import os
import sys
from dataclasses import asdict, replace
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
        f"FreshMesh — lộ trình đợt giao (nguồn dữ liệu: {plan.source})",
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


def _get_default_solver_url() -> str:
    url = os.environ.get("FRESHMESH_SOLVER_URL")
    if url:
        return url
    port = os.environ.get("FRESHMESH_SOLVER_PORT")
    if port:
        return f"http://localhost:{port}"
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("FRESHMESH_SOLVER_URL="):
                return line.split("=", 1)[1].strip()
    return "http://localhost:8000"


def main(argv: list[str] | None = None, client_factory=SolverClient) -> int:
    parser = argparse.ArgumentParser(prog="routing.cli", description="Tính lộ trình giao cho một đợt đơn")
    parser.add_argument("batch", type=Path)
    parser.add_argument("--solver-url", default=_get_default_solver_url())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    cfg = RoutingConfig()

    try:
        raw = json.loads(args.batch.read_text(encoding="utf-8"))
        batch = batch_from_dict(raw)
        source_label = str(raw.get("source") or RoutePlan.source)
        baseline = one_trip_per_order(batch, cfg)
    except (OSError, KeyError, ValueError, TypeError) as e:
        print(f"Dữ liệu đợt đơn không hợp lệ: {e}", file=sys.stderr)
        return 1

    try:
        plan = optimize_routes(batch, client_factory(args.solver_url, timeout_s=cfg.solver_timeout_s), cfg)
    except SolverError as e:
        print(f"Không gọi được solver: {e}", file=sys.stderr)
        return 2
    plan = replace(plan, source=source_label)

    if args.json:
        print(json.dumps({"plan": asdict(plan), "baseline": asdict(baseline)}, ensure_ascii=False, indent=2))
    else:
        print(format_plan(plan, baseline))
    return 0


if __name__ == "__main__":
    sys.exit(main())
