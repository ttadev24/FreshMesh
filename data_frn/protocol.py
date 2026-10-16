"""Pre-registered protocol ``frn-v1`` (``docs/experiments/frn-protocol.md``): every FRN experiment refuses to
run without it and stamps its results with the protocol version and the file's SHA-256."""

from __future__ import annotations

import hashlib
from pathlib import Path

PROTOCOL_ID = "frn-v1"
PROTOCOL_FILE = "frn-protocol.md"


def require_protocol(docs_dir: Path | str) -> str:
    path = Path(docs_dir) / PROTOCOL_FILE
    if not path.exists():
        raise FileNotFoundError(f"pre-registered protocol {path} missing: write and commit it before any run")
    data = path.read_bytes()
    if f"`{PROTOCOL_ID}`".encode() not in data:
        raise ValueError(f"{path} does not declare protocol version {PROTOCOL_ID}")
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def stamp(docs_dir: Path | str) -> dict[str, str]:
    """Fields every result row carries."""
    return {"protocol": PROTOCOL_ID, "protocol_sha256": require_protocol(docs_dir)}
