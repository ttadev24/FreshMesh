import datetime as dt
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from api.chat_quota import ChatQuota, client_ip
from api.config import Settings
from api.main import create_app
from tests.agent.fake_llm import PlannedFakeClient
from tests.api.conftest import assert_error, login, make_settings


def _quota(tmp_path, per_ip=2, global_=0, day=dt.date(2026, 10, 16)):
    clock = {"day": day}
    return ChatQuota(tmp_path / "usage.sqlite", per_ip, global_, salt="s", today=lambda: clock["day"]), clock


def test_per_ip_cap_refuses_after_limit_and_other_ips_continue(tmp_path):
    q, _ = _quota(tmp_path, per_ip=2)
    assert q.consume("1.1.1.1").allowed and q.consume("1.1.1.1").allowed
    refused = q.consume("1.1.1.1")
    assert not refused.allowed and refused.scope == "ip" and refused.limit == 2
    assert "2 lượt" in refused.message_vi()
    assert q.consume("2.2.2.2").allowed


def test_global_cap_counts_every_ip(tmp_path):
    q, _ = _quota(tmp_path, per_ip=10, global_=3)
    assert all(q.consume(ip).allowed for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"))
    refused = q.consume("4.4.4.4")
    assert not refused.allowed and refused.scope == "global"


def test_refused_turn_is_not_counted_and_new_day_resets(tmp_path):
    q, clock = _quota(tmp_path, per_ip=1, global_=2)
    assert q.consume("1.1.1.1").allowed
    assert not q.consume("1.1.1.1").allowed  # refused: must not use up the global budget
    assert q.consume("2.2.2.2").allowed
    clock["day"] = dt.date(2026, 10, 17)
    assert q.consume("1.1.1.1").allowed


def test_counts_survive_a_new_instance_and_deleting_the_file_resets(tmp_path):
    q, _ = _quota(tmp_path, per_ip=1)
    assert q.consume("1.1.1.1").allowed
    q2, _ = _quota(tmp_path, per_ip=1)
    assert not q2.consume("1.1.1.1").allowed
    (tmp_path / "usage.sqlite").unlink()  # reset while the app runs: the table is recreated, no 500
    assert q2.consume("1.1.1.1").allowed


def test_ipv6_is_grouped_by_64_and_raw_addresses_are_not_stored(tmp_path):
    q, _ = _quota(tmp_path, per_ip=1)
    assert q.consume("2001:db8:1:2::a").allowed
    assert not q.consume("2001:db8:1:2::b").allowed  # same /64
    assert q.consume("2001:db8:1:3::a").allowed
    keys = [r[0] for r in sqlite3.connect(tmp_path / "usage.sqlite").execute("SELECT key FROM chat_usage")]
    assert all("2001" not in k for k in keys)


def test_zero_disables_quota_and_writes_nothing_and_negative_is_rejected(tmp_path):
    q, _ = _quota(tmp_path, per_ip=0, global_=0)
    assert not q.enabled
    assert all(q.consume("1.1.1.1").allowed for _ in range(50))
    assert not (tmp_path / "usage.sqlite").exists()
    with pytest.raises(ValueError):
        ChatQuota(tmp_path / "x.sqlite", -1, 0)


def test_concurrent_turns_never_exceed_the_cap(tmp_path):
    q, _ = _quota(tmp_path, per_ip=0, global_=5)
    results: list[bool] = []
    lock = threading.Lock()

    def worker():
        ok = q.consume("1.1.1.1").allowed
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 5


def test_client_ip_uses_rightmost_forwarded_hop_only_behind_loopback():
    xff = {"x-forwarded-for": "198.51.100.1, 203.0.113.7, 127.0.0.1"}
    assert client_ip("127.0.0.1", xff) == "203.0.113.7"
    assert client_ip("::1", {"x-forwarded-for": "203.0.113.7:51234"}) == "203.0.113.7"
    assert client_ip("198.51.100.9", xff) == "198.51.100.9"  # direct client: headers ignored
    assert client_ip("::1", {"x-real-ip": "198.51.100.2"}) == "::1"  # X-Real-IP is not trusted
    assert client_ip("127.0.0.1", {"x-forwarded-for": "not-an-ip"}) == "127.0.0.1"
    assert client_ip(None, {}) == "unknown"


def test_quota_settings_reject_negative_and_treat_empty_as_default(monkeypatch):
    monkeypatch.setenv("FRESHMESH_ALLOW_DEV_SECRET", "1")
    monkeypatch.setenv("FRESHMESH_CHAT_PER_IP_DAILY", "")
    assert Settings().chat_per_ip_daily == 20
    monkeypatch.setenv("FRESHMESH_CHAT_GLOBAL_DAILY", "-5")
    with pytest.raises(RuntimeError):
        Settings()


def test_chat_endpoint_returns_429_and_503_costs_no_turn(data_dir, fake_solver, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    usage = data_dir / "usage.sqlite"
    try:
        no_llm = create_app(make_settings(data_dir, tmp_path / "c1", chat_per_ip_daily=2), solver=fake_solver)
        with TestClient(no_llm) as c:
            headers = login(c, "owner_a")
            for _ in range(3):  # no key: 503 every time, nothing counted
                assert_error(
                    c.post("/api/agent/chat", json={"message": "Xin chào"}, headers=headers), 503, "llm_unavailable"
                )
        app = create_app(
            make_settings(data_dir, tmp_path / "c2", chat_per_ip_daily=2),
            solver=fake_solver,
            llm_client_factory=lambda: PlannedFakeClient([]),
        )
        with TestClient(app) as c:
            headers = login(c, "owner_a")
            assert c.get("/api/health").json()["chat_quota"] == {"per_ip_daily": 2, "global_daily": 0}
            for _ in range(2):
                r = c.post("/api/agent/chat", json={"message": "Xin chào"}, headers=headers)
                assert r.status_code == 200, r.text
            err = assert_error(
                c.post("/api/agent/chat", json={"message": "Xin chào"}, headers=headers), 429, "chat_quota_exceeded"
            )
            assert "0:00" in err["message_vi"]
    finally:
        usage.unlink(missing_ok=True)
