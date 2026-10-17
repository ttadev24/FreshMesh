"""Verdict I1 of protocol frn-v1 (§3) from ``frn_inventory_sums_L*.csv`` → ``frn-inventory.md`` and
``frn_inventory_frontier.svg`` in ``docs/experiments`` (generated). Waste % = wasted ÷ received (§3);
stockout % = lost ÷ demand; frontiers are recomputed on every bootstrap resample of stores."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from data_frn.bootstrap import N_RESAMPLES, SEED
from data_frn.sums_io import open_text, write_summary
from decision.frontier import pareto, waste_at

LEVELS = (5.0, 10.0, 15.0)
FAMILY = {"freshmesh": "FreshMesh", "freshmesh_q28": "FreshMesh + q28", "mean7": "baseline",
          "seasonal_naive": "baseline"}  # fmt: skip
STATS = ("opening", "received", "wasted", "lost", "demand")


def load(path: Path, *more: Path) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, str]]:
    """``{variant: {stat: (n_stores,)}}`` on one sorted store list (union of the files), plus the stamp of the
    first file."""
    rows = []
    for p in (path, *more):
        with open_text(p) as fh:
            rows += list(csv.DictReader(fh))
    stores = sorted({r["store"] for r in rows})
    pos = {s: i for i, s in enumerate(stores)}
    out: dict = defaultdict(lambda: {st: np.zeros(len(stores)) for st in STATS})
    for r in rows:
        for st in STATS:
            out[r["variant"]][st][pos[r["store"]]] += float(r[st])
    return dict(out), {k: rows[0][k] for k in ("protocol", "protocol_sha256", "shelf_life", "seed")}


def _point(t: dict[str, Any]) -> tuple[float, float]:
    return 100.0 * t["lost"] / max(t["demand"], 1e-9), 100.0 * t["wasted"] / max(t["received"], 1e-9)


def frontiers(totals: dict[str, dict[str, float]]) -> dict[str, list[tuple[float, float]]]:
    points: dict[str, list] = defaultdict(list)
    for variant, t in totals.items():
        points[FAMILY[variant.split(":")[0]]].append(_point(t))
    return {fam: pareto(p) for fam, p in points.items()}


def _diffs(fr: dict[str, list], a: str = "FreshMesh", b: str = "baseline") -> list[float]:
    return [waste_at(fr[a], lv) - waste_at(fr[b], lv) for lv in LEVELS]


def verdict(
    sums: dict[str, dict[str, np.ndarray]], a: str = "FreshMesh", b: str = "baseline"
) -> dict[str, Any]:
    """Waste of family ``a`` minus family ``b`` at the stockout ``LEVELS``, with bootstrap CIs over stores."""
    pooled = {v: {st: float(a.sum()) for st, a in s.items()} for v, s in sums.items()}
    fr = frontiers(pooled)
    n_stores = len(next(iter(sums.values()))["demand"])
    idx = np.random.default_rng(SEED).integers(0, n_stores, size=(N_RESAMPLES, n_stores))
    boot = np.array([
        _diffs(frontiers({v: {st: float(x[ix].sum()) for st, x in s.items()} for v, s in sums.items()}), a, b)
        for ix in idx
    ])  # fmt: skip
    per_level = []
    for j, lv in enumerate(LEVELS):
        col = boot[:, j]
        ok = col[~np.isnan(col)]
        lo, hi = (np.percentile(ok, [2.5, 97.5]) if ok.size else (math.nan, math.nan))
        per_level.append({"stockout": lv, "diff": _diffs(fr, a, b)[j], "ci_low": float(lo),
                          "ci_high": float(hi), "undefined_share": float(np.isnan(col).mean())})  # fmt: skip
    passed = all(r["ci_high"] < 0 and r["undefined_share"] == 0 for r in per_level)
    return {"frontiers": fr, "levels": per_level, "pass": passed, "stores": n_stores, "pooled": pooled}


def _n(x: float, nd: int = 2) -> str:
    return "—" if math.isnan(x) else f"{x:.{nd}f}".replace(".", ",")


def reach_note(fr: dict[str, list]) -> str:
    """Why a cell can be '—': the lowest stockout each family reaches (its most generous policy)."""
    lows = "; ".join(f"{fam} {_n(min(p[0] for p in f))}%" for fam, f in fr.items())
    return (f"Hết hàng thấp nhất mỗi họ chính sách đạt được: {lows}. Ô '—' là mức nằm ngoài đường biên của một "
            "họ; quy tắc tính ô đó là không đạt. 'Không xác định' là tỉ lệ lần lấy mẫu lại rơi vào trường hợp này.")  # fmt: skip


def _svg(fr: dict[str, list], path: Path) -> None:
    w, h, pad = 640, 400, 50
    xmax = max(p[0] for f in fr.values() for p in f) * 1.05
    ymax = max(p[1] for f in fr.values() for p in f) * 1.05

    def xy(p):
        return pad + (w - 2 * pad) * p[0] / xmax, h - pad - (h - 2 * pad) * p[1] / ymax

    colors = {"FreshMesh": "#14714C", "FreshMesh + q28": "#2F6DB5", "baseline": "#F7A11F"}
    mid = h / 2
    body = [
        f'<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" stroke="#555"/>',
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h - pad}" stroke="#555"/>',
        f'<text x="{w / 2}" y="{h - 12}" text-anchor="middle" font-size="13">Hết hàng (%)</text>',
        f'<text x="16" y="{mid}" font-size="13" transform="rotate(-90 16 {mid})" text-anchor="middle">'
        "Hàng bỏ (%)</text>",
    ]
    for i, (fam, f) in enumerate(fr.items()):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(xy, f))
        body.append(f'<polyline points="{pts}" fill="none" stroke="{colors[fam]}" stroke-width="2.5"/>')
        label = f'x="{w - pad - 150}" y="{pad + 18 * i}" fill="{colors[fam]}" font-size="13"'
        body.append(f"<text {label}>{fam}</text>")
    head = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="sans-serif">'
    path.write_text(head + "".join(body) + "</svg>\n", encoding="utf-8", newline="\n")


def write_report(paths: dict[int, Path], docs_dir: Path) -> Path:
    """``paths``: {shelf life: sums CSV}; shelf life 2 is primary, 1 and 3 are sensitivity runs."""
    lines = ["<!-- GENERATED by `python -m data_frn inventory-report`; do not edit by hand -->",
             "# FreshRetailNet — chính sách nhập hàng / inventory policies (frn-v1 §3)", ""]  # fmt: skip
    summary: dict[str, Any] = {"report": "frn-inventory.md", "primary_shelf_life": 2, "shelf_lives": {}}
    for life, path in sorted(paths.items(), key=lambda kv: (kv[0] != 2, kv[0])):
        sums, st = load(path)
        v = verdict(sums)
        summary |= {"protocol": st["protocol"], "protocol_sha256": st["protocol_sha256"]}
        summary["shelf_lives"][str(life)] = {k: v[k] for k in ("levels", "pass", "stores", "frontiers")}
        role = "chính / primary" if life == 2 else "độ nhạy / sensitivity"
        lines += [f"## Hạn dùng {life} ngày — {role}", "",
                  f"Giao thức `{st['protocol']}` (sha256 `{st['protocol_sha256'][:12]}…`), "
                  f"{v['stores']} cửa hàng.",
                  "", "| Hết hàng | Hàng bỏ FreshMesh − baseline (điểm %) | 95% CI | Không xác định |",
                  "|---|---|---|---|"]  # fmt: skip
        for r in v["levels"]:
            ci = f"[{_n(r['ci_low'])}; {_n(r['ci_high'])}]"
            undefined = _n(100 * r["undefined_share"], 1)
            lines.append(f"| {_n(r['stockout'], 0)}% | {_n(r['diff'])} | {ci} | {undefined}% |")
        lines += ["", reach_note(v["frontiers"])]
        if life == 2:
            lines += ["", f"**I1 {'ĐẠT / PASS' if v['pass'] else 'KHÔNG ĐẠT / FAIL'}**", ""]
            _svg(v["frontiers"], Path(docs_dir) / "frn_inventory_frontier.svg")
            lines += ["![Đường biên hàng bỏ ↔ hết hàng](frn_inventory_frontier.svg)", ""]
        lines.append("")
    out = Path(docs_dir) / "frn-inventory.md"
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    write_summary(Path(docs_dir) / "frn_inventory_summary.json", summary)
    return out
