import csv
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from data_sim import generate_all
from simulation import report, sim30
from simulation.demand import ReplayMismatch, future_demand, recover_chain_process
from simulation.freshmesh import file_sha256

DOCS = Path(__file__).resolve().parents[2] / "docs" / "experiments"


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("sim42")
    generate_all(out, seed=42)
    return out


def test_replay_reproduces_generated_history(data_dir):
    proc = recover_chain_process("CHAIN_B", 42, verify_db=data_dir)  # raises on any mismatch
    assert len(proc.uniforms) == len(proc.stores)
    assert len(proc.lognormals) == len(proc.stores) * 30


def test_replay_detects_modified_db(data_dir, tmp_path):
    import shutil

    (tmp_path / "chains").mkdir()
    src = data_dir / "chains" / "CHAIN_A.sqlite"
    dst = tmp_path / "chains" / "CHAIN_A.sqlite"
    shutil.copyfile(src, dst)
    con = sqlite3.connect(dst)
    with con:
        con.execute("UPDATE daily_sales SET units = units + 1 WHERE rowid = 1")
    con.close()
    with pytest.raises(ReplayMismatch):
        recover_chain_process("CHAIN_A", 42, verify_db=tmp_path)


def test_future_demand_deterministic_per_seed_and_out_of_sample():
    proc = recover_chain_process("CHAIN_A", 42)
    a, b, c = future_demand(proc, 1001), future_demand(proc, 1001), future_demand(proc, 1002)
    assert np.array_equal(a.units, b.units) and np.array_equal(a.promo, b.promo)
    assert np.array_equal(a.rain, b.rain)
    assert not np.array_equal(a.units, c.units)
    assert a.units.shape == (len(proc.stores), 30, 30)
    assert a.dates[0].isoformat() == "2026-10-01" and len(a.dates) == 30
    # same stores: mean level of the future window is close to the base level of the seed-42 history
    assert 0.5 < a.units.mean() / max(c.units.mean(), 1e-9) < 2.0


def test_mean_ci_matches_t_interval():
    m, lo, hi = sim30.mean_ci([1.0, 2.0, 3.0, 4.0, 5.0])
    half = 2.776 * np.std([1, 2, 3, 4, 5], ddof=1) / np.sqrt(5)
    assert (m, lo, hi) == pytest.approx((3.0, 3.0 - half, 3.0 + half))


def test_run_refuses_without_protocol(tmp_path):
    with pytest.raises(FileNotFoundError):
        sim30.run_sim30(["CHAIN_A"], [sim30.DEV_SEED], data_dir=tmp_path, docs_dir=tmp_path)
    (tmp_path / sim30.PROTOCOL_FILE).write_text("no version here", encoding="utf-8")
    with pytest.raises(ValueError):
        sim30.require_protocol(tmp_path)


def test_protocol_declares_threshold_seeds_and_versions():
    text = (DOCS / sim30.PROTOCOL_FILE).read_text(encoding="utf-8")
    for version in sim30.PRIMARY_BY_VERSION:
        assert f"`{version}`" in text
    assert "+2.0 percentage points" in text and sim30.STOCKOUT_TOLERANCE_PP == 2.0
    assert "1001, 1002, 1003, 1004, 1005" in text
    assert str(sim30.DEV_SEED) in text


def test_results_csv_carries_protocol_version_and_hash():
    path = DOCS / sim30.RESULTS_CSV
    if not path.exists():
        pytest.skip("sim30 results not generated yet")
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows and {"protocol_version", "protocol_sha256"} <= set(rows[0])
    text = (DOCS / sim30.PROTOCOL_FILE).read_text(encoding="utf-8")
    for r in rows:
        assert r["protocol_version"] in sim30.PRIMARY_BY_VERSION and f"`{r['protocol_version']}`" in text
        assert r["protocol_sha256"] == file_sha256(DOCS / sim30.PROTOCOL_FILE)  # protocol unchanged since run
        assert int(r["seed"]) in sim30.CONFIRMATORY_SEEDS  # dev seed never written
        assert r["source"]  # provenance of the input chain DB (";"-joined dataset ids) is recorded
    # every confirmatory seed of every chain present for the primary pairs (no seed dropped)
    for chain in {r["chain_id"] for r in rows}:
        for policy in (sim30.PRIMARY_BASELINE, *sim30.PRIMARY_BY_VERSION.values()):
            seeds = {int(r["seed"]) for r in rows if r["chain_id"] == chain and r["policy"] == policy}
            assert seeds == set(sim30.CONFIRMATORY_SEEDS)


def _row(chain, seed, policy, waste, stockout):
    base = {k: 0.0 for k in sim30.METRIC_FIELDS}
    return {
        **base,
        "chain_id": chain,
        "seed": seed,
        "policy": policy,
        "waste_pct": waste,
        "stockout_pct": stockout,
    }


def test_summarize_applies_the_frozen_rule():
    rows = []
    for i, s in enumerate(sim30.CONFIRMATORY_SEEDS):
        rows.append(_row("X", s, "baseline_mean7", 10.0 + 0.1 * i, 20.0))
        rows.append(_row("X", s, "freshmesh_balanced_h1", 12.0, 5.0))  # more waste -> fail
        rows.append(
            _row("X", s, "freshmesh_balanced_h1_carry20", 8.0 + 0.05 * i, 21.5 + 0.01 * i)
        )  # +1.5 pp ok
    s = sim30.summarize(rows)
    v = s["chains"]["X"]["verdicts"]
    assert v["sim30-v1"]["pass"] is False and v["sim30-v1"]["waste_ok"] is False
    assert v["sim30-v2"]["pass"] is True
    rows2 = [
        dict(r, stockout_pct=r["stockout_pct"] + (0.6 if r["policy"].endswith("carry20") else 0))
        for r in rows
    ]
    assert sim30.summarize(rows2)["chains"]["X"]["verdicts"]["sim30-v2"]["stockout_ok"] is False


def test_write_generated_keeps_hand_written_text(tmp_path):
    p = tmp_path / "r.md"
    report.write_generated(p, "table v1")
    p.write_text(p.read_text() + "\nmy analysis\n")
    report.write_generated(p, "table v2")
    text = p.read_text()
    assert "table v2" in text and "table v1" not in text and "my analysis" in text


def test_reports_and_summary_from_committed_results():
    if not (DOCS / sim30.RESULTS_CSV).exists():
        pytest.skip("sim30 results not generated yet")
    summary = sim30.summarize(sim30.read_results(DOCS / sim30.RESULTS_CSV))
    ET.fromstring(report.sim30_svg(summary))  # well-formed SVG
    out = report.experiment_summary(DOCS)
    assert out["sources"] and "source" not in out
    assert set(out["sim30"]["overall_pass"]) == set(sim30.PRIMARY_BY_VERSION)
    assert out["sim30"]["headline_version"] == "sim30-v1"
    for chain in out["sim30"]["chains"].values():
        assert {"baseline", "freshmesh_v1", "freshmesh_v2", "verdicts"} <= set(chain)


def test_experiment_summary_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        report.experiment_summary(tmp_path)


def test_results_document_production_adoption_erratum():
    """MED-5: the frozen protocol says "No change to decision/" and v1 = API default; the results document
    must carry a dated correction (the protocol file itself is SHA-pinned and stays untouched)."""
    text = (DOCS / "sim30-results.md").read_text(encoding="utf-8")
    assert "Production adoption (2026-10-13)" in text
    assert "fresh_carry_cost_rate_per_day" in text and "holding_rate=0.005" in text
