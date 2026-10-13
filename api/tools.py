"""Real agent tools (names agreed in the master plan) wired to the service layer.

Read tools: forecast_demand, plan_inventory, suggest_markdown, transfer_stock, optimize_routes, query_data,
render_chart. Draft tools (only create drafts; approval happens in the API): create_purchase_order,
apply_markdown, create_transfer, dispatch_routes. Draft payloads are always computed by the server from
the DB and the real models; numbers supplied by the caller are never trusted.

Store resolution: ``store_id`` may be "A-CH3" or "CH3"; when missing, ``ctx.extras["default_store_id"]``,
then the user's own store, then the chain's first store. Store managers can only use their own store.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from agent.charts import make_render_chart_tool
from agent.sql_guard import make_query_data_tool
from agent.tools import Tool, ToolContext, ToolError, ToolRegistry, ToolResult
from api.drafts import SqlDraftStore
from api.errors import ApiError
from api.repo import ensure_store_access, resolve_store_id
from api.services import DEFAULT_NOW_HOUR, Services, plan_key
from data_sim import SOURCE, chain_db_path
from decision.text import units, vnd

_STR_LIST = {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 64}, "maxItems": 50}
_STORE = {"type": "string", "maxLength": 32, "description": "Mã cửa hàng, ví dụ A-CH3 hoặc CH3."}
_CATS = {
    **_STR_LIST,
    "description": "Nhóm hàng: rau, thit, ca, trung, sua, dau_hu (hoặc vegetable, meat...).",
}
_SKUS = {**_STR_LIST, "description": "Mã mặt hàng, ví dụ SKU_RAU_MUONG."}
_HORIZON = {"type": "integer", "minimum": 1, "maximum": 7}
_NOW_HOUR = {
    "type": "integer",
    "minimum": 6,
    "maximum": 21,
    "description": "Giờ hiện tại trong ngày 2026-10-01.",
}
_NOW_MIN = {"type": "integer", "minimum": 0, "maximum": 240, "description": "Phút từ đầu đợt giao (09:00)."}
_STORE_ARGS = {"store_id": _STORE, "sku_ids": _SKUS, "categories": _CATS}
PLAN_NAMES = ["An toàn", "Cân bằng", "Tiết kiệm", "safe", "balanced", "lean"]


def _obj(props: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


def _tool_errors(fn: Callable[[dict, ToolContext], ToolResult]) -> Callable[[dict, ToolContext], ToolResult]:
    @functools.wraps(fn)
    def wrapper(args: dict, ctx: ToolContext) -> ToolResult:
        try:
            return fn(args, ctx)
        except ApiError as exc:
            raise ToolError(exc.message_vi) from None

    return wrapper


class ToolContextHelper:
    def __init__(self, services: Services):
        self.services = services

    def store(self, args: dict[str, Any], ctx: ToolContext) -> str:
        repo = self.services.repo(ctx.chain_id)
        default = ctx.extras.get("default_store_id") or ctx.store_id
        store_id = resolve_store_id(repo, args.get("store_id"), default=default)
        ensure_store_access(str(ctx.extras.get("role", "store_manager")), ctx.store_id, store_id)
        return store_id

    def skus(self, args: dict[str, Any], ctx: ToolContext, *, default_categories: tuple[str, ...] = ()):
        repo = self.services.repo(ctx.chain_id)
        sku_ids, cats = args.get("sku_ids") or [], args.get("categories") or []
        if not sku_ids and not cats and default_categories:
            cats = list(default_categories)
        return repo.select_skus(sku_ids, cats)


def build_registry(services: Services, drafts: SqlDraftStore) -> ToolRegistry:
    h = ToolContextHelper(services)
    reg = ToolRegistry(draft_store=drafts)

    @_tool_errors
    def forecast_fn(args: dict, ctx: ToolContext) -> ToolResult:
        store_id = h.store(args, ctx)
        data = services.forecast(ctx.chain_id, store_id, h.skus(args, ctx), int(args.get("horizon_days", 1)))
        return ToolResult(data, [f"forecast_demand:{ctx.chain_id}/{store_id}", "forecasting.service"])

    @_tool_errors
    def plan_fn(args: dict, ctx: ToolContext) -> ToolResult:
        store_id = h.store(args, ctx)
        data = services.inventory_plan(
            ctx.chain_id,
            store_id,
            h.skus(args, ctx),
            horizon_days=int(args.get("horizon_days", 1)),
            budget_vnd=args.get("budget_vnd"),
            cold_storage_units=args.get("cold_storage_units"),
        )
        return ToolResult(data, [f"plan_inventory:{ctx.chain_id}/{store_id}", "decision.plan_inventory"])

    @_tool_errors
    def markdown_fn(args: dict, ctx: ToolContext) -> ToolResult:
        store_id = h.store(args, ctx)
        data = services.markdown(
            ctx.chain_id, store_id, h.skus(args, ctx), now_hour=int(args.get("now_hour", DEFAULT_NOW_HOUR))
        )
        return ToolResult(data, [f"suggest_markdown:{ctx.chain_id}/{store_id}", "decision.suggest_markdown"])

    @_tool_errors
    def transfer_fn(args: dict, ctx: ToolContext) -> ToolResult:
        store_id = h.store(args, ctx)
        data = services.transfer(
            ctx.chain_id, store_id, h.skus(args, ctx), now_hour=int(args.get("now_hour", DEFAULT_NOW_HOUR))
        )
        return ToolResult(
            data, [f"transfer_stock:{ctx.chain_id}/{store_id}", "decision.transfer_stock", "routing.paco"]
        )

    @_tool_errors
    def routes_fn(args: dict, ctx: ToolContext) -> ToolResult:
        store_id = h.store(args, ctx)
        data = services.routing_plan(ctx.chain_id, store_id, int(args.get("now_minute", 0)))
        return ToolResult(data, [f"optimize_routes:{ctx.chain_id}/{store_id}", "routing.paco"])

    # ------------------------------------------------------------ draft tools

    @_tool_errors
    def purchase_order_fn(args: dict, ctx: ToolContext) -> ToolResult:
        store_id = h.store(args, ctx)
        key = plan_key(args["plan_name"])
        lines_in = args.get("lines") or []
        repo = services.repo(ctx.chain_id)
        if lines_in and not args.get("sku_ids") and not args.get("categories"):
            skus = repo.select_skus([str(line["sku_id"]) for line in lines_in], None)
        else:
            skus = h.skus(args, ctx)
        result = services.inventory_plan(
            ctx.chain_id,
            store_id,
            skus,
            horizon_days=int(args.get("horizon_days", 1)),
            budget_vnd=args.get("budget_vnd"),
            cold_storage_units=args.get("cold_storage_units"),
        )
        options = {}
        for p in result["plans"]:
            priced = services.purchase_order_lines(
                ctx.chain_id,
                [{"sku_id": ln["sku_id"], "qty": ln["qty"]} for ln in p["lines"] if ln["qty"] > 0],
            )
            options[p["name"]] = {
                "label_vi": p["label_vi"],
                "lines": priced,
                "total_cost_vnd": sum(ln["cost_vnd"] for ln in priced),
                "expected_waste_pct": p["expected_waste_pct"],
                "expected_stockout_pct": p["expected_stockout_pct"],
            }
        chosen = options[key]
        lines = services.purchase_order_lines(ctx.chain_id, lines_in) if lines_in else chosen["lines"]
        payload = {
            "store_id": store_id,
            "store_name": result["store_name"],
            "order_date": result["order_date"],
            "plan_name": key,
            "plan_label_vi": chosen["label_vi"],
            "lines": lines,
            "total_cost_vnd": sum(ln["cost_vnd"] for ln in lines),
            "lines_from_user": bool(lines_in),
            "options": options,
            "source": SOURCE,
        }
        _set_po_plan_metrics(payload)
        return ToolResult(payload, [f"plan_inventory:{ctx.chain_id}/{store_id}"])

    @_tool_errors
    def apply_markdown_fn(args: dict, ctx: ToolContext) -> ToolResult:
        store_id = h.store(args, ctx)
        result = services.markdown(
            ctx.chain_id, store_id, h.skus(args, ctx), now_hour=int(args.get("now_hour", DEFAULT_NOW_HOUR))
        )
        items = [
            {
                "sku_id": p["sku_id"],
                "sku_name": p["sku_name"],
                "unit_price": p["unit_price"],
                "units_at_risk": p["units_at_risk"],
                "schedule": [
                    {"start": s["start"], "discount_pct": s["discount_pct"], "price_vnd": s["price_vnd"]}
                    for s in p["schedule"]
                ],
                "expected_units_sold": p["expected_units_sold"],
                "expected_units_wasted": p["expected_units_wasted"],
                "cash_gain_vnd": p["cash_gain_vnd"],
            }
            for p in result["plans"]
            if any(s["discount_pct"] > 0 for s in p["schedule"])
        ]
        if not items:
            raise ToolError("Không có mặt hàng nào cần giảm giá theo tính toán, nên không tạo bản nháp.")
        payload = {
            "store_id": store_id,
            "store_name": result["store_name"],
            "now": result["now"],
            "items": items,
            "cash_gain_total_vnd": sum(i["cash_gain_vnd"] for i in items),
            "source": SOURCE,
        }
        return ToolResult(payload, [f"suggest_markdown:{ctx.chain_id}/{store_id}"])

    @_tool_errors
    def transfer_draft_fn(args: dict, ctx: ToolContext) -> ToolResult:
        store_id = h.store(args, ctx)
        result = services.transfer(
            ctx.chain_id, store_id, h.skus(args, ctx), now_hour=int(args.get("now_hour", DEFAULT_NOW_HOUR))
        )
        t = result["transfer"]
        if not t["lines"] or not t["routed"]:
            raise ToolError(f"Không tạo phiếu điều chuyển: {t['rationale_vi']}")
        payload = {
            "store_id": store_id,
            "store_name": result["store_name"],
            "lines": t["lines"],
            "units_moved": t["units_moved"],
            "destinations": t["destinations"],
            "km": t["km"],
            "vehicles": t["vehicles"],
            "trip_cost_vnd": t["trip_cost_vnd"],
            "saved_value_vnd": t["saved_value_vnd"],
            "saved_cash_vnd": t["saved_cash_vnd"],
            "stockout_avoided_value_vnd": t["stockout_avoided_value_vnd"],
            "net_saving_vnd": t["net_saving_vnd"],
            "recommended": t["recommended"],
            "rationale_vi": t["rationale_vi"],
            "source": SOURCE,
        }
        return ToolResult(payload, [f"transfer_stock:{ctx.chain_id}/{store_id}"])

    @_tool_errors
    def dispatch_fn(args: dict, ctx: ToolContext) -> ToolResult:
        store_id = h.store(args, ctx)
        plan = services.routing_plan(ctx.chain_id, store_id, int(args.get("now_minute", 0)))
        wanted = args.get("route_plan_id")
        if wanted and wanted not in (plan["route_plan_id"], plan["batch_hash"]):
            raise ToolError("Lộ trình đã thay đổi so với mã được nêu; hãy tính lại lộ trình trước khi gửi.")
        if not plan["routes"]:
            raise ToolError("Không có đơn nào giao được trong đợt này nên không tạo bản nháp gửi lộ trình.")
        payload = {
            "store_id": store_id,
            "route_plan_id": plan["route_plan_id"],
            "batch_hash": plan["batch_hash"],
            "batch_start": plan["batch"]["batch_start"],
            "km": plan["km"],
            "vehicles": plan["vehicles"],
            "baseline_km": plan["baseline_km"],
            "saving_pct": plan["saving_pct"],
            "orders_routed": plan["orders_routed"],
            "routes": [
                {
                    "vehicle_label": r["vehicle_label"],
                    "stops": [
                        {
                            "order_id": s["order_id"],
                            "kind": s["kind"],
                            "pickup_point_id": s["pickup_point_id"],
                            "eta_min": s["eta_min"],
                        }
                        for s in r["stops"]
                    ],
                }
                for r in plan["routes"]
            ],
            "at_risk": [{"order_id": a["order_id"], "reason_vi": a["reason_vi"]} for a in plan["at_risk"]],
            "source": SOURCE,
        }
        return ToolResult(payload, [f"optimize_routes:{ctx.chain_id}/{store_id}"])

    line = _obj(
        {"sku_id": {"type": "string", "minLength": 1}, "qty": {"type": "integer", "minimum": 0}},
        ("sku_id", "qty"),
    )
    tools = [
        Tool(
            "forecast_demand",
            "Dự báo nhu cầu P10/P50/P90 theo cửa hàng và mặt hàng, kèm độ tin cậy.",
            _obj({**_STORE_ARGS, "horizon_days": _HORIZON}),
            "read",
            forecast_fn,
        ),
        Tool(
            "plan_inventory",
            "Lập 3 phương án nhập hàng (An toàn / Cân bằng / Tiết kiệm) từ dự báo và tồn kho.",
            _obj(
                {
                    **_STORE_ARGS,
                    "horizon_days": _HORIZON,
                    "budget_vnd": {"type": "number", "minimum": 0},
                    "cold_storage_units": {"type": "number", "minimum": 0},
                }
            ),
            "read",
            plan_fn,
        ),
        Tool(
            "suggest_markdown",
            "Đề xuất giảm giá theo khung giờ cho hàng tươi hết hạn hôm nay.",
            _obj({**_STORE_ARGS, "now_hour": _NOW_HOUR}),
            "read",
            markdown_fn,
        ),
        Tool(
            "transfer_stock",
            "Tính điều chuyển hàng dư sang cửa hàng thiếu (PACO) và so sánh bằng tiền với giảm giá.",
            _obj({**_STORE_ARGS, "now_hour": _NOW_HOUR}),
            "read",
            transfer_fn,
        ),
        Tool(
            "optimize_routes",
            "Gom đơn online của đợt hiện tại và tính lộ trình giao (PACO), kèm đơn có nguy cơ trễ.",
            _obj({"store_id": _STORE, "now_minute": _NOW_MIN}),
            "read",
            routes_fn,
        ),
        make_query_data_tool(
            lambda chain: chain_db_path(services.data_dir, chain),
            schema_hint_vi="Cột chính: v_sales_daily(store_id, sku_id, sku_name, category, date, "
            "units, revenue); "
            "v_stock(store_id, sku_id, qty, expires_on, days_to_expiry); v_stores; v_skus; v_online_orders.",
        ),
        make_render_chart_tool(),
        Tool(
            "create_purchase_order",
            "Tạo bản nháp đơn đặt hàng theo một phương án nhập (người dùng phải duyệt).",
            _obj(
                {
                    **_STORE_ARGS,
                    "plan_name": {"type": "string", "enum": PLAN_NAMES},
                    "lines": {"type": "array", "items": line, "maxItems": 50},
                    "horizon_days": _HORIZON,
                    "budget_vnd": {"type": "number", "minimum": 0},
                    "cold_storage_units": {"type": "number", "minimum": 0},
                },
                ("plan_name",),
            ),
            "draft",
            purchase_order_fn,
        ),
        Tool(
            "apply_markdown",
            "Tạo bản nháp lịch giảm giá theo khung giờ (người dùng phải duyệt).",
            _obj({**_STORE_ARGS, "now_hour": _NOW_HOUR}),
            "draft",
            apply_markdown_fn,
        ),
        Tool(
            "create_transfer",
            "Tạo bản nháp phiếu điều chuyển hàng dư sang cửa hàng thiếu (người dùng phải duyệt).",
            _obj({**_STORE_ARGS, "now_hour": _NOW_HOUR}),
            "draft",
            transfer_draft_fn,
        ),
        Tool(
            "dispatch_routes",
            "Tạo bản nháp gửi lộ trình đợt giao hiện tại cho shipper (người dùng phải duyệt).",
            _obj(
                {
                    "store_id": _STORE,
                    "route_plan_id": {"type": "string", "maxLength": 64},
                    "now_minute": _NOW_MIN,
                }
            ),
            "draft",
            dispatch_fn,
        ),
    ]
    for tool in tools:
        reg.register(tool)
    return reg


# ---------------------------------------------------------------- draft edits (PATCH /api/drafts/{id})


def make_edit_applier(services: Services, chain_id: str) -> Callable[[dict, dict], dict]:
    """Return ``apply(draft, changes) -> new payload``; money is always re-priced from the DB."""

    def apply(draft: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
        payload = dict(draft["payload"])
        kind = draft["kind"]
        if "note" in changes:
            note = changes["note"]
            if not isinstance(note, str) or len(note) > 500:
                raise ApiError(422, "bad_note", "Ghi chú phải là chuỗi tối đa 500 ký tự.")
            payload["note"] = note
        if kind == "create_purchase_order":
            if "selected_plan" in changes:
                key = plan_key(str(changes["selected_plan"]))
                opt = payload.get("options", {}).get(key)
                if opt is None:
                    raise ApiError(422, "bad_plan_name", "Bản nháp không có phương án này.")
                payload.update(
                    plan_name=key, plan_label_vi=opt["label_vi"], lines=opt["lines"], lines_from_user=False
                )
            if "lines" in changes:
                if not isinstance(changes["lines"], list) or not all(
                    isinstance(x, dict) for x in changes["lines"]
                ):
                    raise ApiError(422, "bad_lines", "Danh sách dòng hàng không hợp lệ.")
                payload["lines"] = services.purchase_order_lines(chain_id, changes["lines"])
                payload["lines_from_user"] = True
            payload["total_cost_vnd"] = sum(ln["cost_vnd"] for ln in payload["lines"])
            _set_po_plan_metrics(payload)
        elif kind == "apply_markdown" and "items" in changes:
            payload["items"] = _edit_markdown_items(payload.get("items", []), changes["items"])
            gains = [i.get("cash_gain_vnd") for i in payload["items"]]
            if all(isinstance(g, int | float) for g in gains):
                payload["cash_gain_total_vnd"] = sum(gains)
                payload.pop("cash_gain_note_vi", None)
            else:
                payload["cash_gain_total_vnd"] = None
                payload["cash_gain_note_vi"] = (
                    "Lịch giảm giá đã được sửa tay: lợi ích tiền mặt dự kiến chưa tính lại cho lịch mới."
                )
        elif kind == "create_transfer" and "lines" in changes:
            payload["lines"] = _edit_transfer_lines(payload.get("lines", []), changes["lines"])
            _recompute_transfer_totals(payload, draft["payload"])
        return payload

    return apply


PLAN_METRICS_NOTE_VI = (
    "Số lượng đã sửa khác phương án {label}: % hàng bỏ và % hết hàng dự kiến chưa tính lại cho số lượng mới."
)


def _set_po_plan_metrics(payload: dict[str, Any]) -> None:
    """Show the selected plan's waste/stockout % only when the order lines are that plan's lines."""
    opt = payload.get("options", {}).get(payload.get("plan_name"), {})

    def qty_map(lines: list[dict]) -> dict[str, int]:
        return {ln["sku_id"]: ln["qty"] for ln in lines if ln.get("qty", 0) > 0}

    if opt and qty_map(payload.get("lines", [])) == qty_map(opt.get("lines", [])):
        payload["expected_waste_pct"] = opt["expected_waste_pct"]
        payload["expected_stockout_pct"] = opt["expected_stockout_pct"]
        payload.pop("plan_metrics_note_vi", None)
    else:
        payload["expected_waste_pct"] = None
        payload["expected_stockout_pct"] = None
        payload["plan_metrics_note_vi"] = PLAN_METRICS_NOTE_VI.format(label=payload.get("plan_label_vi", ""))


def _recompute_transfer_totals(payload: dict[str, Any], before: dict[str, Any]) -> None:
    """Totals follow the edited lines. The route (km, vehicles, trip cost) is not re-solved: it is kept as
    an upper bound and flagged when the set of destinations changed."""
    lines = payload["lines"]
    dests = {ln["to_store_id"] for ln in lines}
    payload["units_moved"] = sum(ln["qty"] for ln in lines)
    payload["destinations"] = len(dests)
    payload["saved_value_vnd"] = sum(ln["value_vnd"] for ln in lines)
    if all("cash_value_vnd" in ln for ln in lines):
        payload["saved_cash_vnd"] = sum(ln["cash_value_vnd"] for ln in lines)
        payload["stockout_avoided_value_vnd"] = sum(ln["stockout_value_vnd"] for ln in lines)
    trip = payload.get("trip_cost_vnd") or 0
    payload["net_saving_vnd"] = payload["saved_value_vnd"] - trip
    payload["recommended"] = bool(lines) and payload["net_saving_vnd"] > 0
    if dests != {ln["to_store_id"] for ln in before.get("lines", [])}:
        payload["stale_route_note_vi"] = (
            f"Quãng đường {units(payload.get('km') or 0)} km, số xe và chi phí chuyến {vnd(trip)} lấy từ "
            "lộ trình tính trước khi sửa (gồm cả cửa hàng nhận đã bỏ); lộ trình chưa tính lại nên lợi ròng "
            "thực tế có thể cao hơn."
        )  # sticky: destinations can only be dropped, never restored, so the route stays stale
    payload["rationale_vi"] = (
        f"Đã sửa số lượng: điều chuyển {payload['units_moved']} đơn vị sang {payload['destinations']} "
        f"cửa hàng, giá trị cứu được {vnd(payload['saved_value_vnd'])}, chi phí chuyến {vnd(trip)}, "
        f"lợi ròng {vnd(payload['net_saving_vnd'])}."
    )


def _edit_markdown_items(items: list[dict], changes: Any) -> list[dict]:
    if not isinstance(changes, list):
        raise ApiError(422, "bad_items", "Danh sách mặt hàng giảm giá không hợp lệ.")
    allowed = {0, 10, 20, 30, 50}
    by_sku = {i["sku_id"]: dict(i) for i in items}
    for ch in changes:
        if not isinstance(ch, dict) or ch.get("sku_id") not in by_sku:
            raise ApiError(422, "bad_items", "Mặt hàng không có trong bản nháp.")
        item = by_sku[ch["sku_id"]]
        new = ch.get("schedule")
        if not isinstance(new, list) or len(new) != len(item["schedule"]):
            raise ApiError(422, "bad_schedule", "Lịch giảm giá phải giữ đủ các khung giờ.")
        discounts = [s.get("discount_pct") if isinstance(s, dict) else None for s in new]
        if any(d not in allowed for d in discounts) or discounts != sorted(discounts):
            raise ApiError(
                422,
                "bad_schedule",
                "Mức giảm phải thuộc {0, 10, 20, 30, 50}% và chỉ tăng dần theo khung giờ "
                "(giá không được tăng lại trong ngày).",
            )
        item["schedule"] = [
            {"start": old["start"], "discount_pct": d, "price_vnd": round(item["unit_price"] * (1 - d / 100))}
            for old, d in zip(item["schedule"], discounts, strict=True)
        ]
        for k in ("expected_units_sold", "expected_units_wasted", "cash_gain_vnd"):
            item.pop(k, None)
        item["edited"] = True
    return list(by_sku.values())


def _edit_transfer_lines(lines: list[dict], changes: Any) -> list[dict]:
    if not isinstance(changes, list):
        raise ApiError(422, "bad_lines", "Danh sách dòng điều chuyển không hợp lệ.")
    index = {(ln["to_store_id"], ln["sku_id"]): dict(ln) for ln in lines}
    for ch in changes:
        key = (ch.get("to_store_id"), ch.get("sku_id")) if isinstance(ch, dict) else None
        if key not in index:
            raise ApiError(422, "bad_lines", "Dòng điều chuyển không có trong bản nháp.")
        qty = ch.get("qty")
        if not isinstance(qty, int) or isinstance(qty, bool) or not 0 <= qty <= index[key]["qty"]:
            raise ApiError(422, "bad_qty", "Số lượng điều chuyển chỉ được giảm, không vượt số đã tính.")
        old = index[key]
        for field in ("value_vnd", "cash_value_vnd", "stockout_value_vnd"):
            if field in old:
                old[field] = round(old[field] * qty / old["qty"]) if old["qty"] else 0
        old["qty"] = qty
    return [ln for ln in index.values() if ln["qty"] > 0]
