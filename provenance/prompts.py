"""Prompt log: every LLM call that produces data is recorded so organizers can inspect it.

`<data_dir>/provenance/prompts.jsonl` holds one JSON object per call attempt (accepted, invalid or failed):
`{id, ts, task, attempt, status, error, model, purpose, dataset_id, system, prompt, prompt_sha256,
parameters, usage, stop_reason, request_id, response_path, response_sha256, parsed_path}`; the full response
text is stored at `response_path` (relative to the data dir). API keys are never part of a record: request
parameters are logged as sent (no headers, no client object) and every logged string is scrubbed of
`sk-ant-…` patterns as a second line of defence.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from provenance.registry import provenance_dir, registry_entries

MSG_NO_KEY_VI = (
    "Chưa cấu hình ANTHROPIC_API_KEY nên không thể sinh dữ liệu bằng AI. "
    "Không có dữ liệu nào được tạo; hãy đặt khóa API rồi chạy lại."
)
DEFAULT_GEN_MODEL = "claude-haiku-5-5"
DEFAULT_SYSTEM = "Bạn sinh tham số dữ liệu cho hệ thống FreshMesh. Trả lời đúng định dạng được yêu cầu."
SECRET_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]*")
STATUSES = ("accepted", "invalid", "api_error")


class LLMGenerationError(RuntimeError):
    def __init__(self, message_vi: str):
        super().__init__(message_vi)
        self.message_vi = message_vi


@dataclass(frozen=True)
class LLMResult:
    """What one model call returned (no SDK objects, so it can be faked in tests)."""

    text: str
    model: str
    stop_reason: str
    usage: dict[str, int] = field(default_factory=dict)
    request_id: str | None = None


LLMCall = Callable[[dict[str, Any]], LLMResult]


@dataclass(frozen=True)
class Generation:
    text: str | None
    record: dict[str, Any]

    @property
    def accepted(self) -> bool:
        return self.record["status"] == "accepted"


def redact(text: str) -> str:
    return SECRET_RE.sub("[REDACTED]", text)


def _redact_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: _redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_redact_obj(v) for v in obj]
    return obj


def prompts_path(data_dir: Path | str = Path("data")) -> Path:
    return provenance_dir(data_dir) / "prompts.jsonl"


def read_prompt_log(data_dir: Path | str = Path("data")) -> list[dict[str, Any]]:
    path = prompts_path(data_dir)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def get_prompt(prompt_id: str, data_dir: Path | str = Path("data")) -> dict[str, Any]:
    """Full record of one logged call plus the response text and a hash check. KeyError if unknown."""
    for rec in read_prompt_log(data_dir):
        if rec["id"] == prompt_id:
            out = dict(rec)
            out["response"] = None
            out["response_sha256_ok"] = None
            if rec.get("response_path"):
                path = Path(data_dir) / rec["response_path"]
                if path.exists():
                    text = path.read_text(encoding="utf-8")
                    out["response"] = text
                    out["response_sha256_ok"] = _sha256(text) == rec["response_sha256"]
                else:
                    out["response_sha256_ok"] = False
            return out
    raise KeyError(f"không có prompt {prompt_id!r} trong {prompts_path(data_dir)}")


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
    response: str | None,
    purpose: str,
    dataset_id: str,
    model: str,
    data_dir: Path | str = Path("data"),
    ts: dt.datetime | None = None,
    system: str | None = None,
    task: str | None = None,
    attempt: int = 1,
    status: str = "accepted",
    error: str | None = None,
    parameters: dict[str, Any] | None = None,
    usage: dict[str, int] | None = None,
    stop_reason: str | None = None,
    request_id: str | None = None,
    parsed_path: str | None = None,
) -> dict[str, Any]:
    """Append one prompt/response record and store the response text. Returns the record.

    Raises ``LLMGenerationError`` unless `dataset_id` is registered with kind 'ai_generated'."""
    require_ai_dataset(dataset_id, data_dir)
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    prompt, system = redact(prompt), redact(system) if system is not None else None
    response = redact(response) if response is not None else None
    when = (ts or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    prompt_hash = _sha256(prompt)
    response_hash = _sha256(response) if response is not None else None
    salt = f"{prompt_hash}{response_hash}{dataset_id}{task}{attempt}{status}{when.isoformat()}"
    prompt_id = f"P{when:%Y%m%dT%H%M%S}-{_sha256(salt)[:10]}"
    resp_rel: str | None = None
    if response is not None:
        rel = Path("provenance") / "responses" / f"{prompt_id}.txt"
        resp_abs = Path(data_dir) / rel
        resp_abs.parent.mkdir(parents=True, exist_ok=True)
        resp_abs.write_text(response, encoding="utf-8")
        resp_rel = rel.as_posix()
    record = {
        "id": prompt_id,
        "ts": when.isoformat(),
        "task": task,
        "attempt": attempt,
        "status": status,
        "error": redact(error) if error else None,
        "model": model,
        "purpose": purpose,
        "dataset_id": dataset_id,
        "system": system,
        "prompt": prompt,
        "prompt_sha256": prompt_hash,
        "parameters": _redact_obj(parameters or {}),
        "usage": usage or {},
        "stop_reason": stop_reason,
        "request_id": request_id,
        "response_path": resp_rel,
        "response_sha256": response_hash,
        "parsed_path": parsed_path,
    }
    path = prompts_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def anthropic_call(params: dict[str, Any]) -> LLMResult:
    """One streamed Messages API call with the official SDK. Needs ANTHROPIC_API_KEY."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise LLMGenerationError(MSG_NO_KEY_VI)
    import anthropic

    client = anthropic.Anthropic(api_key=key, max_retries=2)
    try:
        with client.messages.stream(**params) as stream:
            message = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise LLMGenerationError("Khóa ANTHROPIC_API_KEY không hợp lệ.") from None
    except anthropic.RateLimitError:
        raise LLMGenerationError("Dịch vụ AI đang quá tải (429), hãy thử lại sau.") from None
    except anthropic.APIStatusError as exc:
        detail = redact(str(exc.message))[:800]
        raise LLMGenerationError(f"Dịch vụ AI trả lỗi (mã {exc.status_code}): {detail}") from None
    except anthropic.APIConnectionError:
        raise LLMGenerationError("Không kết nối được dịch vụ AI.") from None
    text = "".join(b.text for b in message.content if b.type == "text")
    usage = {
        k: v
        for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        if isinstance(v := getattr(message.usage, k, None), int)
    }
    request_id = getattr(message, "_request_id", None)
    return LLMResult(text, str(message.model), str(message.stop_reason), usage, request_id)


def llm_generate(
    prompt: str,
    purpose: str,
    dataset_id: str,
    model: str | None = None,
    *,
    system: str = DEFAULT_SYSTEM,
    data_dir: Path | str = Path("data"),
    llm: LLMCall | None = None,
    params: dict[str, Any] | None = None,
    task: str | None = None,
    attempt: int = 1,
    validate: Callable[[str], str | None] | None = None,
    parsed_path: str | None = None,
) -> Generation:
    """Call the model once (no tools), log the attempt, return the response text and its log record.

    `params` are extra request parameters (max_tokens, output_config, thinking …) and are logged verbatim with
    the model. `validate(text)` returns an error message (logged, status 'invalid') or None ('accepted').
    `parsed_path` (where the caller stores the accepted, parsed output) is recorded on accepted attempts.
    A response cut off by `max_tokens` or declined (`refusal`) is logged as 'invalid'. API failures are logged
    as 'api_error' and raise `LLMGenerationError` (with `.record`). Without `llm`, the real SDK is used and
    ANTHROPIC_API_KEY must be set, otherwise `LLMGenerationError` is raised and nothing is written.
    """
    require_ai_dataset(dataset_id, data_dir)
    if llm is None:
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            raise LLMGenerationError(MSG_NO_KEY_VI)
        llm = anthropic_call
    used_model = model or os.environ.get("FRESHMESH_LLM_MODEL", "").strip() or DEFAULT_GEN_MODEL
    request = {"model": used_model, "max_tokens": 16000, **(params or {})}
    request["system"] = system
    request["messages"] = [{"role": "user", "content": prompt}]
    logged_params = {k: v for k, v in request.items() if k not in ("system", "messages")}
    common = {
        "prompt": prompt,
        "purpose": purpose,
        "dataset_id": dataset_id,
        "data_dir": data_dir,
        "system": system,
        "task": task,
        "attempt": attempt,
        "parameters": logged_params,
    }
    try:
        result = llm(request)
    except LLMGenerationError as exc:
        if exc.message_vi == MSG_NO_KEY_VI:
            raise
        exc.record = log_prompt(  # type: ignore[attr-defined]
            response=None, model=used_model, status="api_error", error=exc.message_vi, **common
        )
        raise
    error: str | None = None
    if result.stop_reason == "max_tokens":
        error = "Câu trả lời bị cắt do chạm max_tokens."
    elif result.stop_reason == "refusal":
        error = "Mô hình từ chối trả lời (stop_reason=refusal)."
    elif validate is not None:
        error = validate(result.text)
    record = log_prompt(
        response=result.text,
        model=result.model or used_model,
        status="invalid" if error else "accepted",
        error=error,
        usage=result.usage,
        stop_reason=result.stop_reason,
        request_id=result.request_id,
        parsed_path=None if error else parsed_path,
        **common,
    )
    return Generation(result.text, record)
