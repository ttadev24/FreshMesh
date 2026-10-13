"""``render_chart``: build an ECharts ``option`` spec from explicit arguments (no data access).

Chart types:
* ``forecast_band``: P10–P90 band (stacked transparent base + filled width) with the P50 line, plus
  optional extra line series (e.g. actual sales).
* ``line`` / ``bar``: one series per entry of ``series``.

Its output only echoes the numbers it was given, so it is registered as non-verifiable for the
number guardrail.
"""

from __future__ import annotations

from typing import Any

from agent.tools import Tool, ToolContext, ToolError, ToolResult

PRIMARY = "#2E7D32"  # forest green (DESIGN.md primary)
BAND = "#81C784"
PALETTE = ["#2E7D32", "#F59E0B", "#2563EB", "#DC2626", "#6B7280", "#0D9488"]

_NUM_ARRAY = {"type": "array", "items": {"type": "number"}, "minItems": 1, "maxItems": 400}
RENDER_CHART_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chart_type": {"type": "string", "enum": ["forecast_band", "line", "bar"]},
        "title": {"type": "string", "minLength": 1, "maxLength": 120},
        "x": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 400},
        "unit": {"type": "string", "maxLength": 20},
        "band": {
            "type": "object",
            "properties": {"p10": _NUM_ARRAY, "p50": _NUM_ARRAY, "p90": _NUM_ARRAY},
            "required": ["p10", "p50", "p90"],
            "additionalProperties": False,
        },
        "series": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 60},
                    "values": _NUM_ARRAY,
                },
                "required": ["name", "values"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["chart_type", "title", "x"],
    "additionalProperties": False,
}


def _check_len(name: str, values: list[float], n: int) -> None:
    if len(values) != n:
        raise ToolError(f"Chuỗi '{name}' có {len(values)} điểm nhưng trục x có {n} điểm.")


def build_chart_option(args: dict[str, Any]) -> dict[str, Any]:
    chart_type, x = args["chart_type"], list(args["x"])
    series_in = list(args.get("series") or [])
    for s in series_in:
        _check_len(s["name"], s["values"], len(x))
    option: dict[str, Any] = {
        "title": {"text": args["title"]},
        "tooltip": {"trigger": "axis"},
        "color": PALETTE,
        "grid": {"left": 48, "right": 16, "top": 48, "bottom": 32},
        "xAxis": {"type": "category", "data": x, "boundaryGap": chart_type == "bar"},
        "yAxis": {"type": "value", "name": args.get("unit", "")},
    }
    series: list[dict[str, Any]] = []
    legend: list[str] = []
    if chart_type == "forecast_band":
        band = args.get("band")
        if not band:
            raise ToolError("Biểu đồ dự báo cần dữ liệu P10/P50/P90.")
        p10, p50, p90 = band["p10"], band["p50"], band["p90"]
        for name, values in (("P10", p10), ("P50", p50), ("P90", p90)):
            _check_len(name, values, len(x))
        if any(not (lo <= mid <= hi) for lo, mid, hi in zip(p10, p50, p90, strict=True)):
            raise ToolError("Dữ liệu dự báo phải thỏa P10 ≤ P50 ≤ P90.")
        series += [
            {
                "name": "P10",
                "type": "line",
                "data": p10,
                "stack": "band",
                "symbol": "none",
                "lineStyle": {"opacity": 0},
                "areaStyle": {"opacity": 0},
                "tooltip": {"show": True},
            },
            {
                "name": "P10–P90",
                "type": "line",
                "data": [round(hi - lo, 6) for lo, hi in zip(p10, p90, strict=True)],
                "stack": "band",
                "symbol": "none",
                "lineStyle": {"opacity": 0},
                "areaStyle": {"color": BAND, "opacity": 0.35},
            },
            {
                "name": "P50",
                "type": "line",
                "data": p50,
                "symbol": "circle",
                "symbolSize": 5,
                "lineStyle": {"width": 2, "color": PRIMARY},
                "itemStyle": {"color": PRIMARY},
            },
        ]
        legend += ["P50", "P10–P90"]
        for s in series_in:
            series.append(
                {"name": s["name"], "type": "line", "data": s["values"], "lineStyle": {"type": "dashed"}}
            )
            legend.append(s["name"])
    else:
        if not series_in:
            raise ToolError("Biểu đồ cần ít nhất một chuỗi số liệu.")
        for s in series_in:
            series.append({"name": s["name"], "type": chart_type, "data": s["values"]})
            legend.append(s["name"])
    option["legend"] = {"data": legend}
    option["series"] = series
    return option


def render_chart(args: dict[str, Any], ctx: ToolContext | None = None) -> ToolResult:
    option = build_chart_option(args)
    return ToolResult({"chart_type": args["chart_type"], "option": option}, ["render_chart"])


def make_render_chart_tool() -> Tool:
    return Tool(
        "render_chart",
        "Vẽ biểu đồ (ECharts) từ số liệu đã có: dải dự báo P10–P90 với đường P50, đường hoặc cột.",
        RENDER_CHART_SCHEMA,
        "read",
        render_chart,
        verifiable=False,
    )
