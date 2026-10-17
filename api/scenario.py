"""'Nếu… thì…' for the inventory plan (``POST /api/inventory/scenario``): the same store, SKUs and plan
rules, with a known event switched on for every forecast day (``forecasting.drivers.SCENARIO_FEATURES``).
Answers "what would change the decision" in units and money, line by line."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from api.errors import ApiError
from api.repo import SkuInfo
from decision.text import pct, units, vnd
from forecasting.drivers import SCENARIO_FEATURES

ASSUMPTIONS_VI = [
    "Mức tăng/giảm nhu cầu là hiệu ứng mô hình học từ lịch sử bán của chính chuỗi (tương quan, không phải "
    "cam kết); cùng quy tắc lập phương án, chỉ đổi dự báo.",
    "Không có kịch bản mưa: mô hình chỉ biết lượng mưa trung bình theo tháng, nên 'mai mưa to' sẽ là ngoại suy.",
]


def _p50_by_sku(plan_out: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for r in plan_out["forecast"]:
        out[r["sku_id"]] += r["p50"]
    return out


def _summary(plan_out: dict[str, Any], name: str) -> dict[str, Any]:
    plan = next(p for p in plan_out["plans"] if p["name"] == name)
    keep = ("total_cost_vnd", "expected_waste_pct", "expected_stockout_pct", "expected_leftover_units")
    return {k: plan[k] for k in keep} | {"demand_p50_units": round(sum(_p50_by_sku(plan_out).values()), 1)}


def compare_scenario(
    services: Any,
    chain_id: str,
    store_id: str,
    skus: Sequence[SkuInfo],
    *,
    horizon_days: int,
    scenario: dict[str, bool],
) -> dict[str, Any]:
    on = {k: True for k, v in scenario.items() if v}
    if not on:
        raise ApiError(422, "empty_scenario", "Chọn ít nhất một tình huống: khuyến mãi hoặc ngày lễ / sự kiện.")
    base = services.inventory_plan(chain_id, store_id, skus, horizon_days=horizon_days)
    alt = services.inventory_plan(chain_id, store_id, skus, horizon_days=horizon_days, scenario=on)
    name = base["recommended_plan"]  # same plan rule on both sides, so only the forecast differs
    qty = {p: {ln["sku_id"]: ln for ln in next(x for x in out["plans"] if x["name"] == name)["lines"]}
           for p, out in (("base", base), ("alt", alt))}  # fmt: skip
    p50 = {"base": _p50_by_sku(base), "alt": _p50_by_sku(alt)}
    lines = [
        {
            "sku_id": sku_id,
            "sku_name": ln["sku_name"],
            "base_p50": round(p50["base"][sku_id], 1),
            "scenario_p50": round(p50["alt"][sku_id], 1),
            "base_qty": ln["qty"],
            "scenario_qty": qty["alt"][sku_id]["qty"],
            "delta_qty": qty["alt"][sku_id]["qty"] - ln["qty"],
            "delta_cost_vnd": qty["alt"][sku_id]["cost_vnd"] - ln["cost_vnd"],
        }
        for sku_id, ln in qty["base"].items()
    ]
    lines.sort(key=lambda r: (-abs(r["delta_qty"]), r["sku_id"]))
    b, a = _summary(base, name), _summary(alt, name)
    label = " + ".join(SCENARIO_FEATURES[k] for k in on)
    demand_change = 100 * (a["demand_p50_units"] - b["demand_p50_units"]) / max(b["demand_p50_units"], 1.0)
    units_change = sum(r["delta_qty"] for r in lines)
    summary = (
        f"Nếu có {label.lower()}: nhu cầu dự báo {'+' if demand_change >= 0 else ''}{pct(demand_change)} "
        f"({units(b['demand_p50_units'])} → {units(a['demand_p50_units'])} đơn vị). "
        f"Phương án {base['recommended_label_vi']} đổi từ {vnd(b['total_cost_vnd'])} thành "
        f"{vnd(a['total_cost_vnd'])} ({'+' if units_change >= 0 else ''}{units_change} đơn vị hàng)."
    )
    return {
        "store_id": store_id,
        "store_name": base["store_name"],
        "order_date": base["order_date"],
        "horizon_days": horizon_days,
        "scenario": on,
        "scenario_label_vi": label,
        "plan_name": name,
        "plan_label_vi": base["recommended_label_vi"],
        "base": b,
        "with_scenario": a,
        "lines": lines,
        "summary_vi": summary,
        "assumptions_vi": ASSUMPTIONS_VI,
        "sources": base.get("sources", []),
        "source_labels_vi": base.get("source_labels_vi", []),
    }
