"""CLI for the decision flows, using the same service layer as the API (``api.services``).

    uv run python -m decision.cli flow1 --chain CHAIN_A --store A-CH1 --items rau,thit

Prints the Vietnamese flow-1 report: forecast P10/P50/P90 → 3 plans (total, % waste, % stockout),
confidence, assumptions and the data sources used. Nothing is ordered: the report ends with what to approve.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from api.errors import ApiError
from api.repo import resolve_store_id
from api.routing_service import RoutingService
from api.services import Services, fmt_flow1_text
from data_sim import CHAIN_IDS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="decision.cli", description="FreshMesh — luồng ra quyết định")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("flow1", help="nhập hàng cho ngày mai: dự báo → 3 phương án")
    p1.add_argument("--chain", required=True, choices=CHAIN_IDS)
    p1.add_argument("--store", required=True, help="mã cửa hàng, ví dụ A-CH1 hoặc CH1")
    p1.add_argument("--items", default="rau,thit", help="nhóm hàng hoặc mã SKU, cách nhau bằng dấu phẩy")
    p1.add_argument("--horizon", type=int, default=1)
    p1.add_argument("--budget", type=float, default=None, help="ngân sách (VND)")
    p1.add_argument("--data", type=Path, default=Path("data"))
    args = parser.parse_args(argv)

    services = Services(args.data, RoutingService(args.data / "cache", None), auto_train=True)
    try:
        repo = services.repo(args.chain)
        store_id = resolve_store_id(repo, args.store, default=None)
        items = [x.strip() for x in args.items.split(",") if x.strip()]
        sku_ids = [x for x in items if x.upper().startswith("SKU_")]
        categories = [x for x in items if x not in sku_ids]
        skus = repo.select_skus(sku_ids, categories)
        result = services.inventory_plan(
            args.chain, store_id, skus, horizon_days=args.horizon, budget_vnd=args.budget
        )
    except ApiError as exc:
        print(f"Lỗi: {exc.message_vi}", file=sys.stderr)
        return 1
    print(fmt_flow1_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
