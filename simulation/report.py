# ruff: noqa: E501  (long Vietnamese markdown/SVG string literals read better unwrapped)
"""Markdown/SVG reports of the sim30 and routing experiments, and ``experiment_summary`` for the API/UI.

Generated tables sit between ``<!-- BEGIN GENERATED -->`` / ``<!-- END GENERATED -->``; text outside the
markers (the hand-written analysis) is preserved when a report is regenerated. SVGs are written by hand
(no plotting library).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from html import escape
from pathlib import Path
from typing import Any

from data_sim import SOURCE
from simulation import routing_bench, sim30

BEGIN, END = "<!-- BEGIN GENERATED -->", "<!-- END GENERATED -->"
SIM30_MD = "sim30-results.md"
SIM30_SVG = "sim30_waste_stockout.svg"
ROUTING_MD = "routing-benchmark.md"
ROUTING_SVG = "routing_benchmark_km.svg"
POLICY_LABELS = {
    "baseline_mean7": "Baseline TB 7 ngày / mean-7",
    "baseline_mean7_net": "Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory)",
    "freshmesh_balanced_h1": "FreshMesh Cân bằng h=1 (v1 primary)",
    "freshmesh_balanced_h1_carry20": "FreshMesh Cân bằng h=1, carry 20% (v2 primary)",
    "freshmesh_balanced_hL": "FreshMesh Cân bằng h=L (exploratory)",
    "freshmesh_safe_h1": "FreshMesh An toàn h=1 (exploratory)",
    "freshmesh_lean_h1": "FreshMesh Tiết kiệm h=1 (exploratory)",
}
METHOD_LABELS = {"one_trip_per_order": "Mỗi đơn một chuyến", "paco": "PACO", "sa": "SA", "alns": "ALNS"}
COLORS = {
    "baseline_mean7": "#8a8f98",
    "freshmesh_balanced_h1": "#e08a2e",
    "freshmesh_balanced_h1_carry20": "#1f8a70",
    "one_trip_per_order": "#8a8f98",
    "paco": "#1f8a70",
    "sa": "#3b6fb6",
    "alns": "#b5527a",
}


def write_generated(path: Path, generated: str, tail: str = "") -> None:
    """Replace the generated block of ``path`` (keep text outside it); create the file if missing."""
    path = Path(path)
    block = f"{BEGIN}\n{generated.rstrip()}\n{END}"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if BEGIN in text and END in text:
            head, rest = text.split(BEGIN, 1)
            _, after = rest.split(END, 1)
            path.write_text(head + block + after, encoding="utf-8")
            return
    path.write_text(block + "\n" + (f"\n{tail.rstrip()}\n" if tail else ""), encoding="utf-8")


def _f(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}"


def _ci(t: Sequence[float], nd: int = 1, scale: float = 1.0) -> str:
    m, lo, hi = (v / scale for v in t)
    return f"{_f(m, nd)} [{_f(lo, nd)}; {_f(hi, nd)}]"


# ---------------------------------------------------------------- sim30


def sim30_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Sim30 — kết quả mô phỏng 30 ngày / 30-day inventory simulation results",
        "",
        f"Dữ liệu: **{SOURCE}**. Giao thức đăng ký trước: [sim30-protocol.md](sim30-protocol.md) "
        f"(`sim30-v1`, revision `sim30-v2`). Seeds {', '.join(map(str, sim30.CONFIRMATORY_SEEDS))}; "
        "mean [95% t-CI] over seeds; % pooled over stores × 14 fresh SKUs × 30 days.",
        "",
        "## Kết luận theo tiêu chí §1.4 #3 / Verdict",
        "",
        "| Chuỗi / chain | v1: Cân bằng h=1 (pre-registered) | v2: carry 20% (revision) |",
        "|---|---|---|",
    ]
    for chain, c in summary["chains"].items():
        cells = []
        for version in sim30.PRIMARY_BY_VERSION:
            v = c["verdicts"].get(version)
            if v is None:
                cells.append("—")
                continue
            d = c["diff_vs_baseline"][v["policy"]]
            word = "**ĐẠT / PASS**" if v["pass"] else "**KHÔNG ĐẠT / FAIL**"
            cells.append(
                f"{word} — Δbỏ {_ci(d['waste_pct'], 2)} pp; Δhết hàng {_ci(d['stockout_pct'], 2)} pp"
            )
        lines.append(f"| {chain} | {cells[0]} | {cells[1]} |")
    ov = summary["overall_pass"]
    lines += [
        "",
        "Toàn bộ / overall (all chains pass): "
        + "; ".join(f"`{k}` → {'ĐẠT / PASS' if v else 'KHÔNG ĐẠT / FAIL'}" for k, v in ov.items())
        + ".",
        "",
        "Rule: chain passes iff upper 95% CI of Δwaste < 0 **and** upper 95% CI of Δstockout ≤ +"
        f"{sim30.STOCKOUT_TOLERANCE_PP} pp (Δ = FreshMesh − baseline_mean7).",
        "",
        "## Bảng kết quả / results by policy",
        "",
        "| Chuỗi | Chính sách / policy | % bỏ / waste % | % hết hàng / stockout % | Lợi nhuận / net profit (triệu đ) "
        "| Chi phí proxy (triệu đ) |",
        "|---|---|---|---|---|---|",
    ]
    for chain, c in summary["chains"].items():
        for p, m in c["policies"].items():
            lines.append(
                f"| {chain} | {POLICY_LABELS.get(p, p)} | {_ci(m['waste_pct'])} | {_ci(m['stockout_pct'])} | "
                f"{_ci(m['net_profit_vnd'], 1, 1e6)} | {_ci(m['cost_proxy_vnd'], 1, 1e6)} |"
            )
    lines += [
        "",
        "## Chênh lệch so với baseline / paired difference vs `baseline_mean7`",
        "",
        "| Chuỗi | Chính sách | Δ % bỏ (pp) | Δ % hết hàng (pp) | Δ lợi nhuận (triệu đ) |",
        "|---|---|---|---|---|",
    ]
    for chain, c in summary["chains"].items():
        for p, d in c["diff_vs_baseline"].items():
            lines.append(
                f"| {chain} | {POLICY_LABELS.get(p, p)} | {_ci(d['waste_pct'], 2)} | {_ci(d['stockout_pct'], 2)} | "
                f"{_ci(d['net_profit_vnd'], 1, 1e6)} |"
            )
    lines += ["", f"![waste and stockout]({SIM30_SVG})", ""]
    return "\n".join(lines)


def _bar_panel(
    x0: float,
    y0: float,
    w: float,
    h: float,
    title: str,
    groups: Sequence[str],
    series: Sequence[tuple[str, str, Sequence[tuple[float, float, float]]]],
    unit: str,
) -> list[str]:
    """Grouped bars with CI whiskers. ``series`` = (label, color, [(mean, lo, hi) per group])."""
    top = max((t[2] for _, _, vals in series for t in vals), default=1.0)
    ymax = max(1.0, math.ceil(top / 5.0) * 5.0)
    out = [f'<text x="{x0}" y="{y0 - 10}" font-size="13" font-weight="600">{escape(title)}</text>']
    for k in range(6):
        v = ymax * k / 5
        y = y0 + h - h * v / ymax
        out.append(f'<line x1="{x0}" x2="{x0 + w}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e3e5e8"/>')
        out.append(f'<text x="{x0 - 6}" y="{y + 4:.1f}" font-size="10" text-anchor="end">{v:g}{unit}</text>')
    gw = w / max(len(groups), 1)
    bw = gw * 0.8 / max(len(series), 1)
    for gi, g in enumerate(groups):
        gx = x0 + gi * gw + gw * 0.1
        out.append(
            f'<text x="{gx + gw * 0.4:.1f}" y="{y0 + h + 16}" font-size="11" text-anchor="middle">{escape(g)}</text>'
        )
        for si, (_, color, vals) in enumerate(series):
            m, lo, hi = vals[gi]
            bx = gx + si * bw
            by = y0 + h - h * m / ymax
            out.append(
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw - 2:.1f}" height="{y0 + h - by:.1f}" fill="{color}"/>'
            )
            cx = bx + (bw - 2) / 2
            ylo, yhi = y0 + h - h * lo / ymax, y0 + h - h * hi / ymax
            out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{ylo:.1f}" y2="{yhi:.1f}" stroke="#222"/>')
            out.append(
                f'<text x="{cx:.1f}" y="{by - 4:.1f}" font-size="9" text-anchor="middle">{m:.1f}</text>'
            )
    return out


def _legend(x: float, y: float, items: Sequence[tuple[str, str]]) -> list[str]:
    out = []
    for i, (label, color) in enumerate(items):
        yy = y + i * 16
        out.append(f'<rect x="{x}" y="{yy - 9}" width="11" height="11" fill="{color}"/>')
        out.append(f'<text x="{x + 16}" y="{yy}" font-size="11">{escape(label)}</text>')
    return out


def _svg(width: int, height: int, body: Sequence[str], title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif" fill="#222">\n'
        f"<title>{escape(title)}</title>\n"
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>\n' + "\n".join(body) + "\n</svg>\n"
    )


def sim30_svg(summary: Mapping[str, Any]) -> str:
    chains = list(summary["chains"])
    pols = ["baseline_mean7", *sim30.PRIMARY_BY_VERSION.values()]
    body: list[str] = []
    for i, metric in enumerate(("waste_pct", "stockout_pct")):
        series = [
            (POLICY_LABELS[p], COLORS[p], [summary["chains"][c]["policies"][p][metric] for c in chains])
            for p in pols
            if all(p in summary["chains"][c]["policies"] for c in chains)
        ]
        title = "% hàng tươi phải bỏ / waste %" if metric == "waste_pct" else "% hết hàng / stockout %"
        body += _bar_panel(70 + i * 420, 60, 360, 240, title, chains, series, "%")
    body += _legend(70, 350, [(POLICY_LABELS[p], COLORS[p]) for p in pols])
    body.append(
        f'<text x="70" y="410" font-size="10">{SOURCE} · mean of 5 seeds, whiskers = 95% t-CI · '
        "sim30-protocol.md</text>"
    )
    return _svg(870, 420, body, "Sim30 waste and stockout")


def write_sim30_report(docs_dir: Path) -> dict[str, Any]:
    docs_dir = Path(docs_dir)
    summary = sim30.summarize(sim30.read_results(docs_dir / sim30.RESULTS_CSV))
    write_generated(docs_dir / SIM30_MD, sim30_markdown(summary))
    (docs_dir / SIM30_SVG).write_text(sim30_svg(summary), encoding="utf-8")
    return summary


# ---------------------------------------------------------------- routing


def routing_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r["status"] == "ok"]
    methods = [m for m in ("one_trip_per_order", "paco", "sa", "alns") if any(r["method"] == m for r in rows)]
    batches = sorted({(r["chain_id"], r["store_id"]) for r in rows})
    per: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = defaultdict(dict)
    for r in ok:
        per[r["method"]][(r["chain_id"], r["store_id"])] = r
    out: dict[str, Any] = {"n_batches": len(batches), "methods": {}, "source": SOURCE}
    baseline = per["one_trip_per_order"]
    for m in methods:
        done = per[m]
        common = [b for b in batches if b in done and b in baseline]
        km_saving_pct: float | None = None
        better_all: bool | None = None
        if common and m != "one_trip_per_order":
            km_saving_pct = round(
                100
                * (
                    1
                    - sum(float(done[b]["road_km"]) for b in common)
                    / sum(float(baseline[b]["road_km"]) for b in common)
                ),
                1,
            )
            better_all = all(
                float(done[b]["road_km"]) < float(baseline[b]["road_km"])
                and int(done[b]["vehicles"]) < int(baseline[b]["vehicles"])
                for b in common
            )
        out["methods"][m] = {
            "label": METHOD_LABELS[m],
            "batches_ok": len(done),
            "batches_failed": sum(1 for r in rows if r["method"] == m and r["status"] != "ok"),
            "total_km": round(sum(float(done[b]["road_km"]) for b in done), 1),
            "total_vehicles": sum(int(done[b]["vehicles"]) for b in done),
            "late_stops": sum(int(done[b]["late_stops"]) for b in done),
            "batches_exceeding_fleet": sum(int(done[b]["exceeds_fleet"]) for b in done),
            "mean_runtime_s": round(sum(float(done[b]["runtime_s"]) for b in done) / max(len(done), 1), 2),
            "km_saving_vs_baseline_pct": km_saving_pct,
            "better_km_and_vehicles_all_batches": better_all,
        }
    out["at_risk_orders"] = sum(int(r["at_risk"]) for r in rows if r["method"] == "one_trip_per_order")
    out["orders"] = sum(int(r["n_orders"]) for r in rows if r["method"] == "one_trip_per_order")
    return out


def routing_markdown(rows: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    methods = list(summary["methods"])
    lines = [
        "# Benchmark định tuyến / routing benchmark (spec §1.4 #4, §6)",
        "",
        f"Dữ liệu: **{SOURCE}**. Đợt đơn demo hiện tại (cửa sổ 45 phút trước 2026-10-01 09:00) của "
        f"{summary['n_batches']} cửa hàng ở 3 chuỗi, {summary['orders']} đơn, {summary['at_risk_orders']} đơn "
        "bị loại trước khi định tuyến (không kịp giao ngay cả khi đi thẳng — giống nhau cho mọi phương pháp). "
        "Đội xe 4 × 30 đơn vị; km = phút di chuyển × 20 km/h (đã gồm hệ số đường vòng 1,3).",
        "",
        "| Phương pháp / method | Tổng km | Tổng xe / vehicles | Điểm dừng trễ / late stops | Đợt vượt đội xe "
        "| Runtime TB (s) | Tiết kiệm km vs baseline | Tốt hơn baseline cả km và số xe ở mọi đợt |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in methods:
        s = summary["methods"][m]
        sav = "—" if s["km_saving_vs_baseline_pct"] is None else f"{_f(s['km_saving_vs_baseline_pct'])}%"
        better = {None: "—", True: "có / yes", False: "không / no"}[s["better_km_and_vehicles_all_batches"]]
        failed = f" ({s['batches_failed']} lỗi)" if s["batches_failed"] else ""
        lines.append(
            f"| {s['label']}{failed} | {_f(s['total_km'])} | {s['total_vehicles']} | {s['late_stops']} | "
            f"{s['batches_exceeding_fleet']} | {_f(s['mean_runtime_s'], 1)} | {sav} | {better} |"
        )
    lines += [
        "",
        'Baseline "vehicles" = số chuyến (mỗi đơn một chuyến khứ hồi từ cửa hàng). Runtime = thời gian solver '
        "tự báo (lần giải đầu tiên; kết quả được cache theo hash của đợt).",
        "",
        "## Theo cửa hàng / per store (km · xe · trễ)",
        "",
        "| Cửa hàng | Đơn | Định tuyến | " + " | ".join(METHOD_LABELS[m] for m in methods) + " |",
        "|---|---|---|" + "---|" * len(methods),
    ]
    by = {(r["store_id"], r["method"]): r for r in rows}
    for store in sorted({r["store_id"] for r in rows}):
        base = by[(store, "one_trip_per_order")]
        cells = []
        for m in methods:
            r = by.get((store, m))
            if r is None or r["status"] != "ok":
                cells.append(r["status"] if r else "—")
            else:
                cells.append(f"{_f(float(r['road_km']))} · {r['vehicles']} · {r['late_stops']}")
        lines.append(f"| {store} | {base['n_orders']} | {base['n_routable']} | " + " | ".join(cells) + " |")
    lines += ["", f"![km per store]({ROUTING_SVG})", ""]
    return "\n".join(lines)


def routing_svg(rows: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    methods = list(summary["methods"])
    stores = sorted({r["store_id"] for r in rows})
    by = {(r["store_id"], r["method"]): r for r in rows if r["status"] == "ok"}
    series = []
    for m in methods:
        vals = []
        for s in stores:
            v = float(by[(s, m)]["road_km"]) if (s, m) in by else 0.0
            vals.append((v, v, v))
        series.append((METHOD_LABELS[m], COLORS[m], vals))
    width = max(900, 70 + len(stores) * 60)
    body = _bar_panel(60, 60, width - 100, 280, "Quãng đường mỗi đợt / road km per batch", stores, series, "")
    body += _legend(60, 390, [(METHOD_LABELS[m], COLORS[m]) for m in methods])
    body.append(
        f'<text x="60" y="{390 + 16 * len(methods) + 8}" font-size="10">{SOURCE} · demo batch 2026-10-01 09:00</text>'
    )
    return _svg(width, 400 + 16 * len(methods) + 20, body, "Routing benchmark km")


def write_routing_report(docs_dir: Path) -> dict[str, Any]:
    docs_dir = Path(docs_dir)
    rows = routing_bench.read_results(docs_dir / routing_bench.RESULTS_CSV)
    if not rows:
        raise FileNotFoundError(
            f"{docs_dir / routing_bench.RESULTS_CSV} missing; run routing-benchmark first"
        )
    summary = routing_summary(rows)
    write_generated(docs_dir / ROUTING_MD, routing_markdown(rows, summary))
    (docs_dir / ROUTING_SVG).write_text(routing_svg(rows, summary), encoding="utf-8")
    return summary


# ---------------------------------------------------------------- headline numbers


def experiment_summary(docs_dir: Path) -> dict[str, Any]:
    """Headline numbers of the sim30 and routing experiments (for the API/UI).

    Raises ``FileNotFoundError`` when neither result CSV exists; a missing one is reported as ``None``."""
    docs_dir = Path(docs_dir)
    sim_rows = sim30.read_results(docs_dir / sim30.RESULTS_CSV)
    route_rows = routing_bench.read_results(docs_dir / routing_bench.RESULTS_CSV)
    if not sim_rows and not route_rows:
        raise FileNotFoundError(f"no sim30 or routing benchmark results in {docs_dir}")
    out: dict[str, Any] = {"source": SOURCE, "sim30": None, "routing": None}
    if sim_rows:
        s = sim30.summarize(sim_rows)
        chains = {}
        for chain, c in s["chains"].items():
            entry: dict[str, Any] = {"seeds": c["seeds"]}
            for key, policy in (
                ("baseline", sim30.PRIMARY_BASELINE),
                *((f"freshmesh_{v.split('-')[-1]}", p) for v, p in sim30.PRIMARY_BY_VERSION.items()),
            ):
                if policy in c["policies"]:
                    m = c["policies"][policy]
                    entry[key] = {
                        "policy": policy,
                        "waste_pct": round(m["waste_pct"][0], 1),
                        "stockout_pct": round(m["stockout_pct"][0], 1),
                        "net_profit_vnd": round(m["net_profit_vnd"][0]),
                    }
            entry["verdicts"] = {
                v: {
                    "pass": d["pass"],
                    "waste_diff_pp": round(c["diff_vs_baseline"][d["policy"]]["waste_pct"][0], 2),
                    "stockout_diff_pp": round(c["diff_vs_baseline"][d["policy"]]["stockout_pct"][0], 2),
                }
                for v, d in c["verdicts"].items()
            }
            chains[chain] = entry
        out["sim30"] = {
            "protocol": sim30.PROTOCOL_FILE,
            "headline_version": "sim30-v1",  # the pre-registered version; v2 is a dev-seed revision
            "stockout_tolerance_pp": sim30.STOCKOUT_TOLERANCE_PP,
            "overall_pass": s["overall_pass"],
            "chains": chains,
        }
    if route_rows:
        out["routing"] = routing_summary(route_rows)
    return out
