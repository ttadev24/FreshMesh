"""The three demo flows as ``agent.scripted.Scenario`` objects over the REAL tools, plus a rule-based
Vietnamese intent router for chat in ``scripted`` mode (no LLM, no network besides the solver).

Each answer is templated from this turn's read-tool outputs and formatted with ``agent.guardrail``
helpers, so ``verify_numbers`` passes; drafts are only created, never executed.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from agent.guardrail import fmt_num, fmt_pct, fmt_vnd
from agent.scripted import Scenario, ScenarioContext, ScenarioStep
from api.errors import ApiError
from api.repo import ChainRepo, resolve_store_id
from api.services import Services

FLOW_TITLES_VI = {
    1: "Sáng, nhập hàng",
    2: "Chiều, xử lý tồn",
    3: "Giao online theo đợt",
}
FLOW_PROMPTS_VI = {
    1: "Nhập rau và thịt cho mai thế nào?",
    2: "Còn nhiều rau ở {store}",
    3: "Gom đơn online đợt này và tính lộ trình giao",
}
DEFAULT_CATEGORIES = {1: ("vegetable", "meat"), 2: ("vegetable",), 3: ()}
_CATEGORY_WORDS = (
    ("vegetable", ("rau", "rau củ", "cà chua", "xà lách")),
    ("meat", ("thịt", "heo", "bò", "gà")),
    ("seafood", ("cá", "tôm", "hải sản")),
    ("egg", ("trứng",)),
    ("dairy", ("sữa chua",)),
    ("tofu", ("đậu hũ", "đậu phụ")),
)
UNKNOWN_INTENT_VI = (
    "Chế độ kịch bản (không dùng AI) chỉ hiểu 3 luồng: "
    'nhập hàng (ví dụ "Nhập rau và thịt cho mai thế nào?"), '
    'xử lý tồn (ví dụ "Còn nhiều rau ở CH3") và giao online (ví dụ "Gom đơn và tính lộ trình giao"). '
    "Hãy diễn đạt lại hoặc dùng các nút chức năng."
)


def _has(text: str, *words: str) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text) for w in words)


@dataclass(frozen=True)
class Intent:
    flow: int
    store: str | None
    categories: tuple[str, ...]


def detect_intent(message: str) -> Intent | None:
    m = unicodedata.normalize("NFC", message).lower()
    store_m = re.search(r"\b(?:([a-z])\s*-\s*)?ch\s*(\d+)\b", m)
    store = None
    if store_m:
        short = f"CH{int(store_m.group(2))}"
        store = f"{store_m.group(1).upper()}-{short}" if store_m.group(1) else short
    cats = tuple(c for c, words in _CATEGORY_WORDS if _has(m, *words))
    if _has(
        m, "gom đơn", "lộ trình", "giao hàng", "giao online", "đơn online", "shipper", "tuyến giao", "điều xe"
    ):
        return Intent(3, store, ())
    if _has(
        m,
        "còn nhiều",
        "dư",
        "tồn nhiều",
        "sắp hết hạn",
        "ế",
        "giảm giá",
        "điều chuyển",
        "xả hàng",
        "hàng tồn",
    ):
        return Intent(2, store, cats)
    if _has(m, "nhập", "đặt hàng", "mua hàng", "phương án nhập", "nhập hàng"):
        return Intent(1, store, cats)
    return None


# ---------------------------------------------------------------- answers


def _flow1_answer(c: ScenarioContext) -> dict[str, str]:
    plan = c.output("plan_inventory")
    fc = c.output("forecast_demand")
    draft = c.output("create_purchase_order")
    rec = next(p for p in plan["plans"] if p["name"] == plan["recommended_plan"])
    options = "; ".join(
        f"{p['label_vi']} {fmt_vnd(p['total_cost_vnd'])} (bỏ {fmt_pct(p['expected_waste_pct'] / 100)}, "
        f"hết hàng {fmt_pct(p['expected_stockout_pct'] / 100)})"
        for p in plan["plans"]
    )
    bought = [ln for ln in rec["lines"] if ln["qty"] > 0]
    lines = ", ".join(f"{ln['sku_name']} {ln['qty']}" for ln in bought) or "không cần nhập thêm"
    forecast = "; ".join(
        f"{r['sku_name']}: P10 {fmt_num(r['p10'], 1)} · P50 {fmt_num(r['p50'], 1)} · P90 "
        f"{fmt_num(r['p90'], 1)}"
        for r in fc["rows"]
    )
    return {
        "Đề xuất": (
            f"Chọn phương án {rec['label_vi']} cho {plan['store_name']} (hàng về ngày {plan['order_date']}): "
            f"nhập {rec['items_ordered']} mặt hàng, tổng {fmt_vnd(rec['total_cost_vnd'])}, dự kiến bỏ "
            f"{fmt_pct(rec['expected_waste_pct'] / 100)}, hết hàng "
            f"{fmt_pct(rec['expected_stockout_pct'] / 100)}. "
            f"Số lượng: {lines}. Ba phương án: {options}."
        ),
        "Vì sao": (
            f"{plan['recommended_reason_vi']} Dự báo nhu cầu ngày {plan['order_date']} (đơn vị): {forecast}. "
            f"{rec['rationale_vi']}"
        ),
        "Độ tin cậy": f"{plan['confidence']} — {plan['confidence_reason']} {plan['drift']['message_vi']}",
        "Giả định": " ".join(plan["assumptions_vi"]),
        "Việc cần bạn duyệt": (
            f"Bản nháp đơn đặt hàng `{draft['draft_id']}` theo phương án {rec['label_vi']}: bấm "
            "Duyệt để lập đơn đặt hàng, Sửa để đổi phương án hoặc số lượng, Bỏ nếu không nhập. "
            "Hệ thống không tự đặt hàng."
        ),
    }


def _flow2_answer(c: ScenarioContext) -> dict[str, str]:
    md = c.output("suggest_markdown")
    tr = c.output("transfer_stock")
    s, t = tr["summary"], tr["transfer"]
    if s["recommended"] == "transfer":
        dest = ", ".join(f"{ln['to_store_name']} {ln['sku_name']} {ln['qty']}" for ln in t["lines"])
        proposal = (
            f"Điều chuyển {t['units_moved']} đơn vị từ {tr['store_name']} sang {t['destinations']} "
            f"cửa hàng đang thiếu ({dest}) bằng {t['vehicles']} xe, quãng đường {fmt_num(t['km'], 1)} km. "
            f"{s['recommendation_vi']}"
        )
        todo_kind = "phiếu điều chuyển"
        draft = c.output("create_transfer")
    elif s["recommended"] == "markdown":
        items = "; ".join(
            f"{p['sku_name']}: "
            + ", ".join(f"{x['discount_pct']}% từ {x['start'][11:16]}" for x in _steps(p["schedule"]))
            for p in md["plans"]
        )
        proposal = (
            f"Giảm giá theo khung giờ cho {len(md['plans'])} mặt hàng ({md['units_at_risk_total']} "
            f"đơn vị hết hạn hôm nay): {items}. {s['recommendation_vi']}"
        )
        todo_kind = "lịch giảm giá"
        draft = c.output("apply_markdown")
    else:
        proposal = s["recommendation_vi"] + " Giữ nguyên giá và không điều chuyển."
        todo_kind, draft = "", None
    per_sku = " ".join(cmp["recommendation_vi"] for cmp in tr["comparisons"])
    why = (
        "So sánh bằng tiền mặt so với không làm gì, trên cùng số hàng hết hạn hôm nay còn lại lúc này: "
        f"giảm giá lợi thêm {fmt_vnd(s['markdown_gain_vnd'])}, "
        f"điều chuyển lợi thêm {fmt_vnd(s['transfer_gain_vnd'])} (chênh {fmt_vnd(s['difference_vnd'])}); "
        "phạt mất khách khi hết hàng không phải tiền mặt nên không cộng vào so sánh. "
        f"Nếu chỉ xét riêng điều chuyển (so với không làm gì): {t['rationale_vi']} {per_sku}"
    )
    todo = (
        f"Bản nháp {todo_kind} `{draft['draft_id']}`: bấm Duyệt để thực hiện, Sửa để chỉnh, Bỏ để hủy. "
        "Hệ thống không tự thực hiện."
        if draft
        else "Không có."
    )
    return {
        "Đề xuất": proposal,
        "Vì sao": why,
        "Độ tin cậy": (
            f"{tr['confidence']} — theo dự báo kém chắc chắn nhất, {tr['confidence_reason']} "
            "Hệ số co giãn giá là giả định chưa hiệu chỉnh bằng dữ liệu thật; chi phí chuyến tính "
            "từ lộ trình PACO."
            if tr["confidence"]
            else "Thấp — không có mặt hàng nào có dự báo để đánh giá."
        ),
        "Giả định": " ".join(tr["assumptions_vi"]),
        "Việc cần bạn duyệt": todo,
    }


def _steps(schedule: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for slot in schedule:
        if not out or out[-1]["discount_pct"] != slot["discount_pct"]:
            out.append(slot)
    return out


def _flow3_answer(c: ScenarioContext) -> dict[str, str]:
    r = c.output("optimize_routes")
    draft = c.output("dispatch_routes")
    vehicles = "; ".join(
        f"{v['vehicle_label']}: {v['n_stops']} điểm dừng, {v['units']} đơn vị hàng" for v in r["routes"]
    )
    risk = (
        "Đơn có nguy cơ (không đưa vào lộ trình, cần bạn xử lý): "
        + ", ".join(f"`{a['order_id']}` ({a['reason_vi']})" for a in r["at_risk"])
        + "."
        if r["at_risk"]
        else "Không có đơn nào có nguy cơ trễ."
    )
    saving = (
        f", tiết kiệm {fmt_pct(r['saving_pct'] / 100)} ({fmt_num(r['saving_km'], 1)} km)"
        if r["saving_pct"] is not None
        else ""
    )
    fleet = " Số xe cần VƯỢT số xe hiện có." if r["exceeds_fleet"] else ""
    deferred = r["batch"]["deferred_order_ids"]
    if deferred:
        fleet += f" {len(deferred)} đơn vượt giới hạn mỗi đợt được dời sang đợt sau."
    cached = " Kết quả lấy từ bộ nhớ đệm của cùng đợt đơn." if r["cached"] else ""
    return {
        "Đề xuất": (
            f"Gửi lộ trình đợt giao bắt đầu {r['batch']['batch_start'][11:16]} cho "
            f"{r['orders_routed']} đơn bằng {r['vehicles']} xe, tổng {fmt_num(r['km'], 1)} km.{fleet} {risk}"
        ),
        "Vì sao": (
            f"PACO gom {r['batch']['n_orders']} đơn của đợt thành lộ trình nhiều điểm dừng: "
            f"{fmt_num(r['km'], 1)} km so với {fmt_num(r['baseline_km'], 1)} km nếu mỗi đơn một chuyến"
            f"{saving}. {vehicles}. "
            f"Thời gian giải {fmt_num(r['runtime_s'], 1)} giây.{cached}"
        ),
        "Độ tin cậy": f"{r['confidence']} — {r['confidence_reason']}",
        "Giả định": " ".join(r["assumptions_vi"]),
        "Việc cần bạn duyệt": (
            f"Bản nháp gửi lộ trình `{draft['draft_id']}`: bấm Duyệt để gửi cho shipper, Bỏ để hủy. "
            "Hệ thống không tự gửi."
        ),
    }


# ---------------------------------------------------------------- scenario builders


def build_scenario(
    flow: int,
    services: Services,
    *,
    chain_id: str,
    store_id: str,
    categories: tuple[str, ...] = (),
    now_minute: int = 0,
) -> Scenario:
    cats = list(categories or DEFAULT_CATEGORIES[flow])
    base = {"store_id": store_id}
    if flow == 1:

        def po_args(c: ScenarioContext) -> dict[str, Any]:
            return {**base, "categories": cats, "plan_name": c.output("plan_inventory")["recommended_plan"]}

        return Scenario(
            key="1",
            title_vi=FLOW_TITLES_VI[1],
            prompt_vi=FLOW_PROMPTS_VI[1],
            plan_vi="Kế hoạch: dự báo nhu cầu ngày mai → lập 3 phương án nhập → tạo bản nháp đơn "
            "đặt hàng để bạn duyệt.",
            steps=(
                ScenarioStep("forecast_demand", {**base, "categories": cats}),
                ScenarioStep("plan_inventory", {**base, "categories": cats}),
                ScenarioStep("create_purchase_order", po_args),
            ),
            answer=_flow1_answer,
        )
    if flow == 2:
        steps = [
            ScenarioStep("suggest_markdown", {**base, "categories": cats}),
            ScenarioStep("transfer_stock", {**base, "categories": cats}),
        ]
        # The draft kind depends on the money comparison; it is decided from the same deterministic,
        # cached computation the transfer_stock step returns.
        try:
            repo = services.repo(chain_id)
            decision = services.transfer(chain_id, store_id, repo.select_skus(None, cats))["summary"][
                "recommended"
            ]
        except ApiError:
            decision = "none"  # the transfer_stock step reports the error itself
        if decision == "transfer":
            steps.append(ScenarioStep("create_transfer", {**base, "categories": cats}))
        elif decision == "markdown":
            steps.append(ScenarioStep("apply_markdown", {**base, "categories": cats}))
        return Scenario(
            key="2",
            title_vi=FLOW_TITLES_VI[2],
            prompt_vi=FLOW_PROMPTS_VI[2],
            plan_vi="Kế hoạch: tính lịch giảm giá theo khung giờ → tính điều chuyển sang cửa hàng "
            "thiếu (PACO) → so sánh bằng tiền → tạo bản nháp cho cách có lợi hơn.",
            steps=tuple(steps),
            answer=_flow2_answer,
        )
    if flow == 3:

        def dispatch_args(c: ScenarioContext) -> dict[str, Any]:
            return {
                **base,
                "now_minute": now_minute,
                "route_plan_id": c.output("optimize_routes")["route_plan_id"],
            }

        return Scenario(
            key="3",
            title_vi=FLOW_TITLES_VI[3],
            prompt_vi=FLOW_PROMPTS_VI[3],
            plan_vi="Kế hoạch: gom đơn online của đợt hiện tại → tính lộ trình PACO có điểm nhận → "
            "tạo bản nháp gửi lộ trình để bạn duyệt.",
            steps=(
                ScenarioStep("optimize_routes", {**base, "now_minute": now_minute}),
                ScenarioStep("dispatch_routes", dispatch_args),
            ),
            answer=_flow3_answer,
        )
    raise ApiError(404, "unknown_scenario", "Kịch bản chỉ có 1, 2 hoặc 3.")


def default_store(
    flow: int, repo: ChainRepo, *, role: str, own_store: str | None, requested: str | None
) -> str:
    """Store of a flow: explicit request > manager's own store > CH3 for flow 2 > the chain's first store."""
    if requested:
        return resolve_store_id(repo, requested, default=None)
    if role != "owner" and own_store:
        return own_store
    if flow == 2:
        try:
            return resolve_store_id(repo, "CH3", default=None)
        except ApiError:
            pass
    return resolve_store_id(repo, None, default=None)


def flow_message(flow: int, store_id: str) -> str:
    return FLOW_PROMPTS_VI[flow].format(store=store_id.split("-", 1)[-1])
