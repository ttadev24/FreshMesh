import pytest

from agent.charts import build_chart_option, make_render_chart_tool
from agent.tools import ToolContext, ToolError, ToolRegistry

CTX = ToolContext(chain_id="CHAIN_A", actor="owner_a")
X = ["01/10", "02/10", "03/10"]


def test_forecast_band_option():
    opt = build_chart_option(
        {
            "chart_type": "forecast_band",
            "title": "Dự báo rau",
            "x": X,
            "unit": "kg",
            "band": {"p10": [80, 70, 90], "p50": [100, 95, 110], "p90": [130, 120, 150]},
            "series": [{"name": "Thực tế", "values": [98, 101, 0]}],
        }
    )
    names = [s["name"] for s in opt["series"]]
    assert names == ["P10", "P10–P90", "P50", "Thực tế"]
    base, width, p50 = opt["series"][:3]
    assert base["stack"] == width["stack"] == "band"
    assert base["areaStyle"]["opacity"] == 0 and width["areaStyle"]["opacity"] > 0
    assert width["data"] == [50, 50, 60]
    assert p50["data"] == [100, 95, 110] and "stack" not in p50
    assert opt["xAxis"]["data"] == X and opt["yAxis"]["name"] == "kg"
    assert opt["legend"]["data"] == ["P50", "P10–P90", "Thực tế"]


def test_bar_and_line():
    bar = build_chart_option(
        {
            "chart_type": "bar",
            "title": "Doanh số",
            "x": ["A1", "A2"],
            "series": [{"name": "Số lượng", "values": [90, 12]}],
        }
    )
    assert bar["series"] == [{"name": "Số lượng", "type": "bar", "data": [90, 12]}]
    assert bar["xAxis"]["boundaryGap"] is True
    line = build_chart_option(
        {
            "chart_type": "line",
            "title": "T",
            "x": X,
            "series": [{"name": "a", "values": [1, 2, 3]}, {"name": "b", "values": [3, 2, 1]}],
        }
    )
    assert [s["type"] for s in line["series"]] == ["line", "line"]


@pytest.mark.parametrize(
    "args,match",
    [
        ({"chart_type": "bar", "title": "T", "x": X, "series": [{"name": "a", "values": [1]}]}, "điểm"),
        ({"chart_type": "bar", "title": "T", "x": X}, "chuỗi"),
        ({"chart_type": "forecast_band", "title": "T", "x": X}, "P10"),
        (
            {
                "chart_type": "forecast_band",
                "title": "T",
                "x": X,
                "band": {"p10": [1, 2, 3], "p50": [0, 2, 3], "p90": [5, 5, 5]},
            },
            "P10 ≤ P50",
        ),
    ],
)
def test_invalid_chart_args(args, match):
    with pytest.raises(ToolError, match=match):
        build_chart_option(args)


def test_registered_tool_is_read_and_non_verifiable():
    reg = ToolRegistry()
    tool = reg.register(make_render_chart_tool())
    assert tool.kind == "read" and tool.verifiable is False
    res = reg.call(
        "render_chart",
        {"chart_type": "bar", "title": "T", "x": ["a"], "series": [{"name": "s", "values": [1]}]},
        CTX,
    )
    assert res.data["option"]["series"][0]["data"] == [1] and "sources" not in res.data
    with pytest.raises(ToolError):
        reg.call("render_chart", {"chart_type": "pie", "title": "T", "x": ["a"]}, CTX)
