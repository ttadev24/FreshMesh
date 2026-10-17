"""Daily chat quotas per client address and for the whole site.

Demo accounts are shared by everyone given the credentials, so a per-user cap would be meaningless: the cost
guard is a per-address cap plus a site-wide cap per Vietnamese calendar day. Counts live in SQLite
(``<data_dir>/usage.sqlite``, mode 0600) so a restart does not reset them. Only the day, a keyed hash of the client address (IPv6 grouped by /64) and a counter are stored; rows older than
``KEEP_DAYS`` are deleted. Deleting the file resets every count (it is recreated on the next turn).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import ipaddress
import logging
import os
import sqlite3
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Vietnam is UTC+7 all year (no DST); a fixed offset avoids needing the IANA tz database on Windows.
VN_TZ = dt.timezone(dt.timedelta(hours=7), "ICT")
KEEP_DAYS = 30
GLOBAL_KEY = "global"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_usage (
    day TEXT NOT NULL,
    key TEXT NOT NULL,
    n INTEGER NOT NULL,
    PRIMARY KEY (day, key)
)
"""


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    scope: str | None = None  # "ip" or "global" when refused
    limit: int = 0

    def message_vi(self) -> str:
        if self.scope == "global":
            return (
                f"Bản demo đã dùng hết {self.limit} lượt hỏi trợ lý của hôm nay cho toàn hệ thống. "
                "Hạn mức đặt lại lúc 0:00 (giờ Việt Nam). Các bảng điều khiển vẫn dùng được bình thường."
            )
        return (
            f"Bạn đã dùng hết {self.limit} lượt hỏi trợ lý hôm nay. Hạn mức đặt lại lúc 0:00 (giờ Việt Nam). "
            "Các bảng điều khiển vẫn dùng được bình thường."
        )


def _today_vn() -> dt.date:
    return dt.datetime.now(VN_TZ).date()


def _ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    value = value.strip().strip("[]")
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        host, sep, port = value.rpartition(":")  # "1.2.3.4:5678"
        if sep and port.isdigit() and host.count(":") == 0:
            return _ip(host)
        return None


_warned_no_forward = False


def client_ip(peer: str | None, headers: Mapping[str, str]) -> str:
    """Client address for quota keys.

    In production uvicorn (``proxy_headers``, trusting 127.0.0.1) has already replaced the loopback peer by
    the address Caddy put in ``X-Forwarded-For`` (Caddy overwrites the header for direct clients, and the
    Next.js rewrite proxy does not append to it). When the peer is still loopback (e.g. Next connected over
    ``::1``), the same rule is applied here: the rightmost non-loopback address of ``X-Forwarded-For``."""
    global _warned_no_forward
    peer_ip = _ip(peer or "")
    if peer_ip is None:
        return peer or "unknown"
    if not peer_ip.is_loopback:
        return str(peer_ip)
    for raw in reversed((headers.get("x-forwarded-for") or "").split(",")):
        hop = _ip(raw)
        if hop is not None and not hop.is_loopback:
            return str(hop)
    if not _warned_no_forward:
        _warned_no_forward = True
        log.warning(
            "chat quota: loopback peer without a forwarded client address; all such turns share one bucket"
        )
    return str(peer_ip)


def _bucket(ip: str) -> str:
    """IPv6 clients are grouped by /64 (one host can rotate through its whole /64)."""
    addr = _ip(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is None:
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr) if addr is not None else ip


class ChatQuota:
    """``consume(ip)`` checks and counts one chat turn atomically. A limit of 0 disables that cap."""

    def __init__(
        self,
        db_path: Path,
        per_ip_daily: int,
        global_daily: int,
        *,
        salt: str = "",
        today: Callable[[], dt.date] = _today_vn,
    ):
        if per_ip_daily < 0 or global_daily < 0:
            raise ValueError("chat quotas must be >= 0 (0 disables a cap)")
        self.db_path = Path(db_path)
        self.per_ip_daily = int(per_ip_daily)
        self.global_daily = int(global_daily)
        self._salt = salt.encode("utf-8")
        self._today = today
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.per_ip_daily > 0 or self.global_daily > 0

    def _key(self, ip: str) -> str:
        digest = hmac.new(self._salt, _bucket(ip).encode("utf-8"), hashlib.sha256).hexdigest()
        return f"ip:{digest[:24]}"

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        con.execute(_SCHEMA)  # no-op when present; recreates the table if the file was deleted
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass
        return con

    def consume(self, ip: str) -> QuotaDecision:
        if not self.enabled:
            return QuotaDecision(True)
        day = self._today().isoformat()
        ip_key = self._key(ip)
        with self._lock:
            con = self._connect()
            try:
                con.execute("BEGIN IMMEDIATE")
                rows = con.execute(
                    "SELECT key, n FROM chat_usage WHERE day = ? AND key IN (?, ?)", (day, GLOBAL_KEY, ip_key)
                ).fetchall()
                counts = dict(rows)
                if self.global_daily and counts.get(GLOBAL_KEY, 0) >= self.global_daily:
                    con.execute("ROLLBACK")
                    return QuotaDecision(False, "global", self.global_daily)
                if self.per_ip_daily and counts.get(ip_key, 0) >= self.per_ip_daily:
                    con.execute("ROLLBACK")
                    return QuotaDecision(False, "ip", self.per_ip_daily)
                con.executemany(
                    "INSERT INTO chat_usage (day, key, n) VALUES (?, ?, 1) "
                    "ON CONFLICT (day, key) DO UPDATE SET n = n + 1",
                    [(day, GLOBAL_KEY), (day, ip_key)],
                )
                cutoff = (dt.date.fromisoformat(day) - dt.timedelta(days=KEEP_DAYS)).isoformat()
                con.execute("DELETE FROM chat_usage WHERE day < ?", (cutoff,))
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
            finally:
                con.close()
        return QuotaDecision(True)
