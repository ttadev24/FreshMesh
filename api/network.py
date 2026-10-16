"""Network view (``GET /api/network``): the caller's stores, the rest of the FreshMesh network as anonymised
density cells, and what the federated model shares. Other chains are competitors: they appear only as
"Chuỗi khác N" with store counts on grid cells of at least ``K_MIN`` stores, never as identifiable points.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from api.errors import ApiError
from api.services import Services, fl_summary_payload
from data_sim import CHAIN_IDS
from decision.text import pct

K_MIN = 2  # a cell must hold at least this many stores
FINE, COARSE = 2, 1  # decimal places of lat/lng: ~1,1 km then ~11 km cells
STORE_FIELDS = ("store_id", "name", "lat", "lng", "area_type", "is_new")


def anonymous_cells(points: Sequence[tuple[float, float]], k_min: int = K_MIN) -> list[dict[str, Any]]:
    """Store counts on ~1.1 km cells; a store alone there moves to ~11 km cells; still alone → dropped."""
    fine = Counter((round(lat, FINE), round(lng, FINE)) for lat, lng in points)
    cells = [{"lat": a, "lng": b, "stores": n} for (a, b), n in fine.items() if n >= k_min]
    rest = [(lat, lng) for lat, lng in points if fine[(round(lat, FINE), round(lng, FINE))] < k_min]
    coarse = Counter((round(lat, COARSE), round(lng, COARSE)) for lat, lng in rest)
    cells += [{"lat": a, "lng": b, "stores": n} for (a, b), n in coarse.items() if n >= k_min]
    return sorted(cells, key=lambda c: (-c["stores"], c["lat"], c["lng"]))


def _federated(data_dir: Path) -> dict[str, Any]:
    base = {
        "method": "FedAvg + FedPer",
        "shares_vi": "Chỉ trọng số mô hình dự báo",
        "never_shares_vi": "Dữ liệu bán hàng, giá, tồn kho và khách hàng của từng chuỗi",
    }
    try:
        fl = fl_summary_payload(data_dir)
    except ApiError:
        missing = dict.fromkeys(("clients", "rounds", "dp", "evidence_vi"))
        return {**base, "model_ready": False, **missing}
    gain = fl.get("improvement_vs_local", {})
    wape, new = gain.get("wape"), gain.get("new_store")

    def verdict(x: float) -> str:
        return f"tốt hơn {pct(100 * x)}" if x > 0 else f"kém hơn {pct(-100 * x)}"

    evidence = (
        f"Trên dữ liệu thử nghiệm, so với mô hình riêng từng chuỗi, mô hình liên kết {verdict(wape)} WAPE "
        f"tổng thể và {verdict(new)} ở cửa hàng mới."
        if wape is not None and new is not None
        else None
    )
    return {
        **base,
        "model_ready": bool(fl.get("fl_model_deployed")),
        "clients": fl.get("chains_participating"),
        "rounds": fl.get("rounds"),
        "dp": fl.get("epsilon") is not None,
        "evidence_vi": evidence,
    }


def build_network(
    services: Services, data_dir: Path, chain_id: str, own_store_ids: Sequence[str] | None, flows_today: list
) -> dict[str, Any]:
    """``own_store_ids``: None for an owner (all stores), else the stores the caller may see."""
    repo = services.repo(chain_id)
    stores = [s for s in repo.stores() if own_store_ids is None or s.store_id in own_store_ids]
    others = []
    for i, other in enumerate((c for c in CHAIN_IDS if c != chain_id), start=1):
        try:
            points = [(s.lat, s.lng) for s in services.repo(other).stores()]
        except (ApiError, FileNotFoundError):
            continue
        cells = anonymous_cells(points)
        others.append({"label_vi": f"Chuỗi khác {i}", "stores": len(points), "cells": cells})
    return {
        "chain_id": chain_id,
        "chain_name": repo.chain_name(),
        "stores": [{k: s.to_dict()[k] for k in STORE_FIELDS} for s in stores],
        "network": {
            "chains": 1 + len(others),
            "stores_total": len(repo.stores()) + sum(o["stores"] for o in others),
            "others": others,
        },
        "federated": _federated(data_dir),
        "flows_today": [f for f in flows_today if own_store_ids is None or f["from"] in own_store_ids],
        **repo.provenance(("stores",)),
    }
