from pathlib import Path

import pytest

from data_frn.protocol import PROTOCOL_FILE, PROTOCOL_ID, require_protocol, stamp

DOCS = Path(__file__).resolve().parents[2] / "docs" / "experiments"


def test_committed_protocol_declares_the_version():
    assert stamp(DOCS)["protocol"] == PROTOCOL_ID
    assert len(stamp(DOCS)["protocol_sha256"]) == 64


def test_hash_ignores_line_endings_but_not_content(tmp_path):
    (tmp_path / PROTOCOL_FILE).write_bytes(f"# p\n`{PROTOCOL_ID}`\nthreshold 5%\n".encode())
    lf = require_protocol(tmp_path)
    (tmp_path / PROTOCOL_FILE).write_bytes(f"# p\r\n`{PROTOCOL_ID}`\r\nthreshold 5%\r\n".encode())
    assert require_protocol(tmp_path) == lf  # Windows checkout (core.autocrlf) gives the same hash
    (tmp_path / PROTOCOL_FILE).write_bytes(f"# p\n`{PROTOCOL_ID}`\nthreshold 6%\n".encode())
    assert require_protocol(tmp_path) != lf


def test_missing_or_undeclared_protocol_refuses_to_run(tmp_path):
    with pytest.raises(FileNotFoundError):
        require_protocol(tmp_path)
    (tmp_path / PROTOCOL_FILE).write_text("no version here", encoding="utf-8")
    with pytest.raises(ValueError):
        require_protocol(tmp_path)
