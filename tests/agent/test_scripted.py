from datetime import UTC, datetime

import pytest

from agent.audit import AuditLog
from agent.guardrail import fmt_num, fmt_pct, fmt_vnd
from agent.scripted import (
    Scenario,
    ScenarioRegistry,
    ScenarioStep,
    register_scenario,
    run_scenario,
    stream_scenario,
)
from agent.testing import InMemoryDraftStore
from agent.tools import Tool, ToolContext, ToolError, ToolRegistry, ToolResult

CTX = ToolContext(chain_id="CHAIN_A", actor="owner_a")
OBJ = {"type": "object"}


def _registry(store, fail=False):
    reg = ToolRegistry(draft_store=store)

    def forecast(args, ctx):
        if fail:
            raise ToolError("Không có dữ liệu cho cửa hàng.")
        return ToolResult(
            {"rows": [{"sku_id": "RAU1", "p10": 80.2, "p50": 101.6, "p90": 131.9}]}, ["forecast"]
        )

    def plan(args, ctx):
        p50 = args["p50"]
        return ToolResult(
            {
                "plans": [
                    {"name": "An toàn", "qty": 132, "total_cost_vnd": 1_056_000, "expected_waste_pct": 0.083},
                    {
                        "name": "Cân bằng",
                        "qty": round(p50) + 8,
                        "total_cost_vnd": 878_400,
                        "expected_waste_pct": 0.041,
                    },
                ]
            },
            ["plan_inventory"],
        )

    def po(args, ctx):
        return ToolResult({"lines": [{"sku_id": "RAU1", "qty": args["qty"]}]}, [])

    reg.register(Tool("forecast_demand", "Dự báo", OBJ, "read", forecast))
    reg.register(Tool("plan_inventory", "Lập 3 phương án nhập", OBJ, "read", plan))  # as the real tool
    reg.register(Tool("create_purchase_order", "Nháp đơn", OBJ, "draft", po))
    return reg


def _answer(ctx):
    plans = ctx.output("plan_inventory")["plans"]
    bal = plans[1]
    row = ctx.output("forecast_demand")["rows"][0]
    draft = ctx.output("create_purchase_order")["draft_id"]
    return {
        "Đề xuất": f"Chọn phương án {bal['name']}: nhập {fmt_num(bal['qty'])} kg, {fmt_vnd(bal['total_cost_vnd'])}.",
        "Vì sao": f"P50 {fmt_num(row['p50'], 1)} kg (P10 {fmt_num(row['p10'], 1)} – P90 {fmt_num(row['p90'], 1)}); "
        f"hàng bỏ dự kiến {fmt_pct(bal['expected_waste_pct'])} so với {fmt_pct(plans[0]['expected_waste_pct'])}.",
        "Độ tin cậy": "Trung bình.",
        "Giả định": f"So sánh {len(plans)} phương án; dữ liệu giả lập.",
        "Việc cần bạn duyệt": f"Bản nháp đơn đặt hàng `{draft}`.",
    }


SCENARIO = Scenario(
    key="1",
    title_vi="Sáng, nhập hàng",
    prompt_vi="Nhập rau và thịt cho mai thế nào?",
    plan_vi="Dự báo nhu cầu ngày mai, lập 3 phương án nhập, tạo nháp đơn theo phương án Cân bằng.",
    steps=(
        ScenarioStep("forecast_demand", {"store_id": "A1", "sku_ids": ["RAU1"], "horizon_days": 1}),
        ScenarioStep("plan_inventory", lambda c: {"p50": c.output("forecast_demand")["rows"][0]["p50"]}),
        ScenarioStep(
            "create_purchase_order", lambda c: {"qty": c.output("plan_inventory")["plans"][1]["qty"]}
        ),
    ),
    answer=_answer,
)


def test_scenario_runs_end_to_end_with_verified_numbers(tmp_path):
    store = InMemoryDraftStore()
    audit = AuditLog(tmp_path / "a.sqlite", clock=lambda: datetime(2026, 10, 1, tzinfo=UTC))
    turn = run_scenario(SCENARIO, _registry(store), CTX, audit=audit, turn_id_factory=lambda: "s1")
    assert [c.name for c in turn.tool_calls] == ["forecast_demand", "plan_inventory", "create_purchase_order"]
    assert turn.tool_calls[1].args == {"p50": 101.6}
    assert turn.tool_calls[2].args == {"qty": 110}
    assert turn.plan_vi == SCENARIO.plan_vi
    assert turn.unverified == [] and turn.template_ok and not turn.rewritten
    assert "878.400 đ" in turn.answer_text and "4,1%" in turn.answer_text
    assert turn.drafts == ["draft-1"] and store.executed() == []
    assert [e.event for e in audit.turn("CHAIN_A", "s1")] == [
        "command",
        "plan",
        "tool_call",
        "tool_call",
        "tool_call",
        "answer",
    ]


def test_stream_scenario_event_order():
    events = list(stream_scenario(SCENARIO, _registry(InMemoryDraftStore()), CTX))
    assert [e.type for e in events] == ["plan"] + ["tool_call", "tool_result"] * 3 + ["answer"]


def test_failed_step_stops_and_answers_with_error():
    turn = run_scenario(SCENARIO, _registry(InMemoryDraftStore(), fail=True), CTX)
    assert len(turn.tool_calls) == 1
    assert turn.template_ok and "Không có dữ liệu" in turn.sections["Vì sao"]
    assert turn.drafts == []


def test_registry_by_key_and_missing_tools():
    scenarios = ScenarioRegistry()
    register_scenario(SCENARIO, scenarios=scenarios)
    with pytest.raises(ValueError):
        register_scenario(SCENARIO, scenarios=scenarios)
    register_scenario(SCENARIO, scenarios=scenarios, replace=True)
    assert scenarios.keys() == ["1"]
    turn = run_scenario("1", _registry(InMemoryDraftStore()), CTX, scenarios=scenarios)
    assert turn.unverified == []
    with pytest.raises(KeyError):
        run_scenario("9", _registry(InMemoryDraftStore()), CTX, scenarios=scenarios)
    with pytest.raises(ValueError, match="unregistered"):
        run_scenario(SCENARIO, ToolRegistry(), CTX)
