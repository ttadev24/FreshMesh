import pytest

from agent.testing import InMemoryDraftStore
from agent.tools import (
    Tool,
    ToolContext,
    ToolError,
    ToolRegistry,
    ToolResult,
    validate_input,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "store_id": {"type": "string", "minLength": 1},
        "sku_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "horizon_days": {"type": "integer", "minimum": 1, "maximum": 7},
        "mode": {"type": "string", "enum": ["fast", "slow"]},
        "budget": {"type": "number"},
    },
    "required": ["store_id", "sku_ids"],
    "additionalProperties": False,
}
CTX = ToolContext(chain_id="CHAIN_A", actor="owner_a")


def _read_tool(name="forecast_demand"):
    def fn(args, ctx):
        return ToolResult(
            data={"store_id": args["store_id"], "p50": 12.5, "chain": ctx.chain_id},
            citations=["forecast:CHAIN_A"],
        )

    return Tool(name, "Dự báo nhu cầu", SCHEMA, "read", fn)


def _draft_tool():
    def fn(args, ctx):
        return ToolResult(data={"lines": [{"sku_id": "RAU1", "qty": args["qty"]}]}, citations=["plan:1"])

    schema = {"type": "object", "properties": {"qty": {"type": "integer"}}, "required": ["qty"]}
    return Tool("create_purchase_order", "Tạo nháp đơn đặt hàng", schema, "draft", fn)


def test_validate_input_accepts_valid_and_reports_all_errors():
    assert validate_input({"store_id": "S1", "sku_ids": ["A"], "horizon_days": 2}, SCHEMA) == []
    errors = validate_input(
        {"sku_ids": [], "horizon_days": 9, "mode": "x", "extra": 1, "budget": True}, SCHEMA
    )
    joined = "\n".join(errors)
    assert "store_id" in joined
    assert "sku_ids" in joined and "minItems" in joined
    assert "horizon_days" in joined and "maximum" in joined
    assert "mode" in joined and "enum" in joined
    assert "extra" in joined
    assert "budget" in joined  # bool is not a number


def test_validate_input_integer_rejects_float_and_bool():
    s = {"type": "integer"}
    assert validate_input(3, s) == []
    assert validate_input(3.5, s) != []
    assert validate_input(True, s) != []


def test_unsupported_schema_keyword_rejected_at_registration():
    bad = Tool("x_tool", "x", {"type": "object", "oneOf": [{}]}, "read", lambda a, c: ToolResult({}, []))
    with pytest.raises(ValueError, match="oneOf"):
        ToolRegistry().register(bad)


@pytest.mark.parametrize("kind", ["write", "action", "execute", "", "READ"])
def test_registry_refuses_other_kinds(kind):
    tool = Tool("t1", "x", {"type": "object"}, kind, lambda a, c: ToolResult({}, []))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="kind"):
        ToolRegistry().register(tool)


def test_registry_refuses_duplicates_and_bad_names():
    reg = ToolRegistry()
    reg.register(_read_tool())
    with pytest.raises(ValueError, match="đã được đăng ký|already"):
        reg.register(_read_tool())
    with pytest.raises(ValueError, match="name"):
        reg.register(Tool("bad name!", "x", {"type": "object"}, "read", lambda a, c: ToolResult({}, [])))


def test_read_tool_call_validates_and_returns_result():
    reg = ToolRegistry()
    reg.register(_read_tool())
    res = reg.call("forecast_demand", {"store_id": "S1", "sku_ids": ["A"]}, CTX)
    assert res.data["p50"] == 12.5 and res.data["chain"] == "CHAIN_A"
    assert res.citations == ["forecast:CHAIN_A"]
    with pytest.raises(ToolError) as ei:
        reg.call("forecast_demand", {"store_id": "S1"}, CTX)
    assert "sku_ids" in ei.value.message_vi
    with pytest.raises(ToolError, match="không tồn tại"):
        reg.call("nope", {}, CTX)


def test_draft_tool_only_creates_draft_via_store():
    store = InMemoryDraftStore()
    reg = ToolRegistry(draft_store=store)
    reg.register(_draft_tool())
    res = reg.call("create_purchase_order", {"qty": 40}, CTX)
    assert res.data["status"] == "draft"
    assert res.data["requires_approval"] is True
    draft_id = res.data["draft_id"]
    rec = store.drafts[draft_id]
    assert rec.status == "draft"
    assert rec.chain_id == "CHAIN_A" and rec.created_by == "owner_a" and rec.kind == "create_purchase_order"
    assert rec.payload == {"lines": [{"sku_id": "RAU1", "qty": 40}]}
    assert f"draft:{draft_id}" in res.citations


def test_draft_tool_without_store_fails_cleanly():
    reg = ToolRegistry()
    reg.register(_draft_tool())
    with pytest.raises(ToolError, match="bản nháp"):
        reg.call("create_purchase_order", {"qty": 1}, CTX)


def test_draft_fn_never_receives_store():
    seen = {}

    def fn(args, ctx):
        seen["ctx"] = ctx
        return ToolResult({"x": 1}, [])

    reg = ToolRegistry(draft_store=InMemoryDraftStore())
    reg.register(Tool("apply_markdown", "nháp", {"type": "object"}, "draft", fn))
    reg.call("apply_markdown", {}, CTX)
    values = list(vars(seen["ctx"]).values()) + list(seen["ctx"].extras.values())
    assert not any(hasattr(v, "create_draft") for v in values)


def test_tool_fn_exception_becomes_tool_error():
    def boom(args, ctx):
        raise RuntimeError("secret internals")

    reg = ToolRegistry()
    reg.register(Tool("boom", "x", {"type": "object"}, "read", boom))
    with pytest.raises(ToolError) as ei:
        reg.call("boom", {}, CTX)
    assert "secret internals" not in ei.value.message_vi


def test_tool_fn_must_return_tool_result():
    reg = ToolRegistry()
    reg.register(Tool("bad", "x", {"type": "object"}, "read", lambda a, c: {"x": 1}))  # type: ignore[arg-type,return-value]
    with pytest.raises(ToolError):
        reg.call("bad", {}, CTX)


def test_anthropic_definitions():
    reg = ToolRegistry()
    reg.register(_read_tool())
    reg.register(_draft_tool())
    defs = reg.definitions()
    names = [d["name"] for d in defs]
    assert names == ["forecast_demand", "create_purchase_order"]
    assert defs[0]["input_schema"] == SCHEMA
    assert "BẢN NHÁP" in defs[1]["description"]
    assert reg.names() == ["forecast_demand", "create_purchase_order"]
    assert "forecast_demand" in reg
