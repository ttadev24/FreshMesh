"""``uv run --group bench python -m data_frn download|audit [--data data] [--docs docs/experiments]``."""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m data_frn", description=__doc__)
    parser.add_argument("command", choices=["download", "audit"])
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--docs", type=Path, default=Path("docs/experiments"))
    args = parser.parse_args(argv)
    if args.command == "download":
        from data_frn.download import ensure_files

        for split, path in ensure_files(args.data).items():
            print(f"{split}: {path} (sha256 verified)")
        return 0
    from data_frn.audit import audit, write_report

    print(write_report(audit(args.data), args.docs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
