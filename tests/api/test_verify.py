import api.verify as verify


def test_verify_run_passes_every_case_quickly(client, owner_a):
    r = client.get("/api/verify/run", headers=owner_a)
    assert r.status_code == 200, r.text
    body = r.json()
    failed = [c for c in body["cases"] if not c["pass"]]
    assert failed == [], failed
    assert body["passed"] == body["total"] == 12
    assert body["duration_ms"] < 5000
    assert all(c["title_vi"] and c["input_vi"] and c["expected_vi"] and c["actual_vi"] for c in body["cases"])


def test_verify_needs_a_login(client):
    assert client.get("/api/verify/run").status_code == 401


def test_a_broken_check_is_reported_as_failed_not_hidden(data_dir, monkeypatch):
    def boom():
        raise RuntimeError("guard missing")

    original = verify.cases

    def patched(d, policy=None):
        return [*original(d, policy)[:-1], ("undo_window", "t", "i", "e", boom)]

    monkeypatch.setattr(verify, "cases", patched)
    out = verify.run_all(data_dir)
    assert out["passed"] == 11 and out["cases"][-1]["pass"] is False
    assert "RuntimeError" in out["cases"][-1]["actual_vi"]


def test_the_checks_would_fail_if_a_guard_were_removed(data_dir, monkeypatch):
    """The cases test the real rules: disabling the SQL guard makes its case fail."""
    monkeypatch.setattr(verify, "validate_readonly_sql", lambda sql, chain: sql)
    out = verify.run_all(data_dir)
    sql_case = next(c for c in out["cases"] if c["id"] == "sql_delete_blocked")
    assert sql_case["pass"] is False


def test_escalation_checks_follow_the_live_policy(data_dir, monkeypatch):
    """Switching the manager's limit off makes the authority case fail: the case tests the deployed rule."""
    from api.escalation import ApprovalPolicy

    out = verify.run_all(data_dir, ApprovalPolicy(manager_order_limit_vnd=0))
    case = next(c for c in out["cases"] if c["id"] == "authority_needs_owner")
    assert case["pass"] is False and "được tự duyệt" in case["actual_vi"]
