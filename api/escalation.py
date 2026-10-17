"""When FreshMesh stops and hands the decision to a person (human in the loop). One policy, three kinds:

* ``missing_data`` — the plan rests on thin or drifting evidence (a new store, low 7-day forecast coverage):
  ask for the fact that would change it and say what is used meanwhile.
* ``out_of_scope`` — the owner's goals cannot all be met (``decision.frontier.choose_for_goal``): ask which
  goal gives, with the concrete options. Nothing is chosen silently.
* ``authority`` — a store manager approves above their limit: purchase orders of one store and delivery
  day add up (splitting an order does not get around it), and markdowns deeper than the cap. The draft stays
  pending and goes to the owner; nothing is executed.

Every escalation is ``{kind, reason_vi, question_vi, choices_vi}`` plus kind-specific fields. An approved
action can be undone within ``undo_window_min`` by its approver or the owner; undo is audited and puts the
draft back to pending (``api.drafts``). Routes already sent to shippers are not undone. A limit of 0 switches
its rule off; an undo window of 0 switches undo off.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from decision.text import pct, vnd
from forecasting.confidence import SHORT_HISTORY_DAYS

ESCALATION_KINDS = ("missing_data", "out_of_scope", "authority")


def _pct(value: float) -> str:  # "50%", "37,5%"
    return pct(value).replace(",0%", "%")


@dataclass(frozen=True)
class ApprovalPolicy:
    manager_order_limit_vnd: int = 5_000_000
    manager_max_discount_pct: int = 30  # markdown levels are 10/20/30/50%: 50% needs the owner
    undo_window_min: int = 30


def escalation(kind: str, reason_vi: str, question_vi: str, choices_vi: list[str], **extra: Any) -> dict:
    if kind not in ESCALATION_KINDS:
        raise ValueError(f"unknown escalation kind {kind!r}")
    base = {"kind": kind, "reason_vi": reason_vi, "question_vi": question_vi, "choices_vi": choices_vi}
    return base | extra


# ---------------------------------------------------------------- missing_data (inventory plans)


def data_questions(history_days: int, drift: dict[str, Any]) -> list[dict]:
    """Questions whose answer would change the plan, asked instead of pretending the forecast is sure."""
    out = []
    if history_days < SHORT_HISTORY_DAYS:
        out.append(escalation(
            "missing_data",
            f"Cửa hàng mới có {history_days} ngày lịch sử (cần {SHORT_HISTORY_DAYS} ngày để dự báo vững); "
            "khoảng dự báo còn rộng.",
            "Bạn có số bán thực tế 7 ngày gần nhất của cửa hàng (hoặc file bán hàng từ máy POS) không? "
            "Có số này, khoảng dự báo hẹp lại và đơn nhập sát nhu cầu hơn.",
            ["Tải file bán hàng (CSV)", "Chưa có, dùng dự báo hiện tại"],
            field="recent_sales",
        ))  # fmt: skip
    if drift.get("alert"):
        coverage = drift.get("coverage_7d")
        seen = f"chỉ {_pct(100 * coverage)}" if coverage is not None else "thấp"
        out.append(escalation(
            "missing_data",
            f"7 ngày qua, nhu cầu thật rơi vào khoảng dự báo {seen} số lần (mục tiêu 80%).",
            "Tuần qua cửa hàng có gì bất thường không (khuyến mãi, đóng cửa, sửa đường, mất điện)? "
            "Biết nguyên nhân thì FreshMesh không học nhầm ngày bất thường.",
            ["Có, tôi ghi chú sự kiện", "Không có gì, dùng phương án An toàn"],
            field="events",
        ))  # fmt: skip
    return out


# ---------------------------------------------------------------- authority (draft approval)


def order_value_vnd(payload: dict[str, Any]) -> int:
    return int(sum(ln.get("cost_vnd", 0) for ln in payload.get("lines", []) if ln.get("qty", 0) > 0))


def max_discount_pct(payload: dict[str, Any]) -> float:
    slots = [s for item in payload.get("items", []) for s in item.get("schedule", [])]
    return max((float(s.get("discount_pct") or 0) for s in slots), default=0.0)


def approval_escalation(
    kind: str,
    payload: dict[str, Any],
    *,
    is_owner: bool,
    policy: ApprovalPolicy,
    approved_same_day_vnd: int = 0,
) -> dict | None:
    """The authority escalation a store manager's approval triggers, or None when they may approve.
    ``approved_same_day_vnd``: purchase orders the store's managers already approved for the same delivery
    day (the limit is per store and day)."""
    if is_owner:
        return None
    choices = ["Chuyển chủ chuỗi duyệt", "Sửa bản nháp cho trong hạn mức"]
    limit = policy.manager_order_limit_vnd
    value = order_value_vnd(payload)
    if kind == "create_purchase_order" and limit and value + approved_same_day_vnd > limit:
        already = (
            f" cộng {vnd(approved_same_day_vnd)} quản lý đã duyệt cho cùng ngày giao"
            if approved_same_day_vnd
            else ""
        )
        return escalation(
            "authority",
            f"Đơn nhập {vnd(value)}{already} vượt hạn mức duyệt {vnd(limit)}/ngày của quản lý cửa hàng.",
            f"Chủ chuỗi duyệt đơn nhập {vnd(value)} này, hay quản lý giảm đơn để tổng trong ngày không quá "
            f"{vnd(limit)}?",
            choices,
            needs_role="owner",
            value_vnd=value,
            approved_same_day_vnd=approved_same_day_vnd,
            limit_vnd=limit,
        )
    depth, cap = max_discount_pct(payload), policy.manager_max_discount_pct
    if kind == "apply_markdown" and cap and depth > cap:
        return escalation(
            "authority",
            f"Mức giảm giá {_pct(depth)} vượt mức tối đa {_pct(cap)} quản lý cửa hàng được tự duyệt.",
            f"Chủ chuỗi duyệt mức giảm {_pct(depth)}, hay quản lý giảm nhẹ hơn (tối đa {_pct(cap)})?",
            choices,
            needs_role="owner",
            discount_pct=depth,
            limit_pct=cap,
        )
    return None


# ---------------------------------------------------------------- undo of an approved draft


def undo_refusal(
    draft: dict[str, Any], *, username: str, is_owner: bool, now: dt.datetime, policy: ApprovalPolicy
) -> tuple[int, str, str] | None:
    """``(HTTP status, code, Vietnamese reason)`` when the approved draft cannot be undone now, else None."""
    if not is_owner and draft.get("decided_by") != username:
        return 403, "forbidden_undo", "Chỉ người đã duyệt hoặc chủ chuỗi được hoàn tác bản nháp này."
    if draft.get("kind") == "dispatch_routes":
        msg = "Lộ trình đã gửi cho shipper không hoàn tác được; hãy lập lộ trình mới."
        return 409, "undo_not_supported", msg
    if not policy.undo_window_min:
        return 409, "undo_disabled", "Hệ thống này đã tắt chức năng hoàn tác."
    if not draft.get("decided_at"):
        return 409, "undo_window_passed", "Không rõ thời điểm duyệt nên không hoàn tác được."
    decided = dt.datetime.fromisoformat(draft["decided_at"])
    if decided.tzinfo is None:  # written as UTC
        decided = decided.replace(tzinfo=dt.UTC)
    minutes = (now - decided).total_seconds() / 60
    if minutes > policy.undo_window_min:
        return (
            409,
            "undo_window_passed",
            f"Đã quá {policy.undo_window_min} phút kể từ lúc duyệt ({round(minutes)} phút); "
            "không hoàn tác được nữa, hãy tạo bản nháp điều chỉnh mới.",
        )
    return None
