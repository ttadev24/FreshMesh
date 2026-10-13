from tests.api.conftest import assert_error


def test_manager_sees_only_own_store(client, manager_a):
    stores = client.get("/api/stores", headers=manager_a).json()
    assert [s["store_id"] for s in stores] == ["A-CH1"]


def test_manager_defaults_to_own_store(client, manager_a):
    body = client.get("/api/forecast?categories=rau", headers=manager_a).json()
    assert body["store_id"] == "A-CH1"


def test_manager_forbidden_on_other_stores(client, manager_a):
    assert_error(client.get("/api/forecast?store_id=A-CH3", headers=manager_a), 403, "forbidden_store")
    for path, body in (
        ("/api/inventory/plan", {"store_id": "A-CH2"}),
        ("/api/markdown/suggest", {"store_id": "CH3"}),
        ("/api/transfer/plan", {"store_id": "CH3"}),
        ("/api/routing/plan", {"store_id": "A-CH4"}),
        ("/api/drafts", {"kind": "dispatch_routes", "payload": {"store_id": "A-CH4"}}),
        ("/api/agent/scenario/2", {"store_id": "CH3"}),
    ):
        assert_error(client.post(path, json=body, headers=manager_a), 403, "forbidden_store")


def test_manager_cannot_approve_other_store_drafts(client, owner_a, manager_a):
    other = client.post("/api/drafts", json={"kind": "dispatch_routes", "payload": {"store_id": "A-CH2"}},
                        headers=owner_a).json()["draft"]
    assert_error(client.post(f"/api/drafts/{other['draft_id']}/approve", headers=manager_a), 403, "forbidden_draft")
    assert_error(client.post(f"/api/drafts/{other['draft_id']}/reject", headers=manager_a), 403, "forbidden_draft")
    assert_error(client.patch(f"/api/drafts/{other['draft_id']}", json={"payload": {"note": "x"}}, headers=manager_a),
                 403, "forbidden_draft")
    listed = client.get("/api/drafts", headers=manager_a).json()["drafts"]
    assert all(d["store_id"] == "A-CH1" for d in listed)
    own = client.post("/api/drafts", json={"kind": "dispatch_routes", "payload": {}}, headers=manager_a)
    assert own.status_code == 201 and own.json()["draft"]["store_id"] == "A-CH1"
    approved = client.post(f"/api/drafts/{own.json()['draft']['draft_id']}/approve", headers=manager_a)
    assert approved.json()["draft"]["status"] == "dispatched"


def test_manager_audit_is_scoped(client, owner_a, manager_a):
    client.post("/api/drafts", json={"kind": "dispatch_routes", "payload": {"store_id": "A-CH5"}}, headers=owner_a)
    entries = client.get("/api/audit", headers=manager_a).json()["entries"]
    for e in entries:
        p = e["payload"]
        about_store = p.get("store_id") == "A-CH1" or (
            e["event"] == "tool_call" and (p.get("output") or {}).get("store_id") == "A-CH1"
        )
        assert e["actor"] == "manager_a1" or about_store
    owner_entries = client.get("/api/audit", headers=owner_a).json()["entries"]
    assert any(e["payload"].get("store_id") == "A-CH5" for e in owner_entries)


def test_manager_sees_tool_calls_about_own_store_only(client, owner_a, manager_a):
    """OPEN (d): tool_call entries carry the store in the server-computed output; a manager sees those of
    their store (whoever ran them) and never another store's."""
    t1 = client.post("/api/agent/scenario/3", json={"store_id": "A-CH1"}, headers=owner_a).json()["turn_id"]
    t2 = client.post("/api/agent/scenario/3", json={"store_id": "A-CH2"}, headers=owner_a).json()["turn_id"]
    own = client.post("/api/agent/scenario/3", json={}, headers=manager_a).json()["turn_id"]
    entries = client.get("/api/audit?event=tool_call&limit=1000", headers=manager_a).json()["entries"]
    turns = {e["payload"].get("turn_id") for e in entries}
    assert t1 in turns and own in turns and t2 not in turns
    for e in entries:
        assert e["actor"] == "manager_a1" or e["payload"]["output"]["store_id"] == "A-CH1"
