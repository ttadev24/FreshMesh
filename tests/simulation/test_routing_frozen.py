import pytest

from simulation.routing_bench import results_name, run_routing_benchmark, write_results


def test_result_set_names_keep_detours_and_tags_apart():
    assert results_name(1.3) == "routing_benchmark.csv"
    assert results_name(1.58) == "routing_benchmark_detour158.csv"
    assert results_name(1.585) == "routing_benchmark_detour1585.csv"
    assert results_name(1.3, "_v12") == "routing_benchmark_v12.csv"
    assert results_name(1.58, "_v12") == "routing_benchmark_v12_detour158.csv"


def test_a_set_holding_the_r1_verdict_is_not_silently_rewritten(tmp_path):
    write_results(tmp_path / "routing_benchmark.csv",
                  [{"chain_id": "CHAIN_A", "store_id": "A-CH1", "method": "zone_sweep", "status": "ok"}])  # fmt: skip
    with pytest.raises(ValueError, match="pre-registered R1"):
        run_routing_benchmark(data_dir=tmp_path, docs_dir=tmp_path, solver_url="http://127.0.0.1:9", chain_ids=[])
    assert not list(tmp_path.glob("*.tmp"))
