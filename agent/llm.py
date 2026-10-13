"""LLM clients behind one provider-neutral protocol.

* :class:`AnthropicClient`: Claude via the official ``anthropic`` SDK, streaming with tool calling.
  Model from ``FRESHMESH_LLM_MODEL`` (default ``claude-sonnet-5-5``), key from ``ANTHROPIC_API_KEY``.
  Without a key it raises :class:`LLMUnavailableError` with a Vietnamese message (never a stack trace).
* :class:`ScriptedClient`: replays a recorded scenario (see ``agent.scripted``) with no network. It reads
  the tool results present in the conversation exactly like a real model would, so the scripted path
  runs through the same loop, guardrail and audit as the LLM path.

Messages use the Anthropic Messages shape (``role`` + content blocks). Assistant content returned by a
client is appended back verbatim (``LLMResponse.assistant_content``) so provider-specific blocks such as
thinking blocks survive the tool loop unchanged.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from agent.guardrail import redact_for_llm, unwrap_untrusted, wrap_untrusted

DEFAULT_MODEL = "claude-sonnet-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MSG_NO_KEY_VI = "Chưa cấu hình ANTHROPIC_API_KEY nên không dùng được trợ lý AI; hãy dùng chế độ kịch bản."


class LLMUnavailableError(RuntimeError):
    def __init__(self, message_vi: str):
        super().__init__(message_vi)
        self.message_vi = message_vi


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class LLMRequest:
    system: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    allow_tools: bool = True
    purpose: Literal["agent", "rewrite"] = "agent"


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str  # "tool_use" | "end_turn" | "max_tokens" | "refusal" | ...
    assistant_content: list[Any] = field(default_factory=list)


TextCallback = Callable[[str], None]


class LLMClient(Protocol):
    name: str

    def complete(self, request: LLMRequest, on_text: TextCallback | None = None) -> LLMResponse: ...


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def configured_model() -> str:
    return os.environ.get("FRESHMESH_LLM_MODEL", "").strip() or DEFAULT_MODEL


# ---------------------------------------------------------------- message helpers


def _has_text(obj: Any) -> bool:
    if isinstance(obj, str):
        return True
    if isinstance(obj, dict):
        return any(_has_text(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_text(v) for v in obj)
    return False


def encode_tool_output(data: Any) -> str:
    """Redact PII, serialise, and wrap as untrusted data when any text (table/user content) is present."""
    safe = redact_for_llm(data)
    body = json.dumps(safe, ensure_ascii=False, default=str)
    return wrap_untrusted(body) if _has_text(safe) else body


def decode_tool_output(content: Any) -> Any:
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    text = unwrap_untrusted(str(content))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def tool_result_block(tool_use_id: str, content: str, *, is_error: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if is_error:
        block["is_error"] = True
    return block


def _get(block: Any, key: str, default: Any = None) -> Any:
    return block.get(key, default) if isinstance(block, dict) else getattr(block, key, default)


@dataclass(frozen=True)
class TurnOutput:
    tool: str
    args: dict[str, Any]
    data: Any
    error: str | None


def turn_start(messages: Sequence[dict[str, Any]]) -> int:
    """Index of the current turn's user message (the last user message whose content is a string)."""
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] == "user" and isinstance(messages[i]["content"], str):
            return i
    return 0


def turn_outputs(messages: Sequence[dict[str, Any]]) -> list[TurnOutput]:
    """Tool calls and their (decoded) results in the current turn, in call order."""
    calls: dict[str, tuple[str, dict[str, Any]]] = {}
    order: list[str] = []
    results: dict[str, tuple[Any, str | None]] = {}
    for msg in messages[turn_start(messages) :]:
        content = msg["content"]
        if isinstance(content, str):
            continue
        for block in content:
            kind = _get(block, "type")
            if kind == "tool_use":
                calls[_get(block, "id")] = (_get(block, "name"), dict(_get(block, "input") or {}))
                order.append(_get(block, "id"))
            elif kind == "tool_result":
                raw = _get(block, "content")
                if _get(block, "is_error", False):
                    results[_get(block, "tool_use_id")] = (None, str(raw))
                else:
                    results[_get(block, "tool_use_id")] = (decode_tool_output(raw), None)
    return [TurnOutput(calls[i][0], calls[i][1], *results[i]) for i in order if i in results]


def turn_user_message(messages: Sequence[dict[str, Any]]) -> str:
    return messages[turn_start(messages)]["content"] if messages else ""


# ---------------------------------------------------------------- Anthropic


class AnthropicClient:
    """Claude with streaming + tool calling. Pass ``sdk_client`` to inject a fake in tests."""

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 16000,
        effort: str | None = None,
        use_fallbacks: bool | None = None,
        sdk_client: Any = None,
    ):
        self.model = model or configured_model()
        self.max_tokens = max_tokens
        self.effort = effort or os.environ.get("FRESHMESH_LLM_EFFORT", "").strip() or "medium"
        if use_fallbacks is None:
            use_fallbacks = os.environ.get("FRESHMESH_LLM_FALLBACKS", "1").strip() != "0"
        self.use_fallbacks = use_fallbacks
        if sdk_client is not None:
            self._sdk = sdk_client
            return
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise LLMUnavailableError(MSG_NO_KEY_VI)
        import anthropic

        self._sdk = anthropic.Anthropic(api_key=key)

    def _params(self, request: LLMRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": request.system,
            "messages": request.messages,
            "output_config": {"effort": self.effort},
        }
        if request.tools:
            # Inputs stream as generated; the registry validates every input against its schema.
            params["tools"] = [{**t, "eager_input_streaming": True} for t in request.tools]
            params["tool_choice"] = {"type": "auto" if request.allow_tools else "none"}
        if self.use_fallbacks:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    def complete(self, request: LLMRequest, on_text: TextCallback | None = None) -> LLMResponse:
        import anthropic

        try:
            with self._sdk.beta.messages.stream(**self._params(request)) as stream:
                for event in stream:
                    if (
                        on_text is not None
                        and getattr(event, "type", "") == "content_block_delta"
                        and getattr(event.delta, "type", "") == "text_delta"
                    ):
                        on_text(event.delta.text)
                message = stream.get_final_message()
        except anthropic.AuthenticationError:
            raise LLMUnavailableError(
                "Khóa ANTHROPIC_API_KEY không hợp lệ; hãy dùng chế độ kịch bản."
            ) from None
        except anthropic.RateLimitError:
            raise LLMUnavailableError("Dịch vụ AI đang quá tải, vui lòng thử lại sau ít phút.") from None
        except anthropic.APIStatusError as exc:
            raise LLMUnavailableError(
                f"Dịch vụ AI trả lỗi (mã {exc.status_code}); hãy dùng chế độ kịch bản."
            ) from None
        except anthropic.APIConnectionError:
            raise LLMUnavailableError("Không kết nối được dịch vụ AI; hãy dùng chế độ kịch bản.") from None
        except ValueError:
            raise LLMUnavailableError("Mô hình trả về tham số công cụ hỏng; vui lòng thử lại.") from None
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in message.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                args = block.input if isinstance(block.input, dict) else {}
                calls.append(ToolCall(block.id, block.name, dict(args)))
        return LLMResponse("".join(text_parts), calls, str(message.stop_reason), list(message.content))


# ---------------------------------------------------------------- scripted


class ScriptStep(Protocol):
    tool: str

    def build_args(self, user_message: str, outputs: list[TurnOutput]) -> dict[str, Any]: ...


class Script(Protocol):
    plan_vi: str

    @property
    def steps(self) -> Sequence[ScriptStep]: ...

    def build_answer(self, user_message: str, outputs: list[TurnOutput]) -> str: ...


class ScriptedClient:
    """Replays a recorded scenario: one tool call per step, then the templated answer."""

    name = "scripted"

    def __init__(self, script: Script):
        self.script = script

    def complete(self, request: LLMRequest, on_text: TextCallback | None = None) -> LLMResponse:
        user_message = turn_user_message(request.messages)
        outputs = turn_outputs(request.messages)
        step_index = len(outputs)
        if (
            request.purpose == "agent"
            and request.allow_tools
            and step_index < len(self.script.steps)
            and all(o.error is None for o in outputs)
        ):
            step = self.script.steps[step_index]
            call = ToolCall(f"scripted-{step_index + 1}", step.tool, step.build_args(user_message, outputs))
            text = self.script.plan_vi if step_index == 0 else ""
            content: list[Any] = [{"type": "text", "text": text}] if text else []
            content.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.args})
            if on_text and text:
                on_text(text)
            return LLMResponse(text, [call], "tool_use", content)
        answer = self.script.build_answer(user_message, outputs)
        if on_text:
            on_text(answer)
        return LLMResponse(answer, [], "end_turn", [{"type": "text", "text": answer}])
