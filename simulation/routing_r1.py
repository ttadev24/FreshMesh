"""Criterion R1 of protocol frn-v1 §6: PACO vs the dispatcher-style ``zone_sweep`` on the 18 demo batches.
PASS iff, at detour factor 1,3, PACO's road km is lower than ``zone_sweep``'s in at least 14 of 18 batches
and PACO's total late stops are no more than ``zone_sweep``'s. Detour 1,58 (measured OSRM median) is a
sensitivity run reported next to it, without a verdict of its own."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from simulation import routing_bench

MIN_BATCHES = 14
DETOURS = (1.3, 1.58)


def verdict(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    ok = {(r["store_id"], r["method"]): r for r in rows if r["status"] == "ok"}
    stores = sorted({s for s, m in ok if m == "zone_sweep"} & {s for s, m in ok if m == "paco"})
    if not stores:
        return None
    km = {m: [float(ok[(s, m)]["road_km"]) for s in stores] for m in ("paco", "zone_sweep")}
    late = {m: sum(int(ok[(s, m)]["late_stops"]) for s in stores) for m in ("paco", "zone_sweep")}
    better = sum(p < z for p, z in zip(km["paco"], km["zone_sweep"], strict=True))
    total = {m: round(sum(v), 1) for m, v in km.items()}
    return {
        "batches": len(stores),
        "paco_shorter_batches": better,
        "km": total,
        "km_saving_pct": round(100 * (1 - total["paco"] / total["zone_sweep"]), 1) if total["zone_sweep"] else None,
        "late_stops": late,
        "pass": better >= MIN_BATCHES and late["paco"] <= late["zone_sweep"],
    }


def verdicts(docs_dir: Path) -> dict[str, Any]:
    """``{"1.3": verdict | None, "1.58": verdict | None}`` from the benchmark CSVs."""
    out = {}
    for d in DETOURS:
        rows = routing_bench.read_results(Path(docs_dir) / routing_bench.results_name(d))
        out[str(d)] = verdict(rows) if rows else None
    return out


def _f(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def markdown(r1: dict[str, Any]) -> str:
    primary = r1.get("1.3")
    if primary is None:
        return ""
    lines = ["", "## R1 — PACO so với điều phối chia vùng / vs dispatcher zones (frn-v1 §6)", "",
             "| Hệ số đường vòng | PACO ngắn hơn | Tổng km PACO | Tổng km chia vùng | Tiết kiệm | Trễ PACO | "
             "Trễ chia vùng |", "|---|---|---|---|---|---|---|"]  # fmt: skip
    for d, v in r1.items():
        if v is None:
            continue
        role = "chính" if d == "1.3" else "độ nhạy"
        saving = "—" if v["km_saving_pct"] is None else f"{_f(v['km_saving_pct'])}%"
        lines.append(
            f"| {d.replace('.', ',')} ({role}) | {v['paco_shorter_batches']}/{v['batches']} đợt | "
            f"{_f(v['km']['paco'])} | {_f(v['km']['zone_sweep'])} | {saving} | {v['late_stops']['paco']} | "
            f"{v['late_stops']['zone_sweep']} |"
        )
    result = "ĐẠT / PASS" if primary["pass"] else "KHÔNG ĐẠT / FAIL"
    lines += ["", f"**R1 {result}** — tiêu chí: PACO ngắn hơn ở ≥ {MIN_BATCHES}/18 đợt và tổng điểm trễ không "
              "nhiều hơn, ở hệ số 1,3. Chia vùng = cách điều phối viên làm tay: quét theo hướng quanh cửa hàng, "
              "đầy xe hoặc sắp trễ thì sang chuyến mới, xe về trước nhận chuyến sau "
              "(`routing/dispatch_baseline.py`).", ""]  # fmt: skip
    return "\n".join(lines)
