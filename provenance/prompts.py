"""Prompt log: every LLM call that produces data is recorded so organizers can inspect it.

`<data_dir>/provenance/prompts.jsonl` holds one JSON object per call:
`{id, ts, model, purpose, dataset_id, prompt, prompt_sha256, response_path, response_sha256}`; the full
response text is stored at `response_path` (relative to the data dir).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from provenance.registry import provenance_dir, registry_entries

MSG_NO_KEY_VI = (
    "Chưa cấu hình ANTHROPIC_API_KEY nên không thể sinh dữ liệu bằng AI. "
    "Không có dữ liệu nào được tạo; hãy đặt khóa API rồi chạy lại."
)


class LLMGenerationError(RuntimeError):
    def __init__(self, message_vi: str):
        super().__init__(message_vi)
        self.message_vi = message_vi


def prompts_path(data_dir: Path | str = Path("data")) -> Path:
    return provenance_dir(data_dir) / "prompts.jsonl"


def read_prompt_log(data_dir: Path | str = Path("data")) -> list[dict[str, Any]]:
    path = prompts_path(data_dir)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require_ai_dataset(dataset_id: str, data_dir: Path | str = Path("data")) -> None:
    """AI output may only be logged under a dataset registered with kind 'ai_generated', so it can never
    be shown with a non-AI label."""
    entry = registry_entries(data_dir).get(dataset_id)
    if entry is None or entry.get("kind") != "ai_generated":
        raise LLMGenerationError(
            f"Bộ dữ liệu {dataset_id!r} chưa được đăng ký với loại 'ai_generated' trong registry; "
            "hãy đăng ký trước khi sinh dữ liệu bằng AI."
        )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def log_prompt(
    *,
    prompt: str,
    response: str,
    purpose: str,
    dataset_id: str,
    model: str,
    data_dir: Path | str = Path("data"),
    ts: dt.datetime | None = None,
) -> dict[str, Any]:
    """Append one prompt/response record and store the response text. Returns the record.

    Raises ``LLMGenerationError`` unless `dataset_id` is registered with kind 'ai_generated'."""
    require_ai_dataset(dataset_id, data_dir)
    when = (ts or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    prompt_hash = _sha256(prompt)
    response_hash = _sha256(response)
    prompt_id = f"P{when:%Y%m%dT%H%M%S}-{_sha256(prompt_hash + response_hash + dataset_id)[:10]}"
    resp_rel = Path("provenance") / "responses" / f"{prompt_id}.txt"
    resp_abs = Path(data_dir) / resp_rel
    resp_abs.parent.mkdir(parents=True, exist_ok=True)
    resp_abs.write_text(response, encoding="utf-8")
    record = {
        "id": prompt_id,
        "ts": when.isoformat(),
        "model": model,
        "purpose": purpose,
        "dataset_id": dataset_id,
        "prompt": prompt,
        "prompt_sha256": prompt_hash,
        "response_path": resp_rel.as_posix(),
        "response_sha256": response_hash,
    }
    with prompts_path(data_dir).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def llm_generate(
    prompt: str,
    purpose: str,
    dataset_id: str,
    model: str | None = None,
    *,
    system: str = "Bạn sinh tham số dữ liệu cho hệ thống FreshMesh. Trả lời đúng định dạng được yêu cầu.",
    data_dir: Path | str = Path("data"),
    client: Any = None,
) -> str:
    """Call Claude once (no tools), log prompt + response, return the response text.

    `client` may be any object with `complete(LLMRequest) -> LLMResponse` (tests inject a fake).
    Without `client`, `ANTHROPIC_API_KEY` must be set, otherwise `LLMGenerationError` is raised and
    nothing is written.
    """
    from agent.llm import AnthropicClient, LLMRequest, LLMUnavailableError

    require_ai_dataset(dataset_id, data_dir)
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            raise LLMGenerationError(MSG_NO_KEY_VI)
        client = AnthropicClient(model=model)
    request = LLMRequest(
        system=system,
        messages=[{"role": "user", "content": prompt}],
        tools=[],
        allow_tools=False,
        purpose="rewrite",
    )
    try:
        response = client.complete(request)
    except LLMUnavailableError as exc:
        # agent/ messages end with chat advice ("; hãy dùng chế độ kịch bản"), irrelevant for data generation.
        reason = exc.message_vi.split(";")[0].rstrip(". ")
        msg = f"Sinh dữ liệu bằng AI thất bại: {reason}. Không có dữ liệu nào được tạo."
        raise LLMGenerationError(msg) from None
    used_model = getattr(client, "model", None) or model or "unknown"
    log_prompt(
        prompt=prompt,
        response=response.text,
        purpose=purpose,
        dataset_id=dataset_id,
        model=str(used_model),
        data_dir=data_dir,
    )
    return response.text
