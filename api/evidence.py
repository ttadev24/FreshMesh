"""'Bằng chứng' (``GET /api/evidence``): each headline claim of FreshMesh next to its measured result, PASS
and FAIL alike, read from the generated reports committed in ``docs/experiments`` (nothing here is
recomputed or typed by hand). A report that has not been run is listed as ``not_run``, never dropped.

Verdicts: ``pass`` / ``fail`` against a criterion written before the run (``pre_registered``), ``mixed``
when some parts of a pre-registered claim pass and others fail, ``measured`` when there is no criterion
(the number is reported as is). Exploratory checks never set a verdict: they are ``measured`` with
``exploratory = true`` and are left out of ``counts`` (protocol frn-v1 §7)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from api.evidence_impact import impact
from decision.text import pct

log = logging.getLogger(__name__)

REAL_VI = (
    "Dữ liệu thật: FreshRetailNet-50K (Dingdong, CC BY 4.0), 18 thành phố; không phải thị trường Việt Nam"
)
SIM_VI = "Dữ liệu mô phỏng có đáp án (data_sim), 3 chuỗi"


def _n(x: float, nd: int = 3) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def _read(docs: Path, name: str) -> dict | None:
    path = docs / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _item(id_: str, title: str, data: str, report: str, pre: bool, fn: Callable[[], tuple],
          exploratory: bool = False) -> dict:  # fmt: skip
    out = {"id": id_, "title_vi": title, "data_vi": data, "report": f"docs/experiments/{report}",
           "pre_registered": pre, "exploratory": exploratory}  # fmt: skip
    try:
        verdict, headline, numbers = fn()
    except Exception:  # a missing or malformed report is listed as not run, never a 500
        log.warning("evidence item %s unavailable", id_, exc_info=True)
        verdict, headline, numbers = "not_run", "Chưa có kết quả trong docs/experiments.", {}
    try:
        big = impact(id_, numbers)
    except Exception:
        log.warning("evidence impact %s unavailable", id_, exc_info=True)
        big = None
    return out | {"verdict": verdict, "headline_vi": headline, "numbers": numbers, "impact": big}


def _frn_forecast(docs: Path) -> tuple:
    s = _read(docs, "frn_forecast_summary.json")
    if s is None:
        raise FileNotFoundError("frn_forecast_summary.json")
    v = s["histories"][s["primary"]]
    t = v["test"]
    passed = [k for k in ("F1", "F2") if v[k]["pass"]]  # the confirmatory criteria; F3 is exploratory
    verdict = "pass" if len(passed) == 2 else "fail" if not passed else "mixed"
    headline = (
        f"WAPE: MLP {_n(t['mlp']['wape'])}, TB 7 ngày {_n(t['mean7']['wape'])}, cùng thứ tuần trước "
        f"{_n(t['seasonal_naive']['wape'])}, phân vị 28 ngày {_n(t['empirical_q28']['wape'])}. "
        f"F1 {'đạt' if v['F1']['pass'] else 'không đạt'}, F2 {'đạt' if v['F2']['pass'] else 'không đạt'}; "
        f"F3 (thăm dò): độ phủ P10–P90 {_n(100 * v['F3']['coverage'], 1)}%."
    )
    return verdict, headline, {"test": t, "criteria": {k: v[k] for k in ("F1", "F2", "F3")}}


def _frn_inventory(docs: Path) -> tuple:
    s = _read(docs, "frn_inventory_summary.json")
    if s is None:
        raise FileNotFoundError("frn_inventory_summary.json")
    main = s["shelf_lives"][str(s["primary_shelf_life"])]

    def outside(level: float) -> str:  # which frontier does not reach this stockout level
        fams = [f for f, pts in main["frontiers"].items()
                if not min(p[0] for p in pts) <= level <= max(p[0] for p in pts)]  # fmt: skip
        return f"ngoài đường biên {', '.join(fams) or 'một họ'}"

    parts = [
        f"hết hàng {pct(r['stockout']).replace(',0%', '%')}: "
        + (outside(r["stockout"]) if r["diff"] is None else f"{_n(r['diff'], 2)} điểm %")
        for r in main["levels"]
    ]
    headline = (
        f"Hàng bỏ của FreshMesh trừ baseline tốt nhất, cùng mức hết hàng ({main['stores']} cửa hàng, "
        f"hạn dùng {s['primary_shelf_life']} ngày): {'; '.join(parts)}. Âm là FreshMesh tốt hơn."
    )
    numbers = {"shelf_lives": s["shelf_lives"]}
    amendments = (  # written after the v1 result, never a verdict of this item
        ("v11", "frn-v1.1", "cùng quy tắc đặt hàng với dự báo phân vị 28 ngày"),
        ("v13", "frn-v1.3", "trung vị dự báo MLP trong quy tắc đặt bù tồn (m × P50 trừ tồn)"),
    )
    for tag, version, what in amendments:
        am = _read(docs, f"frn_inventory_{tag}_summary.json")
        if not am:
            continue
        q = am["shelf_lives"][str(am["primary_shelf_life"])]
        diffs = "; ".join(
            f"{pct(r['stockout']).replace(',0%', '%')}: {'—' if r['diff'] is None else _n(r['diff'], 2)}"
            for r in q["levels"]
        )
        headline += (
            f" Thăm dò sau khi xem kết quả ({version}): {what}, chênh lệch {diffs} điểm % — "
            f"{'đạt' if q['pass'] else 'không đạt'}."
        )
        numbers[tag] = am["shelf_lives"]
    return ("pass" if main["pass"] else "fail"), headline, numbers


def _sim30(summary: dict | None) -> tuple:
    if not summary or not summary.get("sim30"):
        raise FileNotFoundError("sim30_results.csv")
    s = summary["sim30"]
    chains = {c: e["verdicts"] for c, e in s["chains"].items()}
    v1 = {c: v["sim30-v1"]["pass"] for c, v in chains.items() if "sim30-v1" in v}
    if not v1:
        raise KeyError("sim30-v1")
    headline = (
        "So với đặt theo TB 7 ngày, 30 ngày mô phỏng: "
        + "; ".join(
            f"{c} hàng bỏ {_n(v['sim30-v1']['waste_diff_pp'], 1)} điểm %, hết hàng "
            f"{_n(v['sim30-v1']['stockout_diff_pp'], 1)} điểm %"
            for c, v in chains.items()
            if "sim30-v1" in v
        )
        + "."
    )
    v2 = [v["sim30-v2"]["pass"] for v in chains.values() if "sim30-v2" in v]
    if v2:
        headline += f" Bản sửa v2 (giữ lại 20% tồn, viết sau): đạt {sum(v2)}/{len(v2)} chuỗi."
    verdict = "pass" if all(v1.values()) else "fail" if not any(v1.values()) else "mixed"
    return verdict, headline, {"chains": s["chains"]}


def _routing(summary: dict | None) -> tuple:
    if not summary or not summary.get("routing"):
        raise FileNotFoundError("routing_benchmark.csv")
    r = summary["routing"]
    paco, base = r["methods"]["paco"], r["methods"]["one_trip_per_order"]
    headline = (
        f"PACO: {_n(paco['total_km'], 1)} km, {paco['total_vehicles']} xe cho {r['orders']} đơn ở "
        f"{r['n_batches']} đợt; mỗi đơn một chuyến: {_n(base['total_km'], 1)} km, "
        f"{base['total_vehicles']} xe (giảm {_n(paco['km_saving_vs_baseline_pct'], 1)}% km)."
    )
    numbers = {"methods": r["methods"], "orders": r["orders"], "batches": r["n_batches"], "r1": r.get("r1"),
               "r1_v12": r.get("r1_v12")}  # fmt: skip
    r1 = (r.get("r1") or {}).get("1.3")
    if r1 is None:  # the pre-registered R1 has not been run: only the weak one-trip comparison exists
        return "not_run", headline, numbers
    headline += (
        f" So với điều phối chia vùng (cách làm tay): PACO ngắn hơn ở {r1['paco_shorter_batches']}/"
        f"{r1['batches']} đợt, {_n(r1['km']['paco'], 1)} so với {_n(r1['km']['zone_sweep'], 1)} km "
        f"(giảm {_n(r1['km_saving_pct'], 1)}%), điểm trễ {r1['late_stops']['paco']} so với "
        f"{r1['late_stops']['zone_sweep']}."
    )
    fixed = (r.get("r1_v12") or {}).get("1.3")
    if fixed:  # frn-v1.2, written after R1: the solver with the stop service time
        headline += (
            " Sau khi sửa lỗi bộ giải bỏ qua thời gian giao tại điểm (frn-v1.2, viết sau khi xem R1): "
            f"PACO ngắn hơn ở {fixed['paco_shorter_batches']}/{fixed['batches']} đợt "
            f"(giảm {_n(fixed['km_saving_pct'], 1)}% km), điểm trễ {fixed['late_stops']['paco']}."
        )
    return ("pass" if r1["pass"] else "fail"), headline, numbers


def _fl(fl: Callable[[], dict]) -> tuple:
    s = fl()
    m = s["metrics"]
    gain = s["improvement_vs_local"]
    headline = (
        f"WAPE tất cả cửa hàng: tự học {_n(m['local']['wape'], 4)} → liên kết {_n(m['fl']['wape'], 4)}; "
        f"cửa hàng mới: {_n(m['local']['new_store_wape'], 4)} → {_n(m['fl']['new_store_wape'], 4)} "
        f"({s['rounds']} vòng, {s['seeds']} seed)."
    )
    better = gain["wape"] > 0 and gain["new_store"] > 0
    return "measured", headline, {"metrics": m, "improvement_vs_local": gain, "better_than_local": better}


def _frn_fl(docs: Path) -> tuple:
    s = _read(docs, "frn_fl_summary.json")
    if s is None:
        raise FileNotFoundError("frn_fl_summary.json")
    new, r = s["metrics"]["new_store"], s["L1"]
    headline = (
        f"WAPE cửa hàng mới ({new['fl']['stores']} cửa hàng, {len(s['seeds'])} seed): tự học "
        f"{_n(new['local']['wape'], 4)} → liên kết {_n(new['fl']['wape'], 4)}; chênh lệch {_n(r['diff'], 4)} "
        f"[{_n(r['ci_low'], 4)}; {_n(r['ci_high'], 4)}]. Tất cả cửa hàng: "
        f"{_n(s['metrics']['all']['local']['wape'], 4)} → {_n(s['metrics']['all']['fl']['wape'], 4)}."
    )
    return ("pass" if r["pass"] else "fail"), headline, {"metrics": s["metrics"], "L1": r}


def _elasticity(docs: Path) -> tuple:
    s = _read(docs, "frn_elasticity_summary.json")
    if s is None:
        raise FileNotFoundError("frn_elasticity_summary.json")
    lo, hi = s["ai_range"]
    inside = s["inside_ai_range"]
    where = "nằm trong" if inside else "nằm ngoài"
    headline = (
        f"Trung vị hệ số co giãn giá trên {len(s['categories'])} nhóm hàng: {_n(s['median_elasticity'], 2)}, "
        f"{where} khoảng AI đề xuất ({_n(lo, 1)} … {_n(hi, 1)}). Giảm giá có thể nội sinh nên chỉ để "
        "tham khảo."
    )
    numbers = {"median": s["median_elasticity"], "categories": s["categories"], "inside_ai_range": inside}
    return "measured", headline, numbers  # frn-v1 §4 is exploratory: the range check is not a verdict


def _drivers(docs: Path) -> tuple:
    s = _read(docs, "forecast_drivers_check.json")
    if s is None:
        raise FileNotFoundError("forecast_drivers_check.json")
    mae = {c: round(v["weekday_mae_pp"], 1) for c, v in s["chains"].items()}
    headline = "Sai số yếu tố thứ trong tuần so với sự thật mô phỏng: " + ", ".join(
        f"{c} {_n(x, 1)} điểm %" for c, x in mae.items()
    ) + "."
    return "measured", headline, {"weekday_mae_pp": mae}


def build_evidence(docs: Path, fl: Callable[[], dict], experiments: Callable[[], dict | None]) -> dict:
    """``fl``/``experiments``: the FL and sim30/routing summaries (``forecasting.fl``, ``simulation``)."""
    try:
        sim = experiments()
    except Exception:  # partial or missing sim30/routing CSVs: those items become not_run
        log.warning("experiment summary unavailable", exc_info=True)
        sim = None
    claims = [  # (id, question, data, report, pre-registered, result)
        ("frn_forecast", "Dự báo tốt hơn cách đặt hàng quen thuộc?", REAL_VI, "frn-forecast.md", True,
         lambda: _frn_forecast(docs)),
        ("frn_inventory", "Đặt theo mức phục vụ ít hàng bỏ hơn ở cùng mức hết hàng?", REAL_VI,
         "frn-inventory.md", True, lambda: _frn_inventory(docs)),
        ("sim30", "30 ngày vận hành: ít hàng bỏ mà không hết hàng thêm?", SIM_VI, "sim30-results.md", True,
         lambda: _sim30(sim)),
        ("routing", "PACO giao ít km hơn cách điều phối viên chia vùng?", SIM_VI, "routing-benchmark.md",
         True, lambda: _routing(sim)),
        ("federated", "Học liên kết giữa các chuỗi có giúp cửa hàng mới?", SIM_VI, "fl-results.md", False,
         lambda: _fl(fl)),
        ("frn_federated", "Học liên kết giữa 18 thành phố thật có giúp cửa hàng mới?", REAL_VI, "frn-fl.md",
         True, lambda: _frn_fl(docs)),
        ("drivers", "Lời giải thích dự báo có đúng không?", SIM_VI, "forecast-drivers-check.md", False,
         lambda: _drivers(docs)),
    ]  # fmt: skip
    items = [_item(*c) for c in claims]
    items.append(_item("elasticity", "Độ co giãn giá mà động cơ giảm giá dùng có hợp lý trên dữ liệu thật?",
                       REAL_VI, "frn-elasticity.md", True, lambda: _elasticity(docs), exploratory=True))
    counts: dict[str, int] = {}
    for it in items:
        if not it["exploratory"]:
            counts[it["verdict"]] = counts.get(it["verdict"], 0) + 1
    return {"items": items, "counts": counts, "note_vi": "Kết quả KHÔNG ĐẠT được công bố cùng kết quả ĐẠT."}
