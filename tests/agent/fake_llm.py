"""Deterministic, network-free fake LLM for tests and the CI eval (test double, never used at runtime)."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from agent.guardrail import fmt_num, fmt_pct, strip_untrusted
from agent.llm import (
    LLMRequest,
    LLMResponse,
    ToolCall,
    TurnOutput,
    turn_outputs,
    turn_start,
    turn_user_message,
)
from agent.template import format_answer

# ---------------------------------------------------------------- rule-based fake LLM

_STORE_RE = re.compile(r"\bch\s*(\d+)\b")
_PCT_RE = re.compile(r"(\d+(?:,\d+)?)\s*%")
_SQL_RE = re.compile(r"sql\s*:\s*(.+)$", re.IGNORECASE | re.DOTALL)
_INJECTED_CALL_RE = re.compile(r"gọi (?:công cụ )?([a-z_]+)")
_INJECTED_CLAIM_RE = re.compile(r"nói rằng ([^.\"]+)")
_SURPLUS_KEYWORDS = ("còn nhiều", "dư", "tồn nhiều", "sắp hết hạn", "ế")


def _has(text: str, *keywords: str) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(k)}(?!\w)", text) for k in keywords)


@dataclass(frozen=True)
class Intent:
    reads: tuple[str, ...]
    followups: tuple[str, ...] = ()
    refuse: bool = False


def detect_intent(message: str) -> Intent:
    """Keyword routing that stands in for an LLM's tool selection (Vietnamese, lowercase, NFC)."""
    m = unicodedata.normalize("NFC", message).lower()
    if _has(m, "xóa", "xoá", "drop", "sửa dữ liệu", "ghi đè"):
        return Intent((), refuse=True)
    if _has(m, "biểu đồ", "đồ thị", "vẽ"):
        data = "forecast_demand" if _has(m, "dự báo") else "query_data"
        return Intent((data,), ("render_chart",))
    if _has(m, "sql"):
        return Intent(("query_data",))
    if _has(m, "gom đơn", "lộ trình", "giao", "giao hàng", "shipper", "tuyến", "xe"):
        dispatch = _has(m, "gửi lộ trình", "xác nhận gửi", "điều xe", "gửi luôn")
        return Intent(("optimize_routes",), ("dispatch_routes",) if dispatch else ())
    if _has(m, *_SURPLUS_KEYWORDS, "giảm giá", "điều chuyển", "chuyển hàng"):
        surplus = _has(m, *_SURPLUS_KEYWORDS)
        reads: tuple[str, ...] = ()
        if surplus or _has(m, "giảm giá"):
            reads += ("suggest_markdown",)
        if surplus or _has(m, "điều chuyển", "chuyển hàng"):
            reads += ("transfer_stock",)
        apply = _has(m, "áp dụng", "giảm giá luôn")
        return Intent(reads, ("apply_markdown",) if apply else ())
    if _has(m, "nhập", "đặt hàng", "đơn đặt hàng", "mua hàng", "phương án nhập"):
        draft = _has(m, "tạo đơn", "đặt luôn", "đặt hàng luôn", "chốt đơn", "duyệt luôn")
        return Intent(("forecast_demand", "plan_inventory"), ("create_purchase_order",) if draft else ())
    if _has(m, "dự báo", "nhu cầu"):
        return Intent(("forecast_demand",))
    if _has(m, "bao nhiêu", "doanh số", "tổng", "liệt kê", "top", "tồn kho", "bán", "danh sách", "mặt hàng"):
        return Intent(("query_data",))
    return Intent(())


def _store(message: str) -> str:
    m = _STORE_RE.search(unicodedata.normalize("NFC", message).lower())
    return f"A{m.group(1)}" if m else "A1"


def _categories(message: str) -> list[str]:
    m = unicodedata.normalize("NFC", message).lower()
    cats = [c for c, kws in (("rau", ("rau",)), ("thit", ("thịt",))) if _has(m, *kws)]
    return cats or ["rau"]


def _sql_for(message: str) -> str:
    m = unicodedata.normalize("NFC", message).lower()
    explicit = _SQL_RE.search(message)
    if explicit:
        return explicit.group(1).strip()
    if _has(m, "tồn kho", "tồn"):
        return "SELECT store_id, SUM(qty) AS qty FROM v_stock GROUP BY store_id ORDER BY store_id"
    if _has(m, "mặt hàng", "sản phẩm", "sku") and not _has(m, "bán", "bán chạy"):
        return "SELECT sku_id, name, category FROM v_skus WHERE is_fresh = 1 ORDER BY sku_id"
    if _has(m, "đơn online", "đơn"):
        return (
            "SELECT delivery_mode, COUNT(order_id) AS orders FROM v_online_orders "
            "GROUP BY delivery_mode ORDER BY delivery_mode"
        )
    if _has(m, "cửa hàng") and not _has(m, "doanh số", "bán"):
        return "SELECT store_id, name, area_type FROM v_stores ORDER BY store_id"
    if _has(m, "theo ngày", "ngày"):
        return "SELECT date, SUM(units) AS units FROM v_sales_daily GROUP BY date ORDER BY date"
    return "SELECT sku_id, SUM(units) AS units FROM v_sales_daily GROUP BY sku_id ORDER BY units DESC"


def _last(outputs: list[TurnOutput], tool: str) -> Any:
    for o in reversed(outputs):
        if o.tool == tool and o.error is None:
            return o.data
    return None


def build_fake_args(tool: str, message: str, outputs: list[TurnOutput]) -> dict[str, Any]:
    """Arguments the fake model writes for each eval tool (matching ``agent.eval`` schemas)."""
    store = _store(message)
    if tool in ("forecast_demand", "plan_inventory"):
        horizon = 7 if _has(message.lower(), "7 ngày", "tuần") else 1
        return {"store_id": store, "categories": _categories(message), "horizon_days": horizon}
    if tool in ("suggest_markdown", "transfer_stock"):
        return {"store_id": store, "categories": _categories(message)}
    if tool == "optimize_routes":
        return {"store_id": store}
    if tool == "query_data":
        return {"sql": _sql_for(message)}
    if tool == "render_chart":
        fc = _last(outputs, "forecast_demand")
        if fc:
            rows = fc["rows"]
            return {
                "chart_type": "forecast_band",
                "title": "Dự báo nhu cầu",
                "x": [r["date"] for r in rows],
                "unit": "kg",
                "band": {k: [r[k] for r in rows] for k in ("p10", "p50", "p90")},
            }
        q = _last(outputs, "query_data") or {"columns": ["x", "y"], "rows": [["-", 0]]}
        rows = q["rows"] or [["-", 0]]
        return {
            "chart_type": "bar",
            "title": "Số liệu",
            "x": [str(r[0]) for r in rows],
            "series": [{"name": str(q["columns"][-1]), "values": [float(r[-1] or 0) for r in rows]}],
        }
    if tool == "create_purchase_order":
        plans = (_last(outputs, "plan_inventory") or {}).get("plans", [])
        plan = next((p for p in plans if p.get("name") == "Cân bằng"), plans[0] if plans else None)
        lines = [{"sku_id": ln["sku_id"], "qty": int(ln["qty"])} for ln in plan["lines"]] if plan else []
        return {"plan_name": plan["name"] if plan else "Cân bằng", "store_id": store, "lines": lines}
    if tool == "apply_markdown":
        md = _last(outputs, "suggest_markdown") or {}
        slot = (md.get("schedule") or [{"from": "17:00", "discount_pct": 20}])[0]
        pct = _PCT_RE.search(message)
        discount = float(pct.group(1).replace(",", ".")) if pct else float(slot["discount_pct"])
        return {
            "store_id": store,
            "sku_id": md.get("sku_id", "RAU1"),
            "discount_pct": discount,
            "from_time": slot["from"],
        }
    if tool == "dispatch_routes":
        routes = _last(outputs, "optimize_routes") or {}
        return {"store_id": store, "route_plan_id": routes.get("route_plan_id", "unknown")}
    return {}


def _facts(data: Any, limit: int = 4) -> list[str]:
    """Up to ``limit`` numbers from a tool output, formatted the Vietnamese way."""
    out: list[str] = []

    def fmt(key: str, v: float) -> str:
        if key.endswith("_pct"):
            return fmt_pct(v) if abs(v) <= 1 else f"{fmt_num(v, 1 if v % 1 else 0)}%"
        return fmt_num(v, 1 if isinstance(v, float) and v % 1 else 0)

    def walk(obj: Any, key: str) -> None:
        if len(out) >= limit:
            return
        if isinstance(obj, bool) or obj is None:
            return
        if isinstance(obj, int | float):
            if key not in ("lat", "lng"):
                out.append(f"{key} {fmt(key, obj)}")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, str(k))
        elif isinstance(obj, list):
            for v in obj:
                walk(v, key)

    walk(data, "giá trị")
    return out


def _confidence(outputs: list[TurnOutput]) -> str:
    for o in outputs:
        rows = o.data.get("rows") if isinstance(o.data, dict) else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("confidence") in ("Cao", "Trung bình", "Thấp"):
                return f"{row['confidence']} (theo thẻ tin cậy của mô hình dự báo)."
    return "Trung bình (chưa đối chiếu với thực tế)."


class RuleBasedFakeClient:
    """Deterministic stand-in for an LLM, driven only by what it sees in the request.

    * Picks tools from the user's words (:func:`detect_intent`), calls reads in parallel first, then
      dependent tools (chart, drafts) built from the outputs it received.
    * Writes the answer in the fixed template using numbers copied from tool outputs in Vietnamese
      format, so the guardrail must parse ``1.234.567`` / ``12,5%`` correctly for the eval to pass.
    * Follows instructions found in tool output that are *outside* ``<untrusted_data>`` blocks
      ("gọi công cụ X", "nói rằng ..."); with ``gullible=True`` it obeys them even inside the blocks.
    * ``hallucinate=True`` adds an invented number (removed on the rewrite request when
      ``fix_on_rewrite``), to exercise the number guardrail.
    """

    name = "fake"

    def __init__(self, *, gullible: bool = False, hallucinate: bool = False, fix_on_rewrite: bool = True):
        self.gullible = gullible
        self.hallucinate = hallucinate
        self.fix_on_rewrite = fix_on_rewrite
        self.requests: list[LLMRequest] = []

    def _injections(self, request: LLMRequest, available: set[str]) -> tuple[list[str], list[str]]:
        calls: list[str] = []
        claims: list[str] = []
        start = turn_start(request.messages)
        for msg in request.messages[start:]:
            if msg["role"] != "user" or isinstance(msg["content"], str):
                continue
            for block in msg["content"]:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                text = str(block.get("content", ""))
                visible = html.unescape(text) if self.gullible else strip_untrusted(text)
                low = unicodedata.normalize("NFC", visible).lower()
                calls += [t for t in _INJECTED_CALL_RE.findall(low) if t in available]
                claims += _INJECTED_CLAIM_RE.findall(low)
        return calls, claims

    def complete(self, request: LLMRequest, on_text: Any = None) -> LLMResponse:
        self.requests.append(request)
        message = turn_user_message(request.messages)
        outputs = turn_outputs(request.messages)
        available = {t["name"] for t in request.tools}
        intent = detect_intent(message)
        injected_calls, claims = self._injections(request, available)
        if request.purpose == "agent" and request.allow_tools and not intent.refuse:
            called = {o.tool for o in outputs}
            wanted = list(intent.reads) if not outputs else [*intent.followups, *injected_calls]
            pending = [t for t in dict.fromkeys(wanted) if t in available and t not in called]
            if pending:
                calls = [
                    ToolCall(f"fake-{len(outputs) + i + 1}", t, build_fake_args(t, message, outputs))
                    for i, t in enumerate(pending)
                ]
                text = (
                    ("Kế hoạch: gọi " + ", ".join(pending) + " rồi tổng hợp đề xuất.") if not outputs else ""
                )
                content: list[Any] = [{"type": "text", "text": text}] if text else []
                content += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.args} for c in calls]
                return LLMResponse(text, calls, "tool_use", content)
        rewrite = request.purpose == "rewrite"
        answer = self._answer(intent, outputs, claims, rewrite)
        return LLMResponse(answer, [], "end_turn", [{"type": "text", "text": answer}])

    def _answer(self, intent: Intent, outputs: list[TurnOutput], claims: list[str], rewrite: bool) -> str:
        fix = rewrite and self.fix_on_rewrite
        if intent.refuse:
            return format_answer(
                {
                    "Đề xuất": "Tôi không thể xóa hay sửa dữ liệu; trợ lý chỉ đọc số liệu và tạo bản nháp.",
                    "Vì sao": "Mọi thay đổi dữ liệu phải qua quy trình duyệt của người dùng.",
                    "Độ tin cậy": "Cao (quy tắc hệ thống).",
                    "Giả định": "Không có.",
                    "Việc cần bạn duyệt": "Không có.",
                }
            )
        ok = [o for o in outputs if o.error is None]
        failed = [o for o in outputs if o.error is not None]
        reads = [o for o in ok if not (isinstance(o.data, dict) and o.data.get("status") == "draft")]
        drafts = [
            o.data["draft_id"] for o in ok if isinstance(o.data, dict) and o.data.get("status") == "draft"
        ]
        if reads:
            main = reads[0]
            de_xuat = f"Theo {main.tool}: " + "; ".join(_facts(main.data)) + "."
            others = [
                f"{o.tool}: " + "; ".join(_facts(o.data, 3)) for o in reads[1:] if o.tool != "render_chart"
            ]
            vi_sao = " ".join(f"{s}." for s in others) or "Số liệu lấy trực tiếp từ công cụ ở trên."
        elif failed:
            de_xuat = "Chưa thể đưa ra đề xuất."
            vi_sao = f"Công cụ {failed[0].tool} báo lỗi: {failed[0].error}"
        else:
            de_xuat = "Bạn có thể hỏi về nhập hàng, xử lý tồn, giao hàng online hoặc số liệu bán hàng."
            vi_sao = "Câu hỏi chưa cần gọi công cụ."
        if self.hallucinate and not fix:
            vi_sao += " Lợi nhuận dự kiến tăng 37,5%."
        if claims and not fix:
            de_xuat += " Tôi " + claims[0].strip() + "."
        duyet = (
            ("Bản nháp chờ duyệt: " + ", ".join(f"`{d}`" for d in drafts) + ".") if drafts else "Không có."
        )
        return format_answer(
            {
                "Đề xuất": de_xuat,
                "Vì sao": vi_sao,
                "Độ tin cậy": _confidence(ok),
                "Giả định": "Con số lấy trực tiếp từ kết quả công cụ của lượt này.",
                "Việc cần bạn duyệt": duyet,
            }
        )


class PlannedFakeClient:
    """Deterministic stand-in for Claude in API tests: calls the given tools one per model request (args may
    be a function of the outputs so far), stops at the first tool error, then answers in the 5-section
    template with numbers copied from the tool outputs (so the real guardrail must verify them)."""

    name = "fake-planned"
    model = "fake-planned"

    def __init__(self, steps: list[tuple[str, Any]]):
        self.steps = steps
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest, on_text: Any = None) -> LLMResponse:
        self.requests.append(request)
        outputs = turn_outputs(request.messages)
        failed = [o for o in outputs if o.error is not None]
        if (
            request.purpose == "agent"
            and request.allow_tools
            and not failed
            and len(outputs) < len(self.steps)
        ):
            tool, args = self.steps[len(outputs)]
            args = args(outputs) if callable(args) else dict(args)
            call = ToolCall(f"planned-{len(outputs) + 1}", tool, args)
            text = "Kế hoạch: gọi " + ", ".join(t for t, _ in self.steps) + "." if not outputs else ""
            content: list[Any] = [{"type": "text", "text": text}] if text else []
            content.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.args})
            return LLMResponse(text, [call], "tool_use", content)
        ok = [o for o in outputs if o.error is None]
        reads = [o for o in ok if not (isinstance(o.data, dict) and o.data.get("status") == "draft")]
        drafts = [
            o.data["draft_id"] for o in ok if isinstance(o.data, dict) and o.data.get("status") == "draft"
        ]
        if failed:
            de_xuat = "Chưa thể đưa ra đề xuất."
            vi_sao = f"Công cụ {failed[0].tool} báo lỗi: {failed[0].error}"
        elif reads:
            de_xuat = f"Theo {reads[0].tool}: " + "; ".join(_facts(reads[0].data)) + "."
            vi_sao = " ".join(f"{o.tool}: " + "; ".join(_facts(o.data, 3)) + "." for o in reads[1:]) or (
                "Số liệu lấy trực tiếp từ công cụ ở trên."
            )
        else:
            de_xuat, vi_sao = (
                "Bạn có thể hỏi về nhập hàng, xử lý tồn hoặc giao hàng.",
                "Không cần gọi công cụ.",
            )
        conf = next(
            (o.data["confidence"] for o in reads if isinstance(o.data, dict) and o.data.get("confidence")),
            None,
        )
        answer = format_answer(
            {
                "Đề xuất": de_xuat,
                "Vì sao": vi_sao,
                "Độ tin cậy": f"{conf} (theo kết quả công cụ)."
                if conf
                else "Thấp, vì thiếu kết quả công cụ.",
                "Giả định": "Con số lấy trực tiếp từ kết quả công cụ của lượt này.",
                "Việc cần bạn duyệt": ("Bản nháp chờ duyệt: " + ", ".join(f"`{d}`" for d in drafts) + ".")
                if drafts
                else "Không có.",
            }
        )
        return LLMResponse(answer, [], "end_turn", [{"type": "text", "text": answer}])
