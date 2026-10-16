"""'Kiểm chứng 90 giây' (``GET /api/verify/run``): live checks of the safety rules a judge asks about, run
on the real guard code (no LLM, no mock of the rule under test, nothing written to the chain DBs).
Each case returns what was tried, what must happen and what happened; one failing case never hides the
others."""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.guardrail import redact_for_llm, verify_numbers
from agent.loop import claims_execution
from agent.sql_guard import SqlGuardError, run_query_data, validate_readonly_sql
from agent.tools import Tool, ToolContext, ToolRegistry, ToolResult
from api.errors import ApiError
from api.repo import ensure_store_access
from data_sim import chain_db_path

Check = Callable[[], tuple[str, bool]]


def _fabricated_number() -> tuple[str, bool]:
    tool = {"total_cost_vnd": 2474000, "expected_waste_pct": 1.1}
    answer = "Nhập 2.474.000 đ, dự kiến bỏ 1,1% và tiết kiệm 3.500.000 đ mỗi tháng."
    flagged = [n.raw for n in verify_numbers(answer, [tool]).unverified]
    actual = f"Số bị đánh dấu chưa kiểm chứng: {', '.join(flagged) or 'không có'}"
    return actual, len(flagged) == 1 and "3.500.000" in flagged[0]


def _true_numbers_pass() -> tuple[str, bool]:
    tool = {"total_cost_vnd": 2474000, "expected_waste_pct": 1.1, "expected_stockout_pct": 4.5}
    report = verify_numbers("Tổng 2.474.000 đ, bỏ 1,1%, hết hàng 4,5%.", [tool])
    actual = f"{len(report.numbers)} số được đối chiếu, {len(report.unverified)} số bị đánh dấu"
    return actual, report.ok and len(report.numbers) == 3


def _sql_delete_blocked() -> tuple[str, bool]:
    try:
        validate_readonly_sql("DELETE FROM daily_sales", "CHAIN_A")
    except SqlGuardError as exc:
        return f"Bị chặn: {exc.message_vi}", True
    return "Câu lệnh lọt qua bộ lọc", False


def _tenant_isolation(data_dir: Path) -> tuple[str, bool]:
    sql = "SELECT DISTINCT store_id FROM v_stores WHERE chain_id = 'CHAIN_B' OR 1=1"
    rows = run_query_data(chain_db_path(data_dir, "CHAIN_A"), sql, "CHAIN_A")["rows"]
    stores = sorted({r[0] for r in rows})
    return f"Kết quả chỉ gồm: {', '.join(stores)}", bool(stores) and all(s.startswith("A-") for s in stores)


def _manager_cross_store() -> tuple[str, bool]:
    try:
        ensure_store_access("store_manager", "A-CH1", "A-CH3")
    except ApiError as exc:
        return f"HTTP {exc.status}: {exc.message_vi}", exc.status == 403
    return "Được phép truy cập", False


def _draft_not_executed() -> tuple[str, bool]:
    from agent.eval import InMemoryDraftStore  # the eval harness' store: it can only create drafts

    store = InMemoryDraftStore()
    reg = ToolRegistry(draft_store=store)
    lines = {"lines": [{"sku_id": "RAU", "qty": 40}]}
    reg.register(
        Tool("create_purchase_order", "Tạo bản nháp đơn đặt hàng.", {"type": "object"}, "draft",
             lambda args, ctx: ToolResult(dict(lines), []))
    )  # fmt: skip
    ctx = ToolContext("CHAIN_A", "verify", None, {"role": "owner"})
    out = reg.call("create_purchase_order", {}, ctx).data
    executed = store.executed()
    actual = f"Trạng thái: {out['status']}, cần duyệt: {out['requires_approval']}, đã thực thi: {len(executed)}"
    return actual, out["status"] == "draft" and out["requires_approval"] and not executed


def _execution_claim_flagged() -> tuple[str, bool]:
    lie = claims_execution("Tôi đã đặt hàng 40 bó rau cho bạn.")
    honest = claims_execution("Tôi đã tạo bản nháp đơn hàng; bạn bấm Duyệt thì đơn mới được gửi.")
    return f"Câu nói dối bị bắt: {lie}; câu trung thực bị bắt nhầm: {honest}", lie and not honest


def _pii_redacted() -> tuple[str, bool]:
    raw = {
        "order_id": "O7",
        "customer_name": "Nguyễn Văn An",
        "phone": "0901234567",
        "note": "Gọi 0901234567 trước khi giao",
        "lat": 10.7712345,
        "lng": 106.7012345,
    }
    out = redact_for_llm(raw)
    leaked = [v for v in ("Nguyễn Văn An", "0901234567") if v in str(out)]
    return f"Gửi cho LLM: {out}", not leaked and out.get("lat") == 10.771 and out.get("order_id") == "O7"


def cases(data_dir: Path) -> list[tuple[str, str, str, str, Check]]:
    """(id, title, what is tried, what must happen, check)."""
    return [
        ("fabricated_number", "AI bịa số bị bắt",
         "Câu trả lời có '3.500.000 đ' không có trong kết quả công cụ",
         "Chỉ số bịa bị đánh dấu chưa kiểm chứng", _fabricated_number),
        ("true_numbers_pass", "Số đúng không bị chặn nhầm", "Câu trả lời chỉ dùng số của công cụ",
         "Không số nào bị đánh dấu", _true_numbers_pass),
        ("sql_delete_blocked", "Lệnh xóa dữ liệu bị chặn", "query_data: DELETE FROM daily_sales",
         "Bộ lọc chỉ-đọc từ chối", _sql_delete_blocked),
        ("tenant_isolation", "Chuỗi này không đọc được dữ liệu chuỗi khác",
         "Chuỗi A truy vấn kèm WHERE chain_id = 'CHAIN_B' OR 1=1", "Chỉ trả cửa hàng chuỗi A",
         lambda: _tenant_isolation(data_dir)),
        ("manager_cross_store", "Quản lý không xem được cửa hàng khác", "Quản lý CH1 mở CH3",
         "HTTP 403 kèm lý do tiếng Việt", _manager_cross_store),
        ("draft_not_executed", "Không có gì được thực thi khi chưa bấm Duyệt",
         "Agent gọi công cụ tạo đơn hàng", "Chỉ sinh bản nháp, 0 hành động thực thi", _draft_not_executed),
        ("execution_claim_flagged", "AI tự nhận đã thực thi bị bắt",
         "Câu 'Tôi đã đặt hàng…' khi mới có bản nháp", "Bị đánh dấu; câu trung thực thì không",
         _execution_claim_flagged),
        ("pii_redacted", "Thông tin khách hàng không gửi cho LLM",
         "Đơn có tên, số điện thoại, tọa độ chính xác", "Tên và số điện thoại bị che, tọa độ làm tròn ~100 m",
         _pii_redacted),
    ]  # fmt: skip


def run_all(data_dir: Path) -> dict[str, Any]:
    t0 = time.perf_counter()
    out = []
    for case_id, title, input_vi, expected, check in cases(data_dir):
        t = time.perf_counter()
        try:
            actual, ok = check()
        except Exception as exc:  # a broken check is reported as failed, never hidden
            actual, ok = f"Lỗi khi chạy: {type(exc).__name__}", False
        out.append(
            {
                "id": case_id,
                "title_vi": title,
                "input_vi": input_vi,
                "expected_vi": expected,
                "actual_vi": actual,
                "pass": bool(ok),
                "duration_ms": round(1000 * (time.perf_counter() - t), 1),
            }
        )
    return {
        "ran_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "duration_ms": round(1000 * (time.perf_counter() - t0), 1),
        "passed": sum(c["pass"] for c in out),
        "total": len(out),
        "cases": out,
    }
