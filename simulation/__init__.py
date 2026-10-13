"""FreshMesh experiments: 30-day inventory simulation and routing benchmark.

Public API:
    run_sim30(chain_ids, seeds, *, data_dir, docs_dir, ...)   # docs/experiments/sim30-protocol.md
    run_routing_benchmark(*, data_dir, docs_dir, solver_url, ...)
    experiment_summary(docs_dir) -> dict                      # headline numbers for the API/UI
"""

from simulation.report import experiment_summary
from simulation.routing_bench import run_routing_benchmark
from simulation.sim30 import run_sim30

__all__ = ["experiment_summary", "run_routing_benchmark", "run_sim30"]
