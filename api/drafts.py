"""Drafts (`drafts` table of the chain DB) and the human approval path.

* Agent/UI tools only *create* drafts (``SqlDraftStore.create_draft``, the ``agent.tools.DraftStore``
  protocol). Nothing is executed at creation time.
* ``approve`` is the ONLY execution path: status transition (``approved``; ``dispatched`` for
  ``dispatch_routes``) + an execution record written into the payload (e.g. the "đơn đặt hàng" of a
  purchase order) + an ``approval`` audit entry, all in one transaction. Execution is simulated: no external
  system (supplier, POS, shipper app) is called.
* Only ``draft`` rows can be approved, rejected or edited (409 otherwise).
* Role rule: a store manager may list/edit/approve/reject only drafts whose ``payload.store_id`` is their
  store; the owner may act on every draft of the chain.
* Authority (``api.escalation``): a manager's approval above their limit is not executed; the draft stays
  pending with ``payload.escalation`` for the owner and the call answers 403 ``needs_owner``.
* Undo: an approved draft goes back to pending within the undo window (approver or owner); its execution
  record moves to ``payload.undone``.
* Audit entries are inserted into ``audit_log`` in the same transaction (events ``draft_created``,
  ``draft_edited``, ``approval``, ``escalation``, ``undo``, ``rejection``).
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.audit import AuditLog
from agent.template import UNKNOWN_SOURCE_ID
from api import provenance_view
from api.auth import User
from api.errors import ApiError
from api.escalation import ApprovalPolicy, approval_escalation, undo_refusal
from data_sim import chain_db_path

DRAFT_KINDS = ("create_purchase_order", "apply_markdown", "create_transfer", "dispatch_routes")
KIND_LABEL_VI = {
    "create_purchase_order": "Đơn đặt hàng",
    "apply_markdown": "Lịch giảm giá",
    "create_transfer": "Phiếu điều chuyển",
    "dispatch_routes": "Gửi lộ trình cho shipper",
}
EDITABLE_FIELDS = {
    "create_purchase_order": {"selected_plan", "lines", "note"},
    "apply_markdown": {"items", "note"},
    "create_transfer": {"lines", "note"},
    "dispatch_routes": {"note"},
}
SIM_NOTE_VI = "Thực thi giả lập: chưa kết nối hệ thống thật (nhà cung cấp, máy POS, shipper)."


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _row_to_dict(row: sqlite3.Row, data_dir: Path) -> dict[str, Any]:
    payload = json.loads(row["payload_json"] or "{}")
    return {
        "draft_id": row["draft_id"],
        "chain_id": row["chain_id"],
        "kind": row["kind"],
        "kind_label_vi": KIND_LABEL_VI.get(row["kind"], row["kind"]),
        "store_id": payload.get("store_id"),
        "payload": payload,
        "status": row["status"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "decided_at": row["decided_at"],
        "decided_by": row["decided_by"],
        **_draft_provenance(payload, row["source"], data_dir),
    }


def _draft_provenance(payload: dict[str, Any], column: str | None, data_dir: Path) -> dict[str, list[str]]:
    """Provenance of the computation the draft was built from (stored in the payload); drafts written before
    provenance existed fall back to the DB column, whose unknown ids are labelled "không rõ nguồn"."""
    if payload.get("sources"):
        return provenance_view.labelled(payload["sources"], data_dir)
    return provenance_view.labelled((column or "").split(";"), data_dir)


class SqlDraftStore:
    """Drafts of one data root; every call is scoped to a chain DB (tenant)."""

    def __init__(self, data_dir: Path, policy: ApprovalPolicy | None = None):
        self.data_dir = Path(data_dir)
        self.policy = policy or ApprovalPolicy()

    def _connect(self, chain_id: str) -> sqlite3.Connection:
        path = chain_db_path(self.data_dir, chain_id)
        if not path.exists():
            raise ApiError(503, "data_not_ready", "Chưa có dữ liệu của chuỗi; hãy chạy bootstrap.")
        AuditLog(path)  # ensures the append-only triggers exist (DDL runs once per DB file, then memoised)
        con = sqlite3.connect(path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _audit(
        con: sqlite3.Connection, chain_id: str, actor: str, event: str, payload: dict[str, Any]
    ) -> None:
        con.execute(
            "INSERT INTO audit_log(chain_id, ts, actor, event, payload_json) VALUES (?,?,?,?,?)",
            (
                chain_id,
                _now(),
                actor,
                event,
                json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True),
            ),
        )

    # ------------------------------------------------------------ DraftStore protocol

    def create_draft(self, *, chain_id: str, kind: str, payload: dict[str, Any], created_by: str) -> str:
        if kind not in DRAFT_KINDS:
            raise ApiError(422, "bad_draft_kind", f"Loại bản nháp '{kind}' không được hỗ trợ.")
        draft_id = f"draft-{uuid.uuid4().hex[:12]}"
        body = dict(payload)
        source_column = ";".join(sorted(set(body.get("sources") or [UNKNOWN_SOURCE_ID])))
        con = self._connect(chain_id)
        try:
            with con:
                con.execute(
                    "INSERT INTO drafts(draft_id, chain_id, kind, payload_json, status, created_by, "
                    "created_at, source) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        draft_id,
                        chain_id,
                        kind,
                        json.dumps(body, ensure_ascii=False, default=str),
                        "draft",
                        created_by,
                        _now(),
                        source_column,
                    ),
                )
                self._audit(
                    con,
                    chain_id,
                    created_by,
                    "draft_created",
                    {"draft_id": draft_id, "kind": kind, "store_id": body.get("store_id")},
                )
        finally:
            con.close()
        return draft_id

    # ------------------------------------------------------------ reads

    def list(self, user: User, *, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM drafts WHERE chain_id = ?"
        params: list[Any] = [user.chain_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        if not user.is_owner:
            sql += " AND json_extract(payload_json, '$.store_id') = ?"
            params.append(user.store_id)
        sql += " ORDER BY created_at DESC, draft_id"
        con = self._connect(user.chain_id)
        try:
            return [_row_to_dict(r, self.data_dir) for r in con.execute(sql, params).fetchall()]
        finally:
            con.close()

    def get(self, user: User, draft_id: str) -> dict[str, Any]:
        con = self._connect(user.chain_id)
        try:
            row = con.execute(
                "SELECT * FROM drafts WHERE draft_id = ? AND chain_id = ?", (draft_id, user.chain_id)
            ).fetchone()
        finally:
            con.close()
        if row is None:
            raise ApiError(404, "draft_not_found", "Không tìm thấy bản nháp.")
        draft = _row_to_dict(row, self.data_dir)
        self._check_scope(user, draft)
        return draft

    @staticmethod
    def _check_scope(user: User, draft: dict[str, Any]) -> None:
        if not user.is_owner and draft["store_id"] != user.store_id:
            raise ApiError(
                403,
                "forbidden_draft",
                f"Bản nháp này thuộc cửa hàng {draft['store_id']}; bạn chỉ được duyệt bản nháp của "
                f"cửa hàng {user.store_id}.",
            )

    # ------------------------------------------------------------ decisions

    def _transition(
        self,
        user: User,
        draft_id: str,
        mutate: Callable[[dict[str, Any]], tuple[str, dict[str, Any], str, dict[str, Any]]],
        from_status: tuple[str, ...] = ("draft",),
    ) -> dict[str, Any]:
        """Load (scoped) → check status → mutate → write row + audit atomically."""
        con = self._connect(user.chain_id)
        try:
            with con:
                con.execute("BEGIN IMMEDIATE")
                row = con.execute(
                    "SELECT * FROM drafts WHERE draft_id = ? AND chain_id = ?", (draft_id, user.chain_id)
                ).fetchone()
                if row is None:
                    raise ApiError(404, "draft_not_found", "Không tìm thấy bản nháp.")
                draft = _row_to_dict(row, self.data_dir)
                self._check_scope(user, draft)
                if draft["status"] not in from_status:
                    raise ApiError(
                        409,
                        "draft_not_pending",
                        f"Bản nháp đã ở trạng thái '{draft['status']}', không thể thay đổi.",
                    )
                status, payload, event, audit_payload = mutate(draft)
                decided = status != "draft"
                con.execute(
                    "UPDATE drafts SET status = ?, payload_json = ?, decided_at = ?, decided_by = ? "
                    "WHERE draft_id = ?",
                    (
                        status,
                        json.dumps(payload, ensure_ascii=False, default=str),
                        _now() if decided else None,
                        user.username if decided else None,
                        draft_id,
                    ),
                )
                self._audit(con, user.chain_id, user.username, event, audit_payload)
            return self.get(user, draft_id)
        finally:
            con.close()

    def approve(self, user: User, draft_id: str) -> dict[str, Any]:
        escalated: dict[str, Any] = {}

        def mutate(draft: dict[str, Any]) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
            payload = dict(draft["payload"])
            ref = {"draft_id": draft["draft_id"], "kind": draft["kind"], "store_id": draft["store_id"]}
            esc = approval_escalation(draft["kind"], payload, is_owner=user.is_owner, policy=self.policy)
            if esc:  # not executed: stays pending for the owner
                payload["escalation"] = {**esc, "requested_by": user.username, "requested_at": _now()}
                escalated.update(payload["escalation"])
                return "draft", payload, "escalation", {**ref, "escalation": payload["escalation"]}
            record, status = execution_record(draft, user)
            payload["execution"] = record
            if payload.get("escalation"):
                resolved = {"resolved_by": user.username, "resolved_at": record["executed_at"]}
                payload["escalation"] = {**payload["escalation"], **resolved}
            audit = {**ref, "decision": "approved", "status": status, "execution": record}
            return status, payload, "approval", audit

        draft = self._transition(user, draft_id, mutate)
        if escalated:
            raise ApiError(403, "needs_owner", f"{escalated['reason_vi']} Đã chuyển chủ chuỗi duyệt; "
                           "bản nháp vẫn chờ, chưa có gì được thực thi.")  # fmt: skip
        return draft

    def undo(self, user: User, draft_id: str) -> dict[str, Any]:
        def mutate(draft: dict[str, Any]) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
            now = dt.datetime.now(dt.UTC)
            refusal = undo_refusal(
                draft, username=user.username, is_owner=user.is_owner, now=now, policy=self.policy
            )
            if refusal:
                raise ApiError(*refusal)
            payload = dict(draft["payload"])
            record = payload.pop("execution", None) or {}
            undone = {**record, "undone_by": user.username, "undone_at": now.isoformat(timespec="seconds")}
            payload["undone"] = [*payload.get("undone", []), undone]
            audit = {
                "draft_id": draft["draft_id"],
                "kind": draft["kind"],
                "store_id": draft["store_id"],
                "decision": "undone",
                "from_status": draft["status"],
                "record": record.get("po_number") or record.get("record_id"),
            }
            return "draft", payload, "undo", audit

        return self._transition(user, draft_id, mutate, from_status=("approved", "dispatched"))

    def reject(self, user: User, draft_id: str, note: str = "") -> dict[str, Any]:
        def mutate(draft: dict[str, Any]) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
            audit = {
                "draft_id": draft["draft_id"],
                "kind": draft["kind"],
                "store_id": draft["store_id"],
                "decision": "rejected",
                "note": note,
            }
            return "rejected", draft["payload"], "rejection", audit

        return self._transition(user, draft_id, mutate)

    def edit(
        self, user: User, draft_id: str, changes: dict[str, Any], apply: Callable[[dict, dict], dict]
    ) -> dict[str, Any]:
        def mutate(draft: dict[str, Any]) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
            allowed = EDITABLE_FIELDS.get(draft["kind"], {"note"})
            bad = sorted(set(changes) - allowed)
            if bad:
                raise ApiError(
                    422,
                    "field_not_editable",
                    f"Không được sửa trường {', '.join(bad)}; chỉ sửa được: {', '.join(sorted(allowed))}.",
                )
            payload = apply(draft, changes)
            payload["edited_by"] = user.username
            audit = {
                "draft_id": draft["draft_id"],
                "kind": draft["kind"],
                "store_id": draft["store_id"],
                "changes": changes,
            }
            return "draft", payload, "draft_edited", audit

        return self._transition(user, draft_id, mutate)


def execution_record(draft: dict[str, Any], user: User) -> tuple[dict[str, Any], str]:
    """Simulated execution of an approved draft → (record stored in the payload, new status)."""
    p = draft["payload"]
    now = _now()
    kind = draft["kind"]
    base = {"executed_at": now, "approved_by": user.username, "note_vi": SIM_NOTE_VI}
    suffix = draft["draft_id"].split("-")[-1][:8].upper()
    if kind == "create_purchase_order":
        suppliers: dict[str, dict[str, Any]] = {}
        for line in p.get("lines", []):
            if line.get("qty", 0) <= 0:
                continue
            group = suppliers.setdefault(
                line.get("supplier_id", "?"),
                {"supplier_id": line.get("supplier_id"), "lines": [], "subtotal_vnd": 0},
            )
            group["lines"].append(line)
            group["subtotal_vnd"] += line["cost_vnd"]
        return (
            {
                **base,
                "type": "purchase_order",
                "title_vi": "Đơn đặt hàng",
                "po_number": f"PO-{p.get('order_date', '')}-{suffix}",
                "store_id": p.get("store_id"),
                "delivery_date": p.get("order_date"),
                "plan_label_vi": p.get("plan_label_vi"),
                "suppliers": list(suppliers.values()),
                "total_cost_vnd": sum(g["subtotal_vnd"] for g in suppliers.values()),
                "status_vi": "Đơn đặt hàng đã lập (giả lập), chưa gửi tới nhà cung cấp thật.",
            },
            "approved",
        )
    if kind == "apply_markdown":
        return (
            {
                **base,
                "type": "price_change",
                "title_vi": "Lịch giảm giá đã duyệt",
                "record_id": f"MD-{suffix}",
                "store_id": p.get("store_id"),
                "items": [
                    {
                        "sku_id": item.get("sku_id"),
                        "sku_name": item.get("sku_name"),
                        "schedule": [
                            {
                                "start": slot.get("start"),
                                "discount_pct": slot.get("discount_pct"),
                                "price_vnd": slot.get("price_vnd"),
                            }
                            for slot in item.get("schedule", [])
                        ],
                        # None after a manual edit: the gain was not recomputed for the edited schedule.
                        "expected_cash_gain_vnd": item.get("cash_gain_vnd"),
                    }
                    for item in p.get("items", [])
                ],
                "cash_gain_total_vnd": p.get("cash_gain_total_vnd"),
                "status_vi": "Lịch giảm giá đã duyệt (giả lập), chưa đẩy tới máy POS thật.",
            },
            "approved",
        )
    if kind == "create_transfer":
        return (
            {
                **base,
                "type": "transfer_order",
                "title_vi": "Phiếu điều chuyển",
                "record_id": f"TR-{suffix}",
                "from_store_id": p.get("store_id"),
                "lines": p.get("lines", []),
                "status_vi": "Phiếu điều chuyển đã lập (giả lập).",
            },
            "approved",
        )
    if kind == "dispatch_routes":
        return (
            {
                **base,
                "type": "dispatch",
                "title_vi": "Lộ trình đã gửi",
                "record_id": f"DP-{suffix}",
                "store_id": p.get("store_id"),
                "route_plan_id": p.get("route_plan_id"),
                "vehicles": [
                    {
                        "vehicle_label": r.get("vehicle_label"),
                        "order_ids": [s["order_id"] for s in r["stops"]],
                    }
                    for r in p.get("routes", [])
                ],
                "status_vi": "Lộ trình đã đánh dấu gửi cho shipper (giả lập).",
            },
            "dispatched",
        )
    raise ApiError(422, "bad_draft_kind", f"Loại bản nháp '{kind}' không được hỗ trợ.")
