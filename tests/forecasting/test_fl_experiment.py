import xml.etree.ElementTree as ET

import pytest

from forecasting.fl.experiment import COMPARISON_CSV, DP_CSV, TUNING_CSV, run_all
from forecasting.fl.summary import fl_summary
from forecasting.fl.svg import bar_chart_svg, line_chart_svg
from tests.forecasting.conftest import FIXTURE_SOURCES, FL_CHAINS


@pytest.fixture(scope="module")
def experiment_out(fl_dir, tmp_path_factory):
    docs = tmp_path_factory.mktemp("fl_docs")
    paths = run_all(
        fl_dir,
        docs,
        seeds=(0,),
        chains=FL_CHAINS,
        grid={"rounds": (1, 2), "local_epochs": (1,), "finetune_epochs": (0,)},
        epsilons=(10.0,),
    )
    return docs, paths


def test_experiment_outputs(experiment_out):
    docs, paths = experiment_out
    for name in (COMPARISON_CSV, DP_CSV, TUNING_CSV, "fl_comparison_wape.svg", "fl_dp_curve.svg"):
        assert (docs / name).exists()
    for svg in ("fl_comparison_wape.svg", "fl_dp_curve.svg"):
        ET.fromstring((docs / svg).read_text(encoding="utf-8"))  # well-formed
    text = (docs / COMPARISON_CSV).read_text(encoding="utf-8")
    for method in ("local", "fl", "local_fl_trainer", "centralized"):
        assert f"\n{method},mean,ALL,new_store," in text
    tuning = (docs / TUNING_CSV).read_text(encoding="utf-8").splitlines()
    assert len(tuning) == 3 and sum(line.endswith("True") for line in tuning) == 1


def test_fl_summary_from_experiment_output(experiment_out, fl_dir):
    docs, _ = experiment_out
    s = fl_summary(fl_dir, docs)
    assert s["chains_participating"] == list(FL_CHAINS)
    assert s["sources"] == FIXTURE_SOURCES and len(s["source_labels_vi"]) == len(FIXTURE_SOURCES)
    assert set(s["improvement_vs_local"]) >= {"wape", "pinball", "new_store"}
    m = s["metrics"]
    expected = (m["local"]["wape"] - m["fl"]["wape"]) / m["local"]["wape"]
    assert s["improvement_vs_local"]["wape"] == pytest.approx(expected, abs=1e-3)
    assert s["rounds"] in (1, 2)
    assert [d["epsilon"] for d in s["dp_curve"]] == [pytest.approx(10.0), None]
    assert "giả lập" not in s["protocol_note_vi"] and "FedAvg" in s["protocol_note_vi"]


def test_fl_summary_requires_experiments(tmp_path):
    with pytest.raises(FileNotFoundError, match="forecasting.fl experiment"):
        fl_summary(tmp_path, tmp_path)


def test_svg_helpers_escape_and_skip_nan():
    svg = bar_chart_svg("A & B", ["x", "y"], [("s<1>", [0.5, float("nan")])], y_label="WAPE")
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert sum(1 for el in root.iter() if el.tag.endswith("rect")) == 1 + 1 + 1  # background, bar, legend
    ET.fromstring(line_chart_svg("t", [(1.0, 0.5), (10.0, 0.4)], [("ref", 0.45)], x_label="x", y_label="y"))
