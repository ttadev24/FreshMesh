"""Service layer shared by the API endpoints, the agent tools and ``decision.cli``.

Every function reads the caller's chain DB only (tenant = ``chain_id`` from the token), calls the real
modules (``forecasting``, ``decision``, ``routing``) and returns JSON-ready dicts labelled
``source = "SIMULATED"``. Store access rules are checked by the callers (API / tools).

Decision parameters (docs/data-assumptions.md):
* stockout penalty per SKU = ``stockout_penalty_ratio`` × unit margin. ``plan_inventory`` and
  ``transfer_stock`` take one scalar penalty, but ``unit_price`` enters them only through
  ``price − cost + penalty`` (inventory) and ``price − salvage + penalty`` (transfer), so the per-SKU
  penalty is folded exactly into an *effective price* on a copy of the SKU economics for those two calls.
  Markdown uses the real price (it is revenue there).
* "now" for markdown/transfer is ``2026-10-01 <now_hour>:00`` (first forecast day). Stock in the DB is the
  start-of-day stock, so the expected sales before ``now`` (P50 × hourly share of the hours already passed)
  are deducted FIFO from the lots expiring today; the deducted figure is part of the output. Transfer uses
  the same basis: every store's stock at ``now`` (FIFO deduction), rest-of-day demand (quantiles × share of
  the remaining hours) and, at the origin, only today's expiring lots (the units markdown works on).
* The markdown-vs-transfer comparison is cash only: the stockout penalty inside a transfer line's value is
  split out (``stockout_value_vnd``) and reported, never compared.
"""

from __future__ import annotations

import datetime as dt
import importlib
import inspect
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api.config import REPO_ROOT
from api.errors import ApiError
from api.repo import ChainRepo, SkuInfo, StoreInfo
from api.routing_service import RoutingService
from data_sim import ASSUMPTION_DESCRIPTIONS_VI, ASSUMPTIONS, SIM_AS_OF, SOURCE, assumptions_sections
from decision import (
    Constraints,
    ForecastQuantiles,
    StockLot,
    compare_markdown_vs_transfer,
    plan_inventory,
    suggest_markdown,
    transfer_stock,
)
from decision.text import pct, units, vnd
from decision.types import MarkdownPlan
from forecasting.service import (
    ModelNotReadyError,
    drift_status,
    forecast_demand,
    resolve_model_kind,
)
from routing.models import Store

log = logging.getLogger(__name__)
MAX_LINE_QTY = 5_000  # per PO line; guards against absurd quantities (and float overflow)
MAX_PO_LINES = 100
FIRST_DAY = SIM_AS_OF + dt.timedelta(days=1)
DEFAULT_NOW_HOUR = 14  # flow 2 "Chiều, xử lý tồn"
# Store-to-store transfer fleet (passed explicitly to transfer_stock and stated in assumptions_vi).
TRANSFER_VEHICLES = 2
TRANSFER_VEHICLE_CAPACITY = 200
TRANSFER_SERVICE_MIN = 10
TRANSFER_WINDOW_MIN = 240
CONFIDENCE_ORDER = {"Thấp": 0, "Trung bình": 1, "Cao": 2}
PLAN_KEYS = {
    "safe": "safe",
    "balanced": "balanced",
    "lean": "lean",
    "An toàn": "safe",
    "Cân bằng": "balanced",
    "Tiết kiệm": "lean",
}
MARKDOWN_ASSUMPTIONS_VI = (
    "Dữ liệu giả lập (SIMULATED).",
    "Hệ số co giãn giá theo nhóm hàng là giả định (docs/data-assumptions.md), "
    "chưa ước lượng từ dữ liệu thật.",
    "Tồn hiện tại = tồn đầu ngày trừ lượng bán kỳ vọng (P50 × tỷ trọng các giờ đã qua), "
    "bán lô sắp hết hạn trước.",
    "Nhu cầu mỗi giờ theo phân bố Poisson; giá chỉ giảm dần trong ngày.",
)
FL_NOT_READY_VI = (
    "Chưa có kết quả học liên kết (FL) trên máy chủ này; hãy chạy huấn luyện và thí nghiệm FL "
    "(scripts/bootstrap.sh) rồi thử lại."
)
MODEL_NOT_READY_VI = (
    "Chưa có mô hình dự báo cho chuỗi này trên máy chủ; hãy chạy scripts/bootstrap.sh (huấn luyện mô hình) "
    "rồi thử lại."
)


def _model_not_ready() -> ApiError:
    return ApiError(503, "model_not_ready", MODEL_NOT_READY_VI)


@dataclass(frozen=True)
class Services:
    data_dir: Path
    routing: RoutingService
    # The API never trains inside a request (missing model → 503 model_not_ready); the CLI may.
    auto_train: bool = False

    def repo(self, chain_id: str) -> ChainRepo:
        return ChainRepo(self.data_dir, chain_id)

    # ------------------------------------------------------------ forecast

    def _forecast_rows(
        self, chain_id: str, store_ids: Sequence[str], skus: Sequence[SkuInfo], horizon_days: int
    ) -> list[Any]:
        if not 1 <= horizon_days <= 7:
            raise ApiError(422, "bad_horizon", "Số ngày dự báo phải từ 1 đến 7.")
        try:
            return forecast_demand(
                chain_id,
                list(store_ids),
                [s.sku_id for s in skus],
                horizon_days,
                data_dir=self.data_dir,
                auto_train=self.auto_train,
            )
        except ModelNotReadyError:
            raise _model_not_ready() from None
        except FileNotFoundError:
            raise ApiError(
                503, "data_not_ready", "Chưa có dữ liệu hoặc mô hình dự báo; hãy chạy bootstrap."
            ) from None
        except ValueError:
            log.warning("forecast request rejected", exc_info=True)
            raise ApiError(
                422,
                "bad_forecast_request",
                "Không dự báo được cho cửa hàng/mặt hàng đã chọn (mã không có trong dữ liệu hoặc "
                "tham số không hợp lệ).",
            ) from None

    @staticmethod
    def _row_dict(r: Any, names: dict[str, str]) -> dict[str, Any]:
        return {
            "store_id": r.store_id,
            "sku_id": r.sku_id,
            "sku_name": names.get(r.sku_id, r.sku_id),
            "date": r.date.isoformat(),
            "p10": r.p10,
            "p50": r.p50,
            "p90": r.p90,
            "confidence": r.confidence,
            "reason": r.reason,
            "source": SOURCE,
        }

    def _drift(self, chain_id: str, store_id: str) -> dict[str, Any]:
        try:
            d = drift_status(chain_id, store_id, data_dir=self.data_dir, auto_train=self.auto_train)
        except ModelNotReadyError:
            raise _model_not_ready() from None
        return {
            "chain_id": d.chain_id,
            "store_id": d.store_id,
            "coverage_7d": None if d.coverage_7d is None else round(d.coverage_7d, 3),
            "coverage_7d_pct": None if d.coverage_7d is None else round(100 * d.coverage_7d, 1),
            "n_points": d.n_points,
            "alert": d.alert,
            "message_vi": d.message_vi,
            "source": SOURCE,
        }

    def forecast(self, chain_id: str, store_id: str, skus: Sequence[SkuInfo], horizon_days: int = 1) -> dict:
        repo = self.repo(chain_id)
        store = repo.store(store_id)
        names = {s.sku_id: s.name for s in skus}
        rows = self._forecast_rows(chain_id, [store_id], skus, horizon_days)
        return {
            "store_id": store_id,
            "store_name": store.name,
            "as_of": SIM_AS_OF.isoformat(),
            "horizon_days": horizon_days,
            "rows": [self._row_dict(r, names) for r in rows],
            "drift": self._drift(chain_id, store_id),
            "source": SOURCE,
        }

    # ------------------------------------------------------------ inventory (flow 1)

    @staticmethod
    def _penalty(sku: SkuInfo) -> float:
        return float(ASSUMPTIONS["stockout_penalty_ratio"]) * (sku.unit_price - sku.unit_cost)

    def inventory_plan(
        self,
        chain_id: str,
        store_id: str,
        skus: Sequence[SkuInfo],
        *,
        horizon_days: int = 1,
        budget_vnd: float | None = None,
        cold_storage_units: float | None = None,
    ) -> dict:
        repo = self.repo(chain_id)
        store = repo.store(store_id)
        if not skus:
            raise ApiError(422, "no_skus", "Cần chọn ít nhất một mặt hàng.")
        names = {s.sku_id: s.name for s in skus}
        rows = self._forecast_rows(chain_id, [store_id], skus, horizon_days)
        drift = self._drift(chain_id, store_id)
        stock = repo.stock([store_id], [s.sku_id for s in skus])
        economics = {s.sku_id: s.economics(price=s.unit_price + self._penalty(s)) for s in skus}
        try:
            plans = plan_inventory(
                [ForecastQuantiles(r.store_id, r.sku_id, r.date, r.p10, r.p50, r.p90) for r in rows],
                stock,
                economics,
                Constraints(budget_vnd=budget_vnd, cold_storage_capacity=cold_storage_units),
                horizon_days=horizon_days,
            )
        except ValueError:
            log.warning("inventory plan request rejected", exc_info=True)
            raise ApiError(
                422,
                "bad_plan_request",
                "Không lập được phương án nhập: dữ liệu mặt hàng hoặc ràng buộc (ngân sách, kho lạnh) "
                "không hợp lệ.",
            ) from None
        plan_dicts = []
        for p in plans:
            d = p.to_dict()
            for line in d["lines"]:
                line["sku_name"] = names[line["sku_id"]]
            plan_dicts.append(d)
        worst = min(rows, key=lambda r: (CONFIDENCE_ORDER.get(r.confidence, 1), r.sku_id))
        recommended = "safe" if drift["alert"] else "balanced"
        rec_plan = next(p for p in plan_dicts if p["name"] == recommended)
        rec_reason = (
            "Độ phủ dự báo 7 ngày gần nhất thấp nên chọn phương án An toàn."
            if drift["alert"]
            else "Phương án Cân bằng có chi phí kỳ vọng (hàng bỏ + hết hàng) thấp nhất."
        )
        stock_by_sku: dict[str, int] = {}
        for lot in stock:
            if lot.expires_on >= FIRST_DAY:
                stock_by_sku[lot.sku_id] = stock_by_sku.get(lot.sku_id, 0) + lot.qty
        penalty_note = (
            f"Phạt mất khách khi hết hàng = {str(ASSUMPTIONS['stockout_penalty_ratio']).replace('.', ',')} × "
            "biên lợi nhuận đơn vị của từng mặt hàng."
        )
        return {
            "store_id": store_id,
            "store_name": store.name,
            "order_date": FIRST_DAY.isoformat(),
            "horizon_days": horizon_days,
            "plans": plan_dicts,
            "recommended_plan": recommended,
            "recommended_label_vi": rec_plan["label_vi"],
            "recommended_reason_vi": rec_reason,
            "confidence": worst.confidence,
            "confidence_reason": worst.reason,
            "confidence_sku_id": worst.sku_id,
            "forecast": [self._row_dict(r, names) for r in rows],
            "drift": drift,
            "stock_on_hand": [
                {"sku_id": k, "sku_name": names[k], "units": v} for k, v in sorted(stock_by_sku.items())
            ],
            "stockout_penalty_ratio": ASSUMPTIONS["stockout_penalty_ratio"],
            "constraints": {"budget_vnd": budget_vnd, "cold_storage_units": cold_storage_units},
            "assumptions_vi": [*plans[0].assumptions_vi, penalty_note],
            "source": SOURCE,
        }

    def purchase_order_lines(self, chain_id: str, lines: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Price PO lines from the DB (never trust client-supplied money)."""
        skus = self.repo(chain_id).sku_map()
        out = []
        if len(lines) > MAX_PO_LINES:
            raise ApiError(422, "too_many_lines", f"Một đơn nhập tối đa {MAX_PO_LINES} dòng hàng.")
        for line in lines:
            sku_id = str(line.get("sku_id", ""))
            if sku_id not in skus:
                raise ApiError(404, "unknown_sku", f"Mặt hàng '{sku_id}' không tồn tại.")
            qty = line.get("qty")
            if not isinstance(qty, int) or isinstance(qty, bool) or qty < 0:
                raise ApiError(422, "bad_qty", f"Số lượng của {sku_id} phải là số nguyên ≥ 0.")
            sku = skus[sku_id]
            if qty > MAX_LINE_QTY:
                raise ApiError(422, "bad_qty", f"Số lượng của {sku_id} vượt giới hạn {MAX_LINE_QTY} đơn vị.")
            if qty % sku.moq:
                raise ApiError(
                    422, "bad_moq", f"Số lượng {sku.name} phải là bội số của MOQ {sku.moq} (nhà cung cấp)."
                )
            out.append(
                {
                    "sku_id": sku_id,
                    "sku_name": sku.name,
                    "qty": qty,
                    "unit_cost": sku.unit_cost,
                    "cost_vnd": round(qty * sku.unit_cost),
                    "supplier_id": sku.supplier_id,
                }
            )
        return out

    # ------------------------------------------------------------ markdown + transfer (flow 2)

    def _now(self, now_hour: int) -> dt.datetime:
        if not 6 <= now_hour <= 21:
            raise ApiError(422, "bad_hour", "Giờ hiện tại phải trong khung 6h–21h.")
        return dt.datetime.combine(FIRST_DAY, dt.time(now_hour))

    def _markdown_core(
        self, chain_id: str, store_id: str, skus: Sequence[SkuInfo], now_hour: int
    ) -> tuple[
        StoreInfo, dt.datetime, list[tuple[SkuInfo, MarkdownPlan, dict[str, Any]]], list[dict[str, Any]]
    ]:
        repo = self.repo(chain_id)
        store = repo.store(store_id)
        now = self._now(now_hour)
        fresh = [s for s in skus if s.is_fresh]
        shares = {int(h): float(v) for h, v in ASSUMPTIONS["hourly_sales_share"][store.area_type].items()}
        rows = {r.sku_id: r for r in self._forecast_rows(chain_id, [store_id], fresh, 1)} if fresh else {}
        stock = repo.stock([store_id], [s.sku_id for s in fresh])
        share_before = self._share_before(store.area_type, now_hour)
        out, skipped = [], []
        for sku in fresh:
            expiring = sum(
                lot.qty for lot in stock if lot.sku_id == sku.sku_id and lot.expires_on == FIRST_DAY
            )
            p50 = rows[sku.sku_id].p50
            sold_before = round(p50 * share_before, 1)
            remaining = max(0, round(expiring - sold_before))
            if remaining <= 0:
                skipped.append({"sku_id": sku.sku_id, "sku_name": sku.name, "start_of_day_units": expiring})
                continue
            hourly = {
                dt.datetime.combine(FIRST_DAY, dt.time(h)): p50 * v
                for h, v in sorted(shares.items())
                if h >= now_hour
            }
            elasticity = float(ASSUMPTIONS["markdown_elasticity"][sku.category])
            plan = suggest_markdown(
                [StockLot(store_id, sku.sku_id, remaining, FIRST_DAY)],
                hourly,
                sku.economics(),
                elasticity,
                now=now,
            )
            extra = {
                "sku_name": sku.name,
                "start_of_day_units": expiring,
                "expected_sold_before_now": sold_before,
                "forecast_p50_day": p50,
                "unit_price": sku.unit_price,
                "forecast_confidence": rows[sku.sku_id].confidence,
                "forecast_confidence_reason": rows[sku.sku_id].reason,
            }
            out.append((sku, plan, extra))
        out.sort(key=lambda t: (-t[1].units_at_risk, t[0].sku_id))
        return store, now, out, skipped

    def markdown(
        self, chain_id: str, store_id: str, skus: Sequence[SkuInfo], *, now_hour: int = DEFAULT_NOW_HOUR
    ) -> dict:
        store, now, core, skipped = self._markdown_core(chain_id, store_id, skus, now_hour)
        return self._markdown_dict(store, now, core, skipped)

    @staticmethod
    def _markdown_dict(
        store: StoreInfo,
        now: dt.datetime,
        core: list[tuple[SkuInfo, MarkdownPlan, dict]],
        skipped: list[dict],
    ) -> dict:
        plans = [{**plan.to_dict(), **extra} for _, plan, extra in core]
        worst = min(
            plans,
            key=lambda p: (CONFIDENCE_ORDER.get(p["forecast_confidence"], 1), p["sku_id"]),
            default=None,
        )
        return {
            "confidence": worst["forecast_confidence"] if worst else None,
            "confidence_reason": (
                f"{worst['sku_name']}: {worst['forecast_confidence_reason']}" if worst else None
            ),
            "store_id": store.store_id,
            "store_name": store.name,
            "now": now.isoformat(),
            "now_hour": now.hour,
            "plans": plans,
            "skipped": skipped,
            "units_at_risk_total": sum(p["units_at_risk"] for p in plans),
            "cash_gain_total_vnd": sum(p["cash_gain_vnd"] for p in plans),
            "discount_levels_pct": [round(100 * x) for x in ASSUMPTIONS["markdown_discount_levels"]],
            "assumptions_vi": list(MARKDOWN_ASSUMPTIONS_VI),
            "source": SOURCE,
        }

    @staticmethod
    def _share_before(area_type: str, now_hour: int) -> float:
        shares = ASSUMPTIONS["hourly_sales_share"][area_type]
        return sum(float(v) for h, v in shares.items() if int(h) < now_hour)

    @staticmethod
    def _stock_at_now(
        lots: Sequence[StockLot], sold_before: dict[tuple[str, str], float], origin: str
    ) -> list[StockLot]:
        """Stock at ``now``: start-of-day lots minus the expected sales before ``now``, FIFO by expiry
        (as in markdown). The origin keeps only the lots expiring today, i.e. exactly the units markdown
        works on, so both options are compared on the same units."""
        by_key: dict[tuple[str, str], list[StockLot]] = {}
        for lot in lots:
            if lot.expires_on >= FIRST_DAY and lot.qty > 0:
                by_key.setdefault((lot.store_id, lot.sku_id), []).append(lot)
        out: list[StockLot] = []
        for key, group in sorted(by_key.items()):
            left = sold_before.get(key, 0.0)
            for lot in sorted(group, key=lambda x: x.expires_on):
                take = min(float(lot.qty), left)
                left -= take
                qty = round(lot.qty - take)
                if qty > 0 and (key[0] != origin or lot.expires_on == FIRST_DAY):
                    out.append(StockLot(lot.store_id, lot.sku_id, qty, lot.expires_on))
        return out

    def transfer(
        self, chain_id: str, store_id: str, skus: Sequence[SkuInfo], *, now_hour: int = DEFAULT_NOW_HOUR
    ) -> dict:
        repo = self.repo(chain_id)
        store = repo.store(store_id)
        stores = repo.stores()
        fresh = [s for s in skus if s.is_fresh]
        if not fresh:
            raise ApiError(422, "no_fresh_skus", "Điều chuyển chỉ áp dụng cho hàng tươi.")
        _, now, core, skipped = self._markdown_core(chain_id, store_id, fresh, now_hour)
        md = self._markdown_dict(store, now, core, skipped)
        rows = self._forecast_rows(chain_id, [s.store_id for s in stores], fresh, 1)
        # Same time basis as markdown: stock left at `now` and demand of the rest of the day.
        before = {s.store_id: self._share_before(s.area_type, now_hour) for s in stores}
        sold_before = {(r.store_id, r.sku_id): round(r.p50 * before[r.store_id], 1) for r in rows}
        stock = self._stock_at_now(repo.stock(None, [s.sku_id for s in fresh]), sold_before, store_id)
        forecasts = [
            ForecastQuantiles(
                r.store_id, r.sku_id, r.date, *(q * (1 - before[r.store_id]) for q in (r.p10, r.p50, r.p90))
            )
            for r in rows
        ]
        economics = {s.sku_id: s.economics(price=s.unit_price + self._penalty(s)) for s in fresh}
        try:
            plan = transfer_stock(
                forecasts,
                stock,
                {s.store_id: Store(s.store_id, s.lat, s.lng) for s in stores},
                economics,
                router=self.routing.router,
                now=now,
                from_store_id=store_id,
                cost_per_km_vnd=float(ASSUMPTIONS["transfer_cost_per_km_vnd"]),
                fixed_trip_cost_vnd=float(ASSUMPTIONS["transfer_fixed_cost_vnd"]),
                vehicle_capacity=TRANSFER_VEHICLE_CAPACITY,
                num_vehicles=TRANSFER_VEHICLES,
                window_minutes=TRANSFER_WINDOW_MIN,
                service_minutes=TRANSFER_SERVICE_MIN,
                detour_factor=float(ASSUMPTIONS["detour_factor"]),
            )
        except ValueError:
            log.warning("transfer request rejected", exc_info=True)
            raise ApiError(
                422,
                "bad_transfer_request",
                "Không tính được điều chuyển: thiếu dự báo hoặc dữ liệu cửa hàng không hợp lệ.",
            ) from None
        tdict = plan.to_dict()
        by_sku = {s.sku_id: s for s in fresh}
        store_names = {s.store_id: s.name for s in stores}
        for line in tdict["lines"]:
            line["sku_name"] = by_sku[line["sku_id"]].name
            line["to_store_name"] = store_names.get(line["to_store_id"], line["to_store_id"])
            # value_vnd = (price − salvage + stockout penalty) × qty; split the non-cash penalty out.
            line["stockout_value_vnd"] = round(self._penalty(by_sku[line["sku_id"]]) * line["qty"])
            line["cash_value_vnd"] = line["value_vnd"] - line["stockout_value_vnd"]
        tdict["saved_cash_vnd"] = sum(ln["cash_value_vnd"] for ln in tdict["lines"])
        tdict["stockout_avoided_value_vnd"] = sum(ln["stockout_value_vnd"] for ln in tdict["lines"])
        if tdict["lines"]:
            tdict["rationale_vi"] += (
                f" Giá trị cứu được gồm {vnd(tdict['saved_cash_vnd'])} tiền mặt và "
                f"{vnd(tdict['stockout_avoided_value_vnd'])} giá trị tránh thiếu hàng (không phải tiền mặt)."
            )
        comparisons = []
        for sku, mplan, _ in core:
            c = compare_markdown_vs_transfer(
                mplan, plan, non_cash_value_per_unit=self._penalty(sku), sku_name=sku.name
            ).to_dict()
            c["sku_name"] = sku.name
            comparisons.append(c)
        md_total = sum(c["markdown_gain_vnd"] for c in comparisons)
        tr_total = sum(c["transfer_gain_vnd"] for c in comparisons)
        so_total = sum(c["transfer_stockout_value_vnd"] for c in comparisons)
        if max(md_total, tr_total) <= 0:
            recommended, text = "none", "Cả giảm giá và điều chuyển đều không mang lại thêm tiền."
        elif tr_total > md_total:
            recommended = "transfer"
            text = (
                f"Nên điều chuyển: lợi thêm {vnd(tr_total)} tiền mặt, "
                f"hơn giảm giá {vnd(tr_total - md_total)}."
            )
        else:
            recommended = "markdown"
            text = (
                f"Nên giảm giá theo khung giờ: lợi thêm {vnd(md_total)}, "
                f"hơn điều chuyển {vnd(md_total - tr_total)} tiền mặt."
            )
        if so_total:
            text += (
                f" Điều chuyển còn tránh thiếu hàng ở cửa hàng nhận (giá trị ước tính {vnd(so_total)}, "
                "không phải tiền mặt nên không tính vào so sánh)."
            )
        return {
            "store_id": store_id,
            "store_name": store.name,
            "now": now.isoformat(),
            "markdown": md["plans"],
            "confidence": md["confidence"],
            "confidence_reason": md["confidence_reason"],
            "transfer": tdict,
            "comparisons": comparisons,
            "summary": {
                "markdown_gain_vnd": md_total,
                "transfer_gain_vnd": tr_total,
                "difference_vnd": abs(md_total - tr_total),
                "transfer_stockout_value_vnd": so_total,
                "recommended": recommended,
                "recommendation_vi": text,
            },
            "costs": {
                "transfer_cost_per_km_vnd": ASSUMPTIONS["transfer_cost_per_km_vnd"],
                "transfer_fixed_cost_vnd": ASSUMPTIONS["transfer_fixed_cost_vnd"],
                "stockout_penalty_ratio": ASSUMPTIONS["stockout_penalty_ratio"],
            },
            "routing_defaults": {
                "num_vehicles": TRANSFER_VEHICLES,
                "vehicle_capacity": TRANSFER_VEHICLE_CAPACITY,
                "service_minutes": TRANSFER_SERVICE_MIN,
                "window_minutes": TRANSFER_WINDOW_MIN,
            },
            "assumptions_vi": [
                *md["assumptions_vi"],
                f"Chi phí điều chuyển: {vnd(ASSUMPTIONS['transfer_cost_per_km_vnd'])}/km đường + "
                f"{vnd(ASSUMPTIONS['transfer_fixed_cost_vnd'])}/chuyến; lộ trình tính bằng PACO.",
                f"Xe điều chuyển (giả định): tối đa {TRANSFER_VEHICLES} xe, mỗi xe chở "
                f"{TRANSFER_VEHICLE_CAPACITY} đơn vị, dỡ hàng {TRANSFER_SERVICE_MIN} phút mỗi cửa hàng, "
                f"giao xong trong {TRANSFER_WINDOW_MIN} phút.",
                "So sánh chỉ tính tiền mặt: điều chuyển = (giá bán − giá thanh lý) × số lượng chuyển − phần "
                "chi phí chuyến; phạt mất khách khi hết hàng ở cửa hàng nhận được ghi riêng là giá trị tránh "
                "thiếu hàng, không cộng vào so sánh.",
                "Hai cách tính trên cùng số hàng: lô hết hạn hôm nay còn lại ở thời điểm hiện tại (tồn đầu "
                "ngày trừ lượng bán kỳ vọng trước giờ này); nhu cầu các cửa hàng là phần còn lại của ngày "
                "(P10/P50/P90 nhân tỷ trọng các giờ còn lại).",
                "Hai cách là phương án thay thế nhau; chưa đánh giá kết hợp điều chuyển "
                "rồi giảm giá phần còn lại.",
            ],
            "source": SOURCE,
        }

    # ------------------------------------------------------------ routing (flow 3)

    def routing_plan(self, chain_id: str, store_id: str, now_minute: int = 0) -> dict:
        if not 0 <= now_minute <= 240:
            raise ApiError(422, "bad_now_minute", "now_minute phải từ 0 đến 240 phút.")
        return self.routing.plan_for_store(self.repo(chain_id), store_id, now_minute)


# ---------------------------------------------------------------- assumptions / FL


def assumptions_payload() -> dict[str, Any]:
    sections = [
        {"title": s["title"], "body": s["body_md"], "body_md": s["body_md"]} for s in assumptions_sections()
    ]
    roadmap: list[str] = []
    for s in sections:
        if s["title"].lower().startswith("lộ trình"):
            roadmap = [
                re.sub(r"\s+", " ", m.group(1)).strip()
                for m in re.finditer(r"(?ms)^\d+\.\s+(.*?)(?=^\d+\.\s|\Z)", s["body"])
            ]
    return {
        "label": SOURCE,
        "source": SOURCE,
        "title": "Giả định dữ liệu FreshMesh",
        "sections": sections,
        "roadmap": roadmap,
        "parameters": [
            {"key": k, "value": v, "description_vi": ASSUMPTION_DESCRIPTIONS_VI[k]}
            for k, v in ASSUMPTIONS.items()
        ],
    }


def fl_summary_payload(data_dir: Path) -> dict[str, Any]:
    """Wire `forecasting.fl.fl_summary` when that module exists; otherwise 503 `fl_not_ready`."""
    try:
        module = importlib.import_module("forecasting.fl")
    except ImportError:
        raise ApiError(503, "fl_not_ready", FL_NOT_READY_VI) from None
    fn = getattr(module, "fl_summary", None)
    if fn is None:
        raise ApiError(503, "fl_not_ready", FL_NOT_READY_VI)
    params = inspect.signature(fn).parameters
    kwargs: dict[str, Any] = {}
    if "data_dir" in params:
        kwargs["data_dir"] = data_dir
    if "docs_dir" in params:
        kwargs["docs_dir"] = REPO_ROOT / "docs" / "experiments"
    try:
        result = fn(**kwargs)
    except (FileNotFoundError, ValueError, KeyError):  # missing or partial experiment output
        log.warning("FL summary unavailable", exc_info=True)
        raise ApiError(503, "fl_not_ready", FL_NOT_READY_VI) from None
    data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    chains = data.get("chains_participating")
    if isinstance(chains, list):  # contract: a count; the chain ids stay available under "chains"
        data["chains"] = chains
        data["chains_participating"] = len(chains)
    try:
        data["forecast_model_active"] = resolve_model_kind()
    except ValueError:  # misconfigured env: forecasts would fail too, so don't claim any model is active
        data["forecast_model_active"] = "invalid"
    data.setdefault("source", SOURCE)
    return data


def plan_key(name: str) -> str:
    if name not in PLAN_KEYS:
        raise ApiError(422, "bad_plan_name", "Phương án phải là An toàn, Cân bằng hoặc Tiết kiệm.")
    return PLAN_KEYS[name]


def fmt_flow1_text(result: dict[str, Any]) -> str:
    """Vietnamese flow-1 report (used by decision.cli)."""
    lines = [
        f"FreshMesh — phương án nhập hàng (dữ liệu: {result['source']})",
        f"Cửa hàng: {result['store_id']} ({result['store_name']}) | Ngày nhận hàng: {result['order_date']}",
        "",
        "Dự báo nhu cầu (P10 / P50 / P90, đơn vị/ngày):",
    ]
    for r in result["forecast"]:
        lines.append(
            f"  {r['date']}  {r['sku_name']}: {units(r['p10'])} / {units(r['p50'])} / {units(r['p90'])}  "
            f"— độ tin cậy {r['confidence']}"
        )
    lines.append(f"Theo dõi lệch dự báo: {result['drift']['message_vi']}")
    lines.append("")
    for p in result["plans"]:
        mark = "  ← đề xuất" if p["name"] == result["recommended_plan"] else ""
        lines.append(
            f"Phương án {p['label_vi']}: tổng {vnd(p['total_cost_vnd'])}, "
            f"dự kiến bỏ {pct(p['expected_waste_pct'])}, "
            f"hết hàng {pct(p['expected_stockout_pct'])}, "
            f"xác suất không hết hàng {pct(p['service_level_pct'])}{mark}"
        )
        for line in p["lines"]:
            if line["qty"] > 0:
                lines.append(f"    - {line['sku_name']}: {line['qty']} → {vnd(line['cost_vnd'])}")
        lines.append(f"    Lý do: {p['rationale_vi']}")
    lines += [
        "",
        f"Độ tin cậy: {result['confidence']} — {result['confidence_reason']}",
        f"Đề xuất: {result['recommended_label_vi']}. {result['recommended_reason_vi']}",
        "Giả định:",
        *[f"  - {a}" for a in result["assumptions_vi"]],
        "Việc cần bạn duyệt: chọn phương án rồi bấm Duyệt trên web để tạo đơn đặt hàng (không tự đặt hàng).",
    ]
    return "\n".join(lines)
