import sqlite3
from datetime import UTC, datetime

import pytest

from agent.audit import AUDIT_DDL, AuditLog


def _clock():
    return datetime(2026, 10, 1, 8, 0, tzinfo=UTC)


def test_creates_table_with_contract_schema(tmp_path):
    db = tmp_path / "a.sqlite"
    AuditLog(db, clock=_clock)
    con = sqlite3.connect(db)
    cols = [(r[1], r[2]) for r in con.execute("PRAGMA table_info(audit_log)")]
    assert cols == [
        ("audit_id", "INTEGER"),
        ("chain_id", "TEXT"),
        ("ts", "TEXT"),
        ("actor", "TEXT"),
        ("event", "TEXT"),
        ("payload_json", "TEXT"),
    ]
    assert "AUTOINCREMENT" in AUDIT_DDL


def test_existing_table_is_reused(tmp_path):
    db = tmp_path / "a.sqlite"
    con = sqlite3.connect(db)
    con.execute(AUDIT_DDL)
    con.execute(
        "INSERT INTO audit_log(chain_id, ts, actor, event, payload_json) VALUES ('CHAIN_A','t','x','command','{}')"
    )
    con.commit()
    con.close()
    log = AuditLog(db, clock=_clock)
    assert len(log.entries("CHAIN_A")) == 1


def test_records_turn_and_reads_back_grouped(tmp_path):
    log = AuditLog(tmp_path / "a.sqlite", clock=_clock)
    log.log_command("CHAIN_A", "owner_a", "t1", "Nhập rau cho mai?")
    log.log_plan("CHAIN_A", "owner_a", "t1", "Dự báo rồi lập phương án", ["forecast_demand"])
    log.log_tool_call("CHAIN_A", "owner_a", "t1", "forecast_demand", {"store_id": "A1"}, {"p50": 12.5}, None)
    log.log_answer("CHAIN_A", "owner_a", "t1", "**Đề xuất:** ...", ["1,3"], ["draft-1"])
    log.log_decision("CHAIN_A", "owner_a", "draft-1", "approved", note="ok")
    log.log_decision("CHAIN_A", "owner_a", "draft-2", "rejected")
    log.log_command("CHAIN_B", "owner_b", "t9", "khác")

    entries = log.entries("CHAIN_A")
    assert [e.event for e in entries] == ["rejection", "approval", "answer", "tool_call", "plan", "command"]
    assert all(e.chain_id == "CHAIN_A" for e in entries)
    tool = entries[3]
    assert tool.payload == {
        "turn_id": "t1",
        "tool": "forecast_demand",
        "input": {"store_id": "A1"},
        "output": {"p50": 12.5},
        "error": None,
    }
    assert tool.ts == "2026-10-01T08:00:00+00:00"
    assert [e.event for e in log.entries("CHAIN_A", event="approval")] == ["approval"]
    assert [e.event for e in log.turn("CHAIN_A", "t1")] == ["command", "plan", "tool_call", "answer"]
    assert len(log.entries("CHAIN_A", limit=2)) == 2
    assert log.entries("CHAIN_A")[0].to_dict()["payload"]["draft_id"] == "draft-2"


def test_rejects_unknown_event_and_bad_decision(tmp_path):
    log = AuditLog(tmp_path / "a.sqlite", clock=_clock)
    with pytest.raises(ValueError):
        log.append("CHAIN_A", "x", "hack", {})
    with pytest.raises(ValueError):
        log.log_decision("CHAIN_A", "x", "d1", "executed")


def test_append_only(tmp_path):
    db = tmp_path / "a.sqlite"
    log = AuditLog(db, clock=_clock)
    log.log_command("CHAIN_A", "owner_a", "t1", "x")
    assert not hasattr(log, "delete") and not hasattr(log, "update")
    con = sqlite3.connect(db)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE audit_log SET actor='y'")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM audit_log")


def test_schema_is_initialised_once_per_db_file(tmp_path, monkeypatch):
    """LOW-3: per-request AuditLog(path) must not re-run CREATE TABLE/TRIGGER on every request."""
    db = tmp_path / "once.sqlite"
    AuditLog(db, clock=_clock)
    calls = []
    original = AuditLog._connect

    def counting(self):
        calls.append(1)
        return original(self)

    monkeypatch.setattr(AuditLog, "_connect", counting)
    for _ in range(3):
        AuditLog(db, clock=_clock)
    assert calls == []
    monkeypatch.undo()
    # Another DB file still gets its schema and triggers.
    other = tmp_path / "other.sqlite"
    AuditLog(other, clock=_clock).append("CHAIN_A", "u", "command", {})
    con = sqlite3.connect(other)
    triggers = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    con.close()
    assert {"audit_log_no_update", "audit_log_no_delete"} <= triggers
