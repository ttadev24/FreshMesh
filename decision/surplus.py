"""Where will fresh stock be left over today? Ranks stores for flow 2 ("còn nhiều rau…") when the user
names no store, so markdown / transfer run where the surplus actually is.

Same basis as ``suggest_markdown`` in the API: lots expiring today, P50 demand of the day, and the share of
the day's sales already made before ``now`` (hourly profile of the store's area type).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SURPLUS_ASSUMPTIONS_VI = (
    "Dự kiến ế = số đơn vị thuộc lô hết hạn hôm nay trừ nhu cầu P50 của cả ngày, nếu không giảm giá "
    "và không điều chuyển.",
    "Còn trên kệ lúc này = lô hết hạn hôm nay trừ doanh số P50 trước giờ hiện tại, theo tỷ trọng doanh số "
    "theo giờ của loại khu vực.",
)


def units_left_now(expiring: int, p50_day: float, share_before: float) -> int:
    """Units of today's expiring lots still on the shelf at ``now``. Expected sales before ``now`` are rounded
    to 0.1 first, exactly as the markdown / transfer tools do, so every tool quotes the same figure."""
    return max(0, round(expiring - round(p50_day * share_before, 1)))


def rank_surplus_stores(
    stores: Sequence[tuple[str, str, float]],
    expiring_today: Mapping[tuple[str, str], int],
    p50_day: Mapping[tuple[str, str], float],
    sku_names: Mapping[str, str],
    *,
    top_items: int = 5,
) -> list[dict[str, Any]]:
    """``stores`` = (store_id, store_name, share of the day's sales before now). Returns every store, sorted
    by expected unsold units (desc), each with its ``top_items`` SKUs. Numbers are rounded once here so the
    agent can quote them verbatim."""
    out = []
    for store_id, store_name, share_before in stores:
        items = []
        for sku_id, sku_name in sku_names.items():
            expiring = int(expiring_today.get((store_id, sku_id), 0))
            p50 = p50_day.get((store_id, sku_id))
            if expiring <= 0 or p50 is None:
                continue
            left_now = units_left_now(expiring, p50, share_before)
            unsold = round(max(0.0, expiring - p50), 1)
            if left_now > 0:
                items.append(
                    {
                        "sku_id": sku_id,
                        "sku_name": sku_name,
                        "expiring_today_units": expiring,
                        "units_left_now": left_now,
                        "expected_unsold_units": unsold,
                    }
                )
        items.sort(key=lambda x: (-x["expected_unsold_units"], -x["units_left_now"], x["sku_id"]))
        out.append(
            {
                "store_id": store_id,
                "store_name": store_name,
                "expected_unsold_units": round(sum(x["expected_unsold_units"] for x in items), 1),
                "units_left_now": sum(x["units_left_now"] for x in items),
                "items": items[:top_items],
                "items_not_listed": max(0, len(items) - top_items),  # totals above include them
            }
        )
    out.sort(key=lambda s: (-s["expected_unsold_units"], -s["units_left_now"], s["store_id"]))
    return out
