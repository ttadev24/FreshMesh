"""One big, plain number per evidence item (``impact``: ``value_vi``, ``label_vi``, optional ``before_vi`` /
``after_vi`` / ``second_vi``), computed from the same report numbers as the item's headline — never typed by
hand. FAIL items get one too: the number that shows what failed."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _n(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}".replace(".", ",").replace("-", "−")


def _signed(x: float, nd: int = 1) -> str:
    return ("+" if x > 0 else "") + _n(x, nd)


def _frn_forecast(n: dict) -> dict:
    t = n["test"]
    return {"value_vi": f"{_n(t['mlp']['wape'], 3)} vs {_n(t['empirical_q28']['wape'], 3)}",
            "label_vi": "sai số dự báo (WAPE) trên dữ liệu thật: MLP chưa thắng phân vị 28 ngày"}  # fmt: skip


def _frn_inventory(n: dict) -> dict:
    level = next(r for r in n["shelf_lives"]["2"]["levels"] if r["stockout"] == 10.0)
    return {"value_vi": f"{_signed(level['diff'], 2)} điểm",
            "label_vi": "hàng bỏ so với baseline tối ưu, cùng mức hết hàng 10% (dữ liệu thật)"}  # fmt: skip


def _sim30(n: dict) -> dict:
    v1 = [c["verdicts"]["sim30-v1"] for c in n["chains"].values() if "sim30-v1" in c["verdicts"]]
    so = sorted(v["stockout_diff_pp"] for v in v1)
    wa = sorted(v["waste_diff_pp"] for v in v1)
    return {"value_vi": f"{_n(so[-1], 0)}…{_n(so[0], 0)} điểm",
            "label_vi": f"hết hàng giảm, nhưng hàng bỏ tăng {_signed(wa[0], 0)}…{_signed(wa[-1], 0)} điểm % "
                        "(30 ngày mô phỏng, chính sách đăng ký trước)"}  # fmt: skip


def _routing(n: dict) -> dict:
    base = n["methods"]["one_trip_per_order"]
    fixed = (n.get("r1_v12") or {}).get("1.3")
    km = fixed["km"]["paco"] if fixed else n["methods"]["paco"]["total_km"]
    out = {
        "value_vi": f"−{round(100 * (1 - km / base['total_km']))}% km",
        "before_vi": f"{base['total_vehicles']} chuyến, {_n(base['total_km'])} km",
        "after_vi": f"{_n(km)} km" + (f", {fixed['late_stops']['paco']} điểm trễ" if fixed else ""),
        "label_vi": f"{n['orders']} đơn, {n['batches']} đợt, so với mỗi đơn một chuyến"
                    + ("; bộ giải đã sửa lỗi thời gian giao" if fixed else ""),
    }  # fmt: skip
    if fixed:
        out["second_vi"] = (f"so với chia vùng thủ công −{_n(fixed['km_saving_pct'])}% km, "
                            f"{fixed['late_stops']['paco']} điểm trễ")  # fmt: skip
    return out


def _federated(n: dict) -> dict:
    m = n["metrics"]
    return {"value_vi": f"−{_n(n['improvement_vs_local']['new_store'])}%",
            "before_vi": _n(m["local"]["new_store_wape"], 4), "after_vi": _n(m["fl"]["new_store_wape"], 4),
            "label_vi": "sai số dự báo cửa hàng mới, dữ liệu mô phỏng 3 chuỗi"}  # fmt: skip


def _frn_federated(n: dict) -> dict:
    new = n["metrics"]["new_store"]
    lo, fl = new["local"]["wape"], new["fl"]["wape"]
    return {"value_vi": f"{_signed(100 * (fl - lo) / lo, 0)}%", "before_vi": _n(lo, 3), "after_vi": _n(fl, 3),
            "label_vi": "sai số dự báo (WAPE) cửa hàng mới, 18 thành phố dữ liệu thật"}  # fmt: skip


def _drivers(n: dict) -> dict:
    mae = sorted(n["weekday_mae_pp"].values())
    return {"value_vi": f"{_n(mae[0])}–{_n(mae[-1])} điểm",
            "label_vi": "sai số giải thích theo thứ trong tuần so với sự thật mô phỏng"}  # fmt: skip


def _elasticity(n: dict) -> dict:
    where = "trong" if n["inside_ai_range"] else "ngoài"
    label = f"trung vị co giãn giá, {len(n['categories'])} nhóm hàng, {where} khoảng AI đề xuất"
    return {"value_vi": _n(n["median"], 2), "label_vi": label}


IMPACT: dict[str, Callable[[dict], dict]] = {
    "frn_forecast": _frn_forecast, "frn_inventory": _frn_inventory, "sim30": _sim30, "routing": _routing,
    "federated": _federated, "frn_federated": _frn_federated, "drivers": _drivers, "elasticity": _elasticity,
}  # fmt: skip


def impact(item_id: str, numbers: dict[str, Any]) -> dict | None:
    """The item's impact block, or None when its report has not been run."""
    fn = IMPACT.get(item_id)
    return fn(numbers) if fn and numbers else None
