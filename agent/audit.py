"""Append-only decision history (``audit_log`` table of the per-chain DB).

Events: ``command`` (user message), ``plan``, ``tool_call`` (input + redacted output), ``answer``
(with unverified numbers and created drafts), ``approval`` / ``rejection`` (written by the API when a
human decides on a draft). Each agent-turn payload carries ``turn_id`` so the "Lịch sử quyết định" tab
can group a turn. UPDATE/DELETE are blocked by triggers.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AUDIT_DDL = (
    "CREATE TABLE IF NOT EXISTS audit_log(audit_id INTEGER PRIMARY KEY AUTOINCREMENT, chain_id TEXT, "
    "ts TEXT, actor TEXT, event TEXT, payload_json TEXT)"
)
_TRIGGERS = (
    "CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log "
    "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log "
    "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END",
)
EVENTS = frozenset({"command", "plan", "tool_call", "answer", "approval", "rejection"})


@dataclass(frozen=True)
class AuditEntry:
    audit_id: int
    chain_id: str
    ts: str
    actor: str
    event: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "chain_id": self.chain_id,
            "ts": self.ts,
            "actor": self.actor,
            "event": self.event,
            "payload": self.payload,
        }


_INITIALISED: set[tuple[str, int, int]] = set()  # (path, st_dev, st_ino) of DB files with schema + triggers
_INIT_LOCK = threading.Lock()


def _file_key(path: Path) -> tuple[str, int, int] | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return str(path.resolve()), st.st_dev, st.st_ino


class AuditLog:
    def __init__(self, db_path: Path | str, *, clock: Callable[[], datetime] | None = None):
        self.db_path = Path(db_path)
        self._clock = clock or (lambda: datetime.now(UTC))
        # The schema/trigger DDL runs once per DB file and process (the API builds an AuditLog per request);
        # a file replaced in place (new inode, e.g. bootstrap) is initialised again.
        key = _file_key(self.db_path)
        if key is not None and key in _INITIALISED:
            return
        with _INIT_LOCK:
            con = self._connect()
            try:
                with con:
                    con.execute(AUDIT_DDL)
                    for ddl in _TRIGGERS:
                        con.execute(ddl)
            finally:
                con.close()
            key = _file_key(self.db_path)
            if key is not None:
                _INITIALISED.add(key)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def append(self, chain_id: str, actor: str, event: str, payload: dict[str, Any]) -> int:
        if event not in EVENTS:
            raise ValueError(f"unknown audit event {event!r}")
        body = json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)
        con = self._connect()
        try:
            with con:
                cur = con.execute(
                    "INSERT INTO audit_log(chain_id, ts, actor, event, payload_json) VALUES (?,?,?,?,?)",
                    (chain_id, self._clock().isoformat(), actor, event, body),
                )
            return int(cur.lastrowid or 0)
        finally:
            con.close()

    def log_command(self, chain_id: str, actor: str, turn_id: str, message: str) -> int:
        return self.append(chain_id, actor, "command", {"turn_id": turn_id, "message": message})

    def log_plan(self, chain_id: str, actor: str, turn_id: str, plan_vi: str, tools: list[str]) -> int:
        return self.append(chain_id, actor, "plan", {"turn_id": turn_id, "plan_vi": plan_vi, "tools": tools})

    def log_tool_call(
        self,
        chain_id: str,
        actor: str,
        turn_id: str,
        tool: str,
        tool_input: Any,
        output: Any,
        error: str | None,
    ) -> int:
        return self.append(
            chain_id,
            actor,
            "tool_call",
            {"turn_id": turn_id, "tool": tool, "input": tool_input, "output": output, "error": error},
        )

    def log_answer(
        self, chain_id: str, actor: str, turn_id: str, text: str, unverified: list[str], drafts: list[str]
    ) -> int:
        return self.append(
            chain_id,
            actor,
            "answer",
            {"turn_id": turn_id, "text": text, "unverified": unverified, "drafts": drafts},
        )

    def log_decision(self, chain_id: str, actor: str, draft_id: str, decision: str, *, note: str = "") -> int:
        events = {"approved": "approval", "rejected": "rejection"}
        if decision not in events:
            raise ValueError("decision must be 'approved' or 'rejected'")
        return self.append(chain_id, actor, events[decision], {"draft_id": draft_id, "note": note})

    def entries(self, chain_id: str, *, limit: int = 200, event: str | None = None) -> list[AuditEntry]:
        """Newest first, for the 'Lịch sử quyết định' tab."""
        sql = "SELECT audit_id, chain_id, ts, actor, event, payload_json FROM audit_log WHERE chain_id = ?"
        params: list[Any] = [chain_id]
        if event is not None:
            sql += " AND event = ?"
            params.append(event)
        sql += " ORDER BY audit_id DESC LIMIT ?"
        params.append(int(limit))
        return self._query(sql, params)

    def turn(self, chain_id: str, turn_id: str) -> list[AuditEntry]:
        """All entries of one agent turn, oldest first."""
        sql = (
            "SELECT audit_id, chain_id, ts, actor, event, payload_json FROM audit_log "
            "WHERE chain_id = ? AND json_extract(payload_json, '$.turn_id') = ? ORDER BY audit_id"
        )
        return self._query(sql, [chain_id, turn_id])

    def _query(self, sql: str, params: list[Any]) -> list[AuditEntry]:
        con = self._connect()
        try:
            rows = con.execute(sql, params).fetchall()
        finally:
            con.close()
        return [AuditEntry(r[0], r[1], r[2], r[3], r[4], json.loads(r[5] or "{}")) for r in rows]
