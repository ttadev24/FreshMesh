"""``POST /api/sales/import/preview`` and the sample POS file (``GET /api/sales/import/sample``): what a
store's sales file would add, checked against the chain DB and against FreshMesh's own forecast; nothing is
written.
The sample is labelled simulated: the store's last 6 days from the chain DB plus the next day drawn from the
same demand process the data came from (``simulation.demand.future_demand``, seed 1001)."""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Any

from api.errors import ApiError
from api.sales_import import parse_sales
from data_sim import SIM_AS_OF
from decision.text import pct

FORECAST_DAYS = 7
SAMPLE_SEED = 1001
SAMPLE_NOTE_VI = "File mẫu mô phỏng (định dạng KiotViet): 6 ngày từ dữ liệu chuỗi + ngày mai từ bộ mô phỏng."


def preview(services: Any, chain_id: str, store_id: str, text: str) -> dict[str, Any]:
    repo = services.repo(chain_id)
    store = repo.store(store_id)
    skus = repo.sku_map()
    parsed = parse_sales(text, {k: v.name for k, v in skus.items()})
    if not parsed.totals:
        raise ApiError(422, "no_sales_rows", "File không có dòng bán hàng nào khớp mặt hàng của chuỗi.")
    days = sorted({d for _, d in parsed.totals})
    with repo.read() as con:
        held = {
            (r[0], dt.date.fromisoformat(r[1])): r[2]
            for r in con.execute(
                "SELECT sku_id, date, units FROM daily_sales WHERE store_id = ? AND date BETWEEN ? AND ?",
                (store_id, days[0].isoformat(), days[-1].isoformat()),
            )
        }
        first = con.execute("SELECT MIN(date) FROM daily_sales WHERE store_id = ?", (store_id,)).fetchone()[0]
    last_day = SIM_AS_OF + dt.timedelta(days=FORECAST_DAYS)
    past = {k: v for k, v in parsed.totals.items() if k[1] <= SIM_AS_OF}
    ahead = {k: v for k, v in parsed.totals.items() if SIM_AS_OF < k[1] <= last_day}
    compared = [k for k in past if k in held]
    differ = [
        {"sku_id": k[0], "sku_name": skus[k[0]].name, "date": k[1].isoformat(), "file_units": past[k],
         "freshmesh_units": held[k]}
        for k in sorted(compared) if abs(past[k] - held[k]) >= 0.5
    ]  # fmt: skip
    new_days = sorted({d for (sku, d) in past if (sku, d) not in held})
    before = _days_before(set(new_days), first)
    check = _forecast_check(services, chain_id, store_id, skus, ahead)
    inside = sum(c["inside"] for c in check)
    parts = [
        f"Đọc {parsed.rows_read} dòng: {len(parsed.totals)} cặp mặt hàng × ngày, "
        f"{days[0].strftime('%d/%m')}–{days[-1].strftime('%d/%m/%Y')}.",
        f"Khớp {len(compared) - len(differ)}/{len(compared)} với số bán FreshMesh đang có."
        if compared else "",
        f"{len(before)} ngày trước ngày đầu tiên FreshMesh có: cửa hàng sẽ có "
        f"{store.history_days + len(before)} ngày lịch sử nếu được duyệt nhập." if before else "",
        f"Ngày sau dữ liệu: số bán trong file nằm trong khoảng dự báo P10–P90 ở {inside}/{len(check)} dòng "
        f"({pct(100 * inside / len(check))})." if check else "",
    ]  # fmt: skip
    return {
        "store_id": store_id,
        "store_name": store.name,
        "rows_read": parsed.rows_read,
        "pairs": len(parsed.totals),
        "first_day": days[0].isoformat(),
        "last_day": days[-1].isoformat(),
        "compared": len(compared),
        "differences": differ[:50],
        "new_days": [d.isoformat() for d in new_days],
        "history_days_added": len(before),
        "forecast_check": check,
        "forecast_coverage_pct": round(100 * inside / len(check), 1) if check else None,
        "unknown_products": parsed.unknown_products,
        "issues_vi": parsed.issues_vi,
        "summary_vi": " ".join(p for p in parts if p),
        "saved": False,  # preview only: nothing is written to the chain DB
    }


def _days_before(days: set[dt.date], first: str | None) -> list[dt.date]:
    """New days that extend the store's history backwards without a gap (stray old dates do not count)."""
    if first is None:
        return sorted(days)
    out, d = [], dt.date.fromisoformat(first) - dt.timedelta(days=1)
    while d in days:
        out.append(d)
        d -= dt.timedelta(days=1)
    return sorted(out)


def _forecast_check(services: Any, chain_id: str, store_id: str, skus: dict, ahead: dict) -> list[dict]:
    if not ahead:
        return []
    horizon = max((d - SIM_AS_OF).days for _, d in ahead)
    selected = [skus[s] for s in sorted({s for s, _ in ahead})]
    rows = services.forecast(chain_id, store_id, selected, horizon)["rows"]
    out = []
    for r in rows:
        k = (r["sku_id"], dt.date.fromisoformat(r["date"]))
        if k in ahead:
            actual = ahead[k]
            out.append({"sku_id": r["sku_id"], "sku_name": r["sku_name"], "date": r["date"], "actual": actual,
                        "p10": r["p10"], "p50": r["p50"], "p90": r["p90"],
                        "inside": bool(r["p10"] <= actual <= r["p90"])})  # fmt: skip
    return out


@lru_cache(maxsize=4)
def _tomorrow(chain_id: str) -> dict[tuple[str, str], int]:
    from simulation.demand import future_demand, recover_chain_process

    fd = future_demand(recover_chain_process(chain_id), SAMPLE_SEED, n_days=1)
    pairs = ((i, s, j, k) for i, s in enumerate(fd.store_ids) for j, k in enumerate(fd.sku_ids))
    return {(s, k): int(fd.units[i, j, 0]) for i, s, j, k in pairs}


def sample_csv(services: Any, chain_id: str, store_id: str) -> str:
    repo = services.repo(chain_id)
    repo.store(store_id)
    skus = repo.sku_map()
    first = (SIM_AS_OF - dt.timedelta(days=5)).isoformat()
    with repo.read() as con:
        rows = con.execute(
            "SELECT date, sku_id, units FROM daily_sales WHERE store_id = ? AND date >= ? "
            "ORDER BY date, sku_id",
            (store_id, first),
        ).fetchall()
    tomorrow = (SIM_AS_OF + dt.timedelta(days=1)).isoformat()
    nxt = sorted(_tomorrow(chain_id).items())
    rows += [(tomorrow, k, u) for (s, k), u in nxt if s == store_id and k in skus]
    codes = {k: f"SP{i + 1:04d}" for i, k in enumerate(sorted(skus))}  # POS codes differ from FreshMesh's
    lines = ["Ngày,Mã hàng,Tên hàng,Số lượng"]
    for day, sku, units in rows:
        d = dt.date.fromisoformat(day).strftime("%d/%m/%Y")
        lines.append(f'{d},{codes[sku]},"{skus[sku].name}",{units}')
    return "\n".join(lines) + "\n"
