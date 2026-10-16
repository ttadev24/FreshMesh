import sqlite3

from api.services import FRONTIER_PLAN_NAMES
from data_sim import chain_db_path
from tests.api.conftest import assert_error


def _po(client, headers, **payload):
    body = {"store_id": "A-CH1", "plan_name": "Cân bằng", "categories": ["rau", "thit"], **payload}
    r = client.post("/api/drafts", json={"kind": "create_purchase_order", "payload": body}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["draft"]


def test_purchase_order_draft_is_not_executed_until_approved(client, owner_a):
    draft = _po(client, owner_a)
    assert draft["status"] == "draft" and "execution" not in draft["payload"]
    assert draft["payload"]["total_cost_vnd"] == sum(ln["cost_vnd"] for ln in draft["payload"]["lines"])
    assert set(draft["payload"]["options"]) == {"safe", "balanced", "lean", *FRONTIER_PLAN_NAMES}
    listed = {
        d["draft_id"]: d for d in client.get("/api/drafts?status=draft", headers=owner_a).json()["drafts"]
    }
    assert listed[draft["draft_id"]]["status"] == "draft"

    r = client.post(f"/api/drafts/{draft['draft_id']}/approve", headers=owner_a)
    body = r.json()
    assert body["draft"]["status"] == "approved" and body["draft"]["decided_by"] == "owner_a"
    po = body["execution"]
    assert po["title_vi"] == "Đơn đặt hàng" and po["type"] == "purchase_order"
    assert po["total_cost_vnd"] == draft["payload"]["total_cost_vnd"]
    assert sum(len(s["lines"]) for s in po["suppliers"]) == len(
        [ln for ln in draft["payload"]["lines"] if ln["qty"]]
    )
    # Executed once only.
    assert_error(
        client.post(f"/api/drafts/{draft['draft_id']}/approve", headers=owner_a), 409, "draft_not_pending"
    )
    assert_error(
        client.post(f"/api/drafts/{draft['draft_id']}/reject", headers=owner_a), 409, "draft_not_pending"
    )


def test_patch_switches_plan_and_reprices_lines(client, owner_a):
    draft = _po(client, owner_a)
    r = client.patch(
        f"/api/drafts/{draft['draft_id']}", json={"payload": {"selected_plan": "An toàn"}}, headers=owner_a
    )
    p = r.json()["draft"]["payload"]
    assert p["plan_name"] == "safe" and p["total_cost_vnd"] == p["options"]["safe"]["total_cost_vnd"]
    # Client-supplied money is ignored: cost comes from the DB unit cost.
    r = client.patch(
        f"/api/drafts/{draft['draft_id']}",
        json={"payload": {"lines": [{"sku_id": "SKU_RAU_MUONG", "qty": 20, "cost_vnd": 1}]}},
        headers=owner_a,
    )
    p = r.json()["draft"]["payload"]
    assert p["lines"] == [
        {
            "sku_id": "SKU_RAU_MUONG",
            "sku_name": p["lines"][0]["sku_name"],
            "qty": 20,
            "unit_cost": 8000.0,
            "cost_vnd": 160000,
            "supplier_id": p["lines"][0]["supplier_id"],
        }
    ]
    assert p["total_cost_vnd"] == 160000
    assert_error(
        client.patch(
            f"/api/drafts/{draft['draft_id']}",
            json={"payload": {"lines": [{"sku_id": "SKU_RAU_MUONG", "qty": 7}]}},
            headers=owner_a,
        ),
        422,
        "bad_moq",
    )
    assert_error(
        client.patch(
            f"/api/drafts/{draft['draft_id']}", json={"payload": {"status": "approved"}}, headers=owner_a
        ),
        422,
        "field_not_editable",
    )
    assert (
        client.get(f"/api/drafts/{draft['draft_id']}", headers=owner_a).json()["draft"]["status"] == "draft"
    )


def test_reject_and_unknown_kind(client, owner_a):
    draft = _po(client, owner_a)
    r = client.post(f"/api/drafts/{draft['draft_id']}/reject", json={"note": "không cần"}, headers=owner_a)
    assert r.json()["draft"]["status"] == "rejected"
    assert_error(
        client.post("/api/drafts", json={"kind": "delete_everything", "payload": {}}, headers=owner_a),
        422,
        "bad_draft_kind",
    )
    assert_error(client.post("/api/drafts/draft-nope/approve", headers=owner_a), 404, "draft_not_found")


def test_markdown_and_transfer_drafts(client, owner_a):
    md = client.post(
        "/api/drafts",
        json={"kind": "apply_markdown", "payload": {"store_id": "CH3", "categories": ["rau"]}},
        headers=owner_a,
    )
    assert md.status_code == 201, md.text
    item = md.json()["draft"]["payload"]["items"][0]
    sched = [{"discount_pct": 50} for _ in item["schedule"]]
    edited = client.patch(
        f"/api/drafts/{md.json()['draft']['draft_id']}",
        json={"payload": {"items": [{"sku_id": item["sku_id"], "schedule": sched}]}},
        headers=owner_a,
    ).json()["draft"]["payload"]["items"]
    changed = next(i for i in edited if i["sku_id"] == item["sku_id"])
    assert changed["edited"] and all(
        s["price_vnd"] == round(item["unit_price"] * 0.5) for s in changed["schedule"]
    )
    tr = client.post(
        "/api/drafts", json={"kind": "create_transfer", "payload": {"store_id": "CH3"}}, headers=owner_a
    )
    assert tr.status_code == 201, tr.text
    approved = client.post(f"/api/drafts/{tr.json()['draft']['draft_id']}/approve", headers=owner_a).json()
    assert approved["execution"]["type"] == "transfer_order"


def test_audit_trail_of_decisions(client, owner_a, data_dir):
    draft = _po(client, owner_a)
    client.patch(f"/api/drafts/{draft['draft_id']}", json={"payload": {"note": "giao sớm"}}, headers=owner_a)
    client.post(f"/api/drafts/{draft['draft_id']}/approve", headers=owner_a)
    entries = client.get("/api/audit?limit=1000", headers=owner_a).json()["entries"]
    mine = [e["event"] for e in reversed(entries) if e["payload"].get("draft_id") == draft["draft_id"]]
    assert mine == ["draft_created", "draft_edited", "approval"]
    approval = next(
        e for e in entries if e["event"] == "approval" and e["payload"]["draft_id"] == draft["draft_id"]
    )
    assert approval["actor"] == "owner_a" and approval["payload"]["execution"]["type"] == "purchase_order"
    # The audit log is append-only.
    con = sqlite3.connect(chain_db_path(data_dir, "CHAIN_A"))
    try:
        con.execute("DELETE FROM audit_log")
    except sqlite3.DatabaseError as exc:
        assert "append-only" in str(exc)
    else:
        raise AssertionError("audit_log rows were deleted")
    finally:
        con.close()


def test_patch_rejects_absurd_quantities(client, owner_a):
    draft = _po(client, owner_a)
    for qty in (10**12, 10**300):
        r = client.patch(
            f"/api/drafts/{draft['draft_id']}",
            json={"payload": {"lines": [{"sku_id": "SKU_RAU_MUONG", "qty": qty}]}},
            headers=owner_a,
        )
        assert_error(r, 422, "bad_qty")


def _markdown_draft(client, headers):
    r = client.post(
        "/api/drafts",
        json={"kind": "apply_markdown", "payload": {"store_id": "CH3", "categories": ["rau"]}},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["draft"]


def test_markdown_approval_execution_lists_every_item(client, owner_a):
    """HIGH-3: the price-change record carries the payload items, not sku_id None / schedule []."""
    draft = _markdown_draft(client, owner_a)
    items = draft["payload"]["items"]
    body = client.post(f"/api/drafts/{draft['draft_id']}/approve", headers=owner_a).json()
    ex = body["execution"]
    assert ex["type"] == "price_change"
    assert [i["sku_id"] for i in ex["items"]] == [i["sku_id"] for i in items]
    for got, want in zip(ex["items"], items, strict=True):
        assert got["sku_name"] == want["sku_name"]
        assert got["schedule"] == [
            {"start": s["start"], "discount_pct": s["discount_pct"], "price_vnd": s["price_vnd"]}
            for s in want["schedule"]
        ]
        assert got["expected_cash_gain_vnd"] == want["cash_gain_vnd"]
    assert ex["cash_gain_total_vnd"] == draft["payload"]["cash_gain_total_vnd"]
    assert "sku_id" not in ex and "schedule" not in ex
    entries = client.get("/api/audit?event=approval&limit=1000", headers=owner_a).json()["entries"]
    audit = next(e for e in entries if e["payload"]["draft_id"] == draft["draft_id"])
    assert audit["payload"]["execution"]["items"] == ex["items"]


def test_markdown_edit_marks_totals_not_recomputed(client, owner_a):
    """MED-1 / LOW-5: edited items lose their stale gain and the total is not presented as current."""
    draft = _markdown_draft(client, owner_a)
    item = draft["payload"]["items"][0]
    bad = [{"discount_pct": d} for d in [50] + [0] * (len(item["schedule"]) - 1)]
    if len(bad) > 1:
        err = assert_error(
            client.patch(
                f"/api/drafts/{draft['draft_id']}",
                json={"payload": {"items": [{"sku_id": item["sku_id"], "schedule": bad}]}},
                headers=owner_a,
            ),
            422,
            "bad_schedule",
        )
        assert "không được tăng lại trong ngày" in err["message_vi"]
    sched = [{"discount_pct": 50} for _ in item["schedule"]]
    p = client.patch(
        f"/api/drafts/{draft['draft_id']}",
        json={"payload": {"items": [{"sku_id": item["sku_id"], "schedule": sched}]}},
        headers=owner_a,
    ).json()["draft"]["payload"]
    assert p["cash_gain_total_vnd"] is None and "chưa tính lại" in p["cash_gain_note_vi"]
    ex = client.post(f"/api/drafts/{draft['draft_id']}/approve", headers=owner_a).json()["execution"]
    edited = next(i for i in ex["items"] if i["sku_id"] == item["sku_id"])
    assert edited["expected_cash_gain_vnd"] is None and ex["cash_gain_total_vnd"] is None


def test_transfer_edit_recomputes_totals_and_flags_route(client, owner_a):
    """MED-1: units/destinations/value/net follow the edited lines; route-dependent numbers are flagged."""
    tr = client.post(
        "/api/drafts", json={"kind": "create_transfer", "payload": {"store_id": "CH3"}}, headers=owner_a
    )
    assert tr.status_code == 201, tr.text
    draft = tr.json()["draft"]
    lines = draft["payload"]["lines"]
    assert len({ln["to_store_id"] for ln in lines}) >= 2, "fixture needs 2+ destinations"
    first = lines[0]
    # Drop every line of the first destination.
    changes = [
        {"to_store_id": ln["to_store_id"], "sku_id": ln["sku_id"], "qty": 0}
        for ln in lines
        if ln["to_store_id"] == first["to_store_id"]
    ]
    p = client.patch(
        f"/api/drafts/{draft['draft_id']}", json={"payload": {"lines": changes}}, headers=owner_a
    ).json()["draft"]["payload"]
    left = p["lines"]
    assert p["units_moved"] == sum(ln["qty"] for ln in left)
    assert p["destinations"] == len({ln["to_store_id"] for ln in left})
    assert p["saved_value_vnd"] == sum(ln["cash_value_vnd"] for ln in left) == p["saved_cash_vnd"]
    assert p["net_saving_vnd"] == p["saved_value_vnd"] - p["trip_cost_vnd"]
    assert p["recommended"] == (bool(left) and p["net_saving_vnd"] > 0)
    assert "chưa tính lại" in p["stale_route_note_vi"]
    assert p["rationale_vi"].startswith("Đã sửa số lượng")
    assert p["saved_cash_vnd"] == sum(ln["cash_value_vnd"] for ln in left)
    if left:  # halving one line scales its cash/non-cash split; the stale-route note stays
        ln = left[0]
        half = ln["qty"] // 2
        q = client.patch(
            f"/api/drafts/{draft['draft_id']}",
            json={
                "payload": {
                    "lines": [{"to_store_id": ln["to_store_id"], "sku_id": ln["sku_id"], "qty": half}]
                }
            },
            headers=owner_a,
        ).json()["draft"]["payload"]
        if half:
            got = next(
                x for x in q["lines"] if (x["to_store_id"], x["sku_id"]) == (ln["to_store_id"], ln["sku_id"])
            )
            assert got["cash_value_vnd"] == round(ln["cash_value_vnd"] * half / ln["qty"])
        assert q["units_moved"] == p["units_moved"] - (ln["qty"] - half)
        assert "chưa tính lại" in q["stale_route_note_vi"]


def test_purchase_order_with_custom_lines_does_not_reuse_plan_percentages(client, owner_a):
    """MED-1: waste/stockout % of a plan are not shown for lines that differ from that plan."""
    draft = _po(client, owner_a)
    p = client.patch(
        f"/api/drafts/{draft['draft_id']}",
        json={"payload": {"lines": [{"sku_id": "SKU_RAU_MUONG", "qty": 20}]}},
        headers=owner_a,
    ).json()["draft"]["payload"]
    assert p["expected_waste_pct"] is None and p["expected_stockout_pct"] is None
    assert "chưa tính lại" in p["plan_metrics_note_vi"]
    assert p["total_cost_vnd"] == sum(ln["cost_vnd"] for ln in p["lines"])
    # Switching back to a plan restores its own numbers.
    p = client.patch(
        f"/api/drafts/{draft['draft_id']}", json={"payload": {"selected_plan": "Cân bằng"}}, headers=owner_a
    ).json()["draft"]["payload"]
    assert p["expected_waste_pct"] == p["options"]["balanced"]["expected_waste_pct"]
    assert p.get("plan_metrics_note_vi") is None
    # Same at creation time.
    created = _po(client, owner_a, lines=[{"sku_id": "SKU_RAU_MUONG", "qty": 20}])["payload"]
    assert created["expected_waste_pct"] is None and "chưa tính lại" in created["plan_metrics_note_vi"]
