"""FreshMesh data provenance: dataset registry, row-level source ids, prompt log and raw-file manifest.

Public API:
    Dataset, load_registry(data_dir) -> {id: Dataset}
    label_vi(dataset_id, registry=None) -> short Vietnamese badge text
    sources_for(con, tables) -> distinct dataset ids behind those tables of a chain DB
    describe(dataset_id, registry=None) -> full detail dict (incl. logged prompts)
    log_prompt(...), llm_generate(prompt, purpose, dataset_id, model=None, llm=None, ...) -> Generation
    read_prompt_log(data_dir), get_prompt(prompt_id, data_dir) -> full record + response text + hash check
    record_raw_file(...), verify_manifest(data_dir)
CLI: `uv run python -m provenance show [dataset_id]` / `verify` / `prompts` / `prompt <id>`.
"""

from provenance.manifest import read_manifest, record_raw_file, verify_manifest
from provenance.prompts import (
    Generation,
    LLMGenerationError,
    LLMResult,
    get_prompt,
    llm_generate,
    log_prompt,
    read_prompt_log,
)
from provenance.registry import (
    KINDS,
    SYNTHETIC_LABEL_VI,
    Dataset,
    describe,
    label_vi,
    load_registry,
    registry_entries,
    sources_for,
    write_registry,
)

__all__ = [
    "KINDS",
    "SYNTHETIC_LABEL_VI",
    "Dataset",
    "Generation",
    "LLMGenerationError",
    "LLMResult",
    "describe",
    "get_prompt",
    "label_vi",
    "llm_generate",
    "load_registry",
    "log_prompt",
    "read_manifest",
    "read_prompt_log",
    "record_raw_file",
    "registry_entries",
    "sources_for",
    "verify_manifest",
    "write_registry",
]
