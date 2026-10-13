from types import SimpleNamespace as NS

import anthropic
import httpx2
import pytest

from agent.llm import (
    DEFAULT_MODEL,
    FALLBACK_BETA,
    AnthropicClient,
    LLMRequest,
    LLMUnavailableError,
    configured_model,
    decode_tool_output,
    encode_tool_output,
    llm_available,
    tool_result_block,
    turn_outputs,
    turn_user_message,
)


def test_llm_available_and_model_from_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("FRESHMESH_LLM_MODEL", raising=False)
    assert llm_available() is False
    assert configured_model() == DEFAULT_MODEL == "claude-sonnet-5-5"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  ")
    assert llm_available() is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("FRESHMESH_LLM_MODEL", "claude-opus-5-5")
    assert llm_available() is True
    assert configured_model() == "claude-opus-5-5"


def test_missing_key_fails_gracefully_in_vietnamese(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMUnavailableError) as ei:
        AnthropicClient()
    assert "ANTHROPIC_API_KEY" in ei.value.message_vi and "kịch bản" in ei.value.message_vi


def test_client_constructs_with_key_without_network(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    client = AnthropicClient()
    assert client.model == DEFAULT_MODEL


class FakeStream:
    def __init__(self, events, final, error=None):
        self.events, self.final, self.error = events, final, error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        if self.error:
            raise self.error
        return iter(self.events)

    def get_final_message(self):
        return self.final


class FakeSDK:
    def __init__(self, stream):
        self.calls = []
        self._stream = stream
        self.beta = NS(messages=NS(stream=self._make))

    def _make(self, **kwargs):
        self.calls.append(kwargs)
        return self._stream


REQ = LLMRequest(
    "hệ thống",
    [{"role": "user", "content": "xin chào"}],
    [{"name": "forecast_demand", "description": "d", "input_schema": {"type": "object"}}],
)


def test_streaming_tool_use_translation():
    thinking = NS(type="thinking", thinking="", signature="sig")
    text = NS(type="text", text="Tôi sẽ dự báo.")
    tool = NS(type="tool_use", id="tu_1", name="forecast_demand", input={"store_id": "A1"})
    final = NS(content=[thinking, text, tool], stop_reason="tool_use")
    events = [
        NS(type="content_block_delta", delta=NS(type="text_delta", text="Tôi sẽ ")),
        NS(type="content_block_delta", delta=NS(type="input_json_delta", partial_json="{")),
        NS(type="content_block_delta", delta=NS(type="text_delta", text="dự báo.")),
    ]
    sdk = FakeSDK(FakeStream(events, final))
    client = AnthropicClient(sdk_client=sdk, model="claude-sonnet-5-5", use_fallbacks=True, effort="medium")
    chunks = []
    resp = client.complete(REQ, chunks.append)
    assert chunks == ["Tôi sẽ ", "dự báo."]
    assert resp.text == "Tôi sẽ dự báo." and resp.stop_reason == "tool_use"
    assert [(c.id, c.name, c.args) for c in resp.tool_calls] == [
        ("tu_1", "forecast_demand", {"store_id": "A1"})
    ]
    assert resp.assistant_content == [thinking, text, tool]  # echoed back verbatim (thinking preserved)
    params = sdk.calls[0]
    assert params["model"] == "claude-sonnet-5-5"
    assert params["tools"][0]["eager_input_streaming"] is True
    assert params["tool_choice"] == {"type": "auto"}
    assert params["betas"] == [FALLBACK_BETA] and params["fallbacks"] == "default"
    assert params["output_config"] == {"effort": "medium"}
    assert "thinking" not in params and "temperature" not in params


def test_tools_disabled_and_no_fallbacks():
    final = NS(content=[NS(type="text", text="ok")], stop_reason="end_turn")
    sdk = FakeSDK(FakeStream([], final))
    client = AnthropicClient(sdk_client=sdk, use_fallbacks=False)
    req = LLMRequest(REQ.system, REQ.messages, REQ.tools, allow_tools=False)
    client.complete(req)
    assert sdk.calls[0]["tool_choice"] == {"type": "none"}
    assert "betas" not in sdk.calls[0] and "fallbacks" not in sdk.calls[0]
    client.complete(LLMRequest(REQ.system, REQ.messages, []))
    assert "tools" not in sdk.calls[1] and "tool_choice" not in sdk.calls[1]


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")),
        ValueError("bad partial json"),
    ],
)
def test_sdk_errors_become_vietnamese(error):
    sdk = FakeSDK(FakeStream([], None, error=error))
    with pytest.raises(LLMUnavailableError) as ei:
        AnthropicClient(sdk_client=sdk).complete(REQ)
    assert ei.value.message_vi


def test_encode_decode_roundtrip_and_turn_outputs():
    data = {"rows": [{"store": "CH Quận 1", "units": 50}], "phone": "0901234567"}
    enc = encode_tool_output(data)
    assert decode_tool_output(enc) == {"rows": [{"store": "CH Quận 1", "units": 50}]}
    messages = [
        {"role": "user", "content": "lượt cũ"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "x", "name": "old", "input": {}}]},
        {"role": "user", "content": [tool_result_block("x", "1")]},
        {"role": "user", "content": "lượt mới"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "plan"},
                {"type": "tool_use", "id": "a", "name": "t1", "input": {"k": 1}},
                {"type": "tool_use", "id": "b", "name": "t2", "input": {}},
            ],
        },
        {
            "role": "user",
            "content": [tool_result_block("a", enc), tool_result_block("b", "Lỗi", is_error=True)],
        },
    ]
    outs = turn_outputs(messages)
    assert [(o.tool, o.args, o.error) for o in outs] == [("t1", {"k": 1}, None), ("t2", {}, "Lỗi")]
    assert outs[0].data["rows"][0]["units"] == 50
    assert turn_user_message(messages) == "lượt mới"


def test_real_sdk_accepts_request_parameters_offline():
    # A real SDK client pointed at a closed port: unknown kwargs would raise TypeError before any I/O.
    sdk = anthropic.Anthropic(api_key="sk-test", base_url="http://127.0.0.1:9", max_retries=0, timeout=2)
    with pytest.raises(LLMUnavailableError, match="kết nối"):
        AnthropicClient(sdk_client=sdk, use_fallbacks=True).complete(REQ)
