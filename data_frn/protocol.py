"""Pre-registered protocol ``frn-v1`` (``docs/experiments/frn-protocol.md``) and its amendments (``frn-v1.1``,
written after the v1 results): every FRN experiment refuses to run without its protocol file and stamps its
results with the protocol version and the file's SHA-256."""

from __future__ import annotations

import hashlib
from pathlib import Path

PROTOCOL_ID = "frn-v1"
PROTOCOL_FILE = "frn-protocol.md"
PROTOCOL_FILES = {PROTOCOL_ID: PROTOCOL_FILE, "frn-v1.1": "frn-protocol-v1.1.md", "frn-v1.2": "frn-protocol-v1.2.md"}


def require_protocol(docs_dir: Path | str, version: str = PROTOCOL_ID) -> str:
    path = Path(docs_dir) / PROTOCOL_FILES[version]
    if not path.exists():
        raise FileNotFoundError(f"pre-registered protocol {path} missing: write and commit it before any run")
    data = path.read_bytes()
    if f"`{version}`".encode() not in data:
        raise ValueError(f"{path} does not declare protocol version {version}")
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def stamp(docs_dir: Path | str, version: str = PROTOCOL_ID) -> dict[str, str]:
    """Fields every result row carries."""
    return {"protocol": version, "protocol_sha256": require_protocol(docs_dir, version)}
