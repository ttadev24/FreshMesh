"""The three decision cards of the morning brief, each computed by the same service call as its panel.

No LLM: ``headline_vi`` and ``due_vi`` are built from the card's own numbers, so every figure shown is a
field of the tool result (same rule as the agent's number guardrail). Percent values are 0–100.
"""

from __future__ import annotations

from typing import Any

from api.repo import SkuInfo, StoreInfo
from api.services import DEFAULT_NOW_HOUR, Services
from decision.text import pct, units, vnd

REPLENISH_CATEGORIES = ("vegetable", "meat")  # flow 1 of the demo ("Nhập rau và thịt cho mai thế nào?")
SURPLUS_CATEGORIES = ("vegetable",)  # flow 2 ("Cửa hàng nào còn nhiều rau tồn chiều nay?")


def _metric(key: str, label_vi: str, value: float | int | None, unit: str) -> dict[str, Any]:
    return {"key": key, "label_vi": label_vi, "value": value, "unit": unit}


def _km(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " km"


def _prov(result: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "sources": list(result.get("sources", [])),
        "source_labels_vi": list(result.get("source_labels_vi", [])),
    }


def replenish_card(
    services: Services, chain_id: str, store: StoreInfo, skus: list[SkuInfo]
) -> dict[str, Any]:
    r = services.inventory_plan(chain_id, store.store_id, skus, horizon_days=1)
    plan = next(p for p in r["plans"] if p["name"] == r["recommended_plan"])
    n_skus = sum(1 for ln in plan["lines"] if ln.get("qty", 0) > 0)
    return {
        "kind": "replenish",
        "title_vi": "Nhập hàng cho ngày mai",
        "store_id": store.store_id,
        "store_name": store.name,
        "headline_vi": (
            f"Nhập theo phương án {plan['label_vi']}: {vnd(plan['total_cost_vnd'])} cho {n_skus} mặt hàng, "
            f"dự kiến bỏ {pct(plan['expected_waste_pct'])}, hết hàng {pct(plan['expected_stockout_pct'])}."
        ),
        "metrics": [
            _metric("total_cost_vnd", "Tiền nhập", plan["total_cost_vnd"], "vnd"),
            _metric("expected_waste_pct", "Hàng bỏ dự kiến", plan["expected_waste_pct"], "pct"),
            _metric("expected_stockout_pct", "Hết hàng dự kiến", plan["expected_stockout_pct"], "pct"),
            _metric("service_level_pct", "Xác suất không hết hàng", plan["service_level_pct"], "pct"),
            _metric("sku_count", "Mặt hàng cần nhập", n_skus, "count"),
        ],
        "status": "attention" if r["drift"].get("alert") else "ok",
        "confidence": r.get("confidence"),
        "due_vi": None,  # no supplier cut-off in the data: none is invented
        "action": {
            "label_vi": "Xem 3 phương án",
            "panel": "inventory",
            "store_id": store.store_id,
            "prompt_vi": "Nhập rau và thịt cho mai thế nào?",
        },
        **_prov(r),
    }


def _markdown_start(markdown_plans: list[dict[str, Any]]) -> str | None:
    starts = [
        s["start"] for p in markdown_plans for s in p.get("schedule", []) if s.get("discount_pct", 0) > 0
    ]
    return f"Bắt đầu giảm giá lúc {min(starts)[11:16]}" if starts else None


def surplus_card(
    services: Services, chain_id: str, store_ids: list[str], skus: list[SkuInfo]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(card, today's transfer flows). ``store_ids``: all stores for an owner, the own store for a manager."""
    found = services.surplus_stores(chain_id, store_ids, skus, now_hour=DEFAULT_NOW_HOUR)
    top_id = found["top_store_id"]
    base = {"kind": "surplus", "title_vi": "Xử lý hàng tươi tồn chiều nay", "confidence": None}
    if top_id is None:
        return {
            **base,
            "store_id": None,
            "store_name": None,
            "headline_vi": "Không cửa hàng nào dự kiến dư hàng tươi hôm nay.",
            "metrics": [],
            "status": "none",
            "due_vi": None,
            "action": None,
            **_prov(found),
        }, []
    top = next(s for s in found["stores"] if s["store_id"] == top_id)
    r = services.transfer(chain_id, top_id, skus, now_hour=DEFAULT_NOW_HOUR)
    summ = r["summary"]
    flows: dict[str, int] = {}
    for line in r["transfer"].get("lines", []):
        flows[line["to_store_id"]] = flows.get(line["to_store_id"], 0) + int(line["qty"])
    due = {
        "markdown": _markdown_start(r["markdown"]),
        "transfer": f"Điều chuyển trong {r['routing_defaults']['window_minutes']} phút",
    }.get(summ["recommended"])
    return {
        **base,
        "store_id": top_id,
        "store_name": r["store_name"],
        "headline_vi": (
            f"{r['store_name']} dự kiến ế {units(top['expected_unsold_units'])} đơn vị rau. "
            + summ["recommendation_vi"]
        ),
        "metrics": [
            _metric("units_left_now", "Còn trên kệ lúc này", top["units_left_now"], "units"),
            _metric("expected_unsold_units", "Dự kiến ế", top["expected_unsold_units"], "units"),
            _metric("markdown_gain_vnd", "Giảm giá thu thêm", summ["markdown_gain_vnd"], "vnd"),
            _metric("transfer_gain_vnd", "Điều chuyển thu thêm", summ["transfer_gain_vnd"], "vnd"),
        ],
        "status": "attention" if summ["recommended"] != "none" else "ok",
        "confidence": r.get("confidence"),
        "due_vi": due,
        "action": {
            "label_vi": "So sánh giảm giá và điều chuyển",
            "panel": "stock",
            "store_id": top_id,
            "prompt_vi": "Cửa hàng nào còn nhiều rau tồn chiều nay? Nên giảm giá hay điều chuyển?",
        },
        **_prov(r),
    }, [{"kind": "transfer", "from": top_id, "to": to, "units": n} for to, n in sorted(flows.items())]


def delivery_card(services: Services, chain_id: str, store: StoreInfo) -> dict[str, Any]:
    r = services.routing_plan(chain_id, store.store_id)
    n_orders = r["batch"]["n_orders"]
    risk = r["orders_at_risk"]
    headline = f"Gom {r['orders_routed']}/{n_orders} đơn vào {r['vehicles_used']} xe, {_km(r['km'])}"
    if r.get("saving_pct") is not None:
        headline += f", ít hơn {pct(r['saving_pct'])} km so với giao từng đơn"
    headline += f". {risk} đơn có nguy cơ trễ." if risk else "."
    return {
        "kind": "delivery",
        "title_vi": "Giao đơn online đợt này",
        "store_id": store.store_id,
        "store_name": store.name,
        "headline_vi": headline,
        "metrics": [
            _metric("orders", "Đơn trong đợt", n_orders, "count"),
            _metric("vehicles_used", "Số xe", r["vehicles_used"], "count"),
            _metric("total_km", "Quãng đường", r["km"], "km"),
            _metric("saving_pct", "Tiết kiệm km", r.get("saving_pct"), "pct"),
            _metric("at_risk_orders", "Đơn nguy cơ trễ", risk, "count"),
            _metric("late_stops", "Điểm dừng trễ", r.get("late_stops", 0), "count"),
        ],
        "status": "attention" if risk or r.get("late_stops") else "ok",
        "confidence": r.get("confidence"),
        "due_vi": f"Đợt giao bắt đầu {r['batch']['batch_start'][11:16]}",
        "action": {
            "label_vi": "Xem lộ trình",
            "panel": "routes",
            "store_id": store.store_id,
            "prompt_vi": "Gom đơn online đợt này và lập lộ trình giao.",
        },
        **_prov(r),
    }
