// Converts gateway JSON into the typed view models of lib/types.ts. Everything the UI renders goes
// through here, so a shape drift on the backend is fixed in one place and never reaches components
// as `undefined` numbers. Nothing here invents values: missing numbers stay `null` and are rendered
// as "không có dữ liệu".

import {
  ANSWER_SECTIONS,
  type AgentTurn,
  type AnswerSection,
  type Assumptions,
  type AtRiskOrder,
  type AuditEntry,
  type Comparison,
  type Draft,
  type DraftStatus,
  type DriftStatus,
  type FlNetwork,
  type ForecastResponse,
  type ForecastRow,
  type InventoryPlan,
  type InventoryPlanResponse,
  type LatLng,
  type MarkdownPlan,
  type PickupNode,
  type RoutePlanView,
  type RouteStop,
  type StockDecision,
  type ToolStep,
  type TransferPlan,
  type VehicleRoute,
} from "./types";

type Obj = Record<string, unknown>;

export const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const str = (v: unknown, fallback = ""): string => (typeof v === "string" ? v : v == null ? fallback : String(v));
export const num = (v: unknown): number | null => {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v);
  return null;
};
const num0 = (v: unknown) => num(v) ?? 0;
const pick = (o: Obj, ...keys: string[]): unknown => {
  for (const k of keys) if (o[k] !== undefined && o[k] !== null) return o[k];
  return undefined;
};
const strList = (v: unknown) => arr(v).map((x) => str(x)).filter(Boolean);

// ---------------------------------------------------------------- forecast

function toForecastRow(v: unknown): ForecastRow | null {
  if (!isObj(v)) return null;
  const p10 = num(v.p10), p50 = num(v.p50), p90 = num(v.p90);
  if (p10 === null || p50 === null || p90 === null) return null;
  const confidence = str(v.confidence);
  return {
    store_id: str(v.store_id),
    sku_id: str(v.sku_id),
    date: str(v.date),
    p10, p50, p90,
    confidence: (confidence === "Cao" || confidence === "Thấp" ? confidence : "Trung bình"),
    reason: str(v.reason),
  };
}

function toDrift(v: unknown): DriftStatus | null {
  if (!isObj(v)) return null;
  return {
    chain_id: str(v.chain_id) || undefined,
    store_id: str(v.store_id) || undefined,
    coverage_7d: num(v.coverage_7d),
    n_points: num(v.n_points) ?? undefined,
    alert: v.alert === true,
    message_vi: str(v.message_vi),
  };
}

export function isForecastPayload(v: unknown): boolean {
  if (!isObj(v)) return false;
  const rows = arr(v.rows ?? v.forecasts);
  return rows.length > 0 && isObj(rows[0]) && "p50" in (rows[0] as Obj);
}

export function normalizeForecast(raw: unknown): ForecastResponse {
  const o = isObj(raw) ? raw : { rows: raw };
  return {
    rows: arr(o.rows ?? o.forecasts).map(toForecastRow).filter((r): r is ForecastRow => r !== null),
    drift: toDrift(o.drift),
    source: str(o.source, "SIMULATED"),
  };
}

// ---------------------------------------------------------------- inventory plans

function toPlan(v: unknown): InventoryPlan | null {
  if (!isObj(v)) return null;
  return {
    name: str(v.name),
    label_vi: str(v.label_vi, str(v.name)),
    lines: arr(v.lines).filter(isObj).map((l) => ({
      store_id: str(l.store_id) || undefined,
      sku_id: str(l.sku_id),
      qty: num0(l.qty),
      cost_vnd: num0(l.cost_vnd),
      service_level_pct: num(l.service_level_pct) ?? undefined,
      expected_waste_units: num(l.expected_waste_units) ?? undefined,
      expected_shortage_units: num(l.expected_shortage_units) ?? undefined,
    })),
    total_cost_vnd: num0(v.total_cost_vnd),
    items_ordered: num(v.items_ordered) ?? undefined,
    expected_loss_vnd: num(v.expected_loss_vnd) ?? undefined,
    expected_waste_pct: num0(v.expected_waste_pct),
    expected_stockout_pct: num0(v.expected_stockout_pct),
    service_level_pct: num(v.service_level_pct) ?? undefined,
    constrained: v.constrained === true,
    rationale_vi: str(v.rationale_vi),
    assumptions_vi: strList(v.assumptions_vi),
  };
}

export function isInventoryPayload(v: unknown): boolean {
  if (!isObj(v)) return false;
  const plans = arr(v.plans);
  return plans.length > 0 && isObj(plans[0]) && "total_cost_vnd" in (plans[0] as Obj);
}

export function normalizeInventory(raw: unknown): InventoryPlanResponse {
  const o = isObj(raw) ? raw : { plans: raw };
  const plans = arr(o.plans).map(toPlan).filter((p): p is InventoryPlan => p !== null);
  const conf = str(o.confidence);
  const assumptions = strList(o.assumptions_vi);
  return {
    plans,
    recommended_plan: str(o.recommended_plan) || null,
    recommended_reason_vi: str(o.recommended_reason_vi) || null,
    confidence_reason: str(o.confidence_reason) || null,
    confidence: conf === "Cao" || conf === "Trung bình" || conf === "Thấp" ? conf : null,
    assumptions_vi: assumptions.length ? assumptions : [...new Set(plans.flatMap((p) => p.assumptions_vi ?? []))],
    source: str(o.source, "SIMULATED"),
  };
}

// ---------------------------------------------------------------- markdown / transfer

function toMarkdown(v: unknown): MarkdownPlan | null {
  if (!isObj(v) || !("schedule" in v)) return null;
  return {
    store_id: str(v.store_id),
    sku_id: str(v.sku_id),
    units_at_risk: num0(v.units_at_risk),
    schedule: arr(v.schedule).filter(isObj).map((s) => ({
      start: str(s.start),
      discount_pct: num0(s.discount_pct),
      price_vnd: num0(s.price_vnd),
      expected_units_sold: num0(s.expected_units_sold),
    })),
    expected_units_sold: num0(v.expected_units_sold),
    expected_units_wasted: num0(v.expected_units_wasted),
    recovered_revenue_vnd: num0(v.recovered_revenue_vnd),
    waste_cost_vnd: num0(v.waste_cost_vnd),
    net_value_vnd: num0(v.net_value_vnd),
    baseline_units_wasted: num0(v.baseline_units_wasted),
    cash_gain_vnd: num0(v.cash_gain_vnd),
    gain_vs_no_discount_vnd: num0(v.gain_vs_no_discount_vnd),
    rationale_vi: str(v.rationale_vi),
  };
}

function toTransfer(v: unknown): TransferPlan | null {
  if (!isObj(v) || !("net_saving_vnd" in v)) return null;
  return {
    from_store_id: str(v.from_store_id),
    lines: arr(v.lines).filter(isObj).map((l) => ({
      from_store_id: str(l.from_store_id),
      to_store_id: str(l.to_store_id),
      sku_id: str(l.sku_id),
      qty: num0(l.qty),
      value_vnd: num0(l.value_vnd),
      cash_value_vnd: num(l.cash_value_vnd),
      stockout_value_vnd: num(l.stockout_value_vnd),
    })),
    units_moved: num0(v.units_moved),
    destinations: num0(v.destinations),
    routed: v.routed === true,
    recommended: v.recommended === true,
    km: num0(v.km),
    vehicles: num0(v.vehicles),
    trip_cost_vnd: num0(v.trip_cost_vnd),
    saved_value_vnd: num0(v.saved_value_vnd),
    net_saving_vnd: num0(v.net_saving_vnd),
    saved_cash_vnd: num(v.saved_cash_vnd),
    stockout_avoided_value_vnd: num(v.stockout_avoided_value_vnd),
    unserved_store_ids: strList(v.unserved_store_ids),
    rationale_vi: str(v.rationale_vi),
  };
}

function toComparison(v: unknown): Comparison | null {
  if (!isObj(v) || !("markdown_gain_vnd" in v)) return null;
  const rec = str(v.recommended);
  return {
    store_id: str(v.store_id),
    sku_id: str(v.sku_id),
    markdown_gain_vnd: num0(v.markdown_gain_vnd),
    transfer_gain_vnd: num0(v.transfer_gain_vnd),
    difference_vnd: num0(v.difference_vnd),
    recommended: rec === "markdown" || rec === "transfer" ? rec : "none",
    recommendation_vi: str(v.recommendation_vi),
    transfer_stockout_value_vnd: num(v.transfer_stockout_value_vnd),
  };
}

/** Collects markdown plans, a transfer plan and comparisons wherever they sit in the payload. */
export function normalizeStockDecision(raw: unknown): StockDecision {
  const out: StockDecision = { markdown: [], transfer: null, comparisons: [], summary: null };
  const sum = isObj(raw) && isObj(raw.summary) ? raw.summary : null;
  if (sum && "markdown_gain_vnd" in sum) {
    const rec = str(sum.recommended);
    out.summary = {
      markdown_gain_vnd: num0(sum.markdown_gain_vnd),
      transfer_gain_vnd: num0(sum.transfer_gain_vnd),
      difference_vnd: num0(sum.difference_vnd),
      recommended: rec === "markdown" || rec === "transfer" ? rec : "none",
      recommendation_vi: str(sum.recommendation_vi),
      transfer_stockout_value_vnd: num(sum.transfer_stockout_value_vnd),
    };
  }
  const seenMarkdown = new Set<string>();
  const visit = (v: unknown, depth: number) => {
    if (depth > 4) return;
    if (Array.isArray(v)) return v.forEach((x) => visit(x, depth + 1));
    if (!isObj(v)) return;
    const md = toMarkdown(v);
    if (md) {
      const key = `${md.store_id}/${md.sku_id}`;
      if (!seenMarkdown.has(key)) out.markdown.push(md);
      seenMarkdown.add(key);
      return;
    }
    const tr = toTransfer(v);
    if (tr) {
      out.transfer = tr;
      return;
    }
    const cmp = toComparison(v);
    if (cmp) return void out.comparisons.push(cmp);
    Object.entries(v).forEach(([k, x]) => k !== "summary" && k !== "route_plan" && visit(x, depth + 1));
  };
  visit(raw, 0);
  return out;
}

export const isStockPayload = (v: unknown) => {
  const d = normalizeStockDecision(v);
  return d.markdown.length > 0 || d.transfer !== null || d.comparisons.length > 0;
};

// ---------------------------------------------------------------- routes

function toLatLng(v: unknown): LatLng | null {
  if (Array.isArray(v) && v.length >= 2) {
    const a = num(v[0]), b = num(v[1]);
    return a !== null && b !== null ? [a, b] : null;
  }
  if (isObj(v)) {
    const lat = num(v.lat), lng = num(pick(v, "lng", "lon"));
    return lat !== null && lng !== null ? [lat, lng] : null;
  }
  return null;
}

function toPath(v: unknown): LatLng[] {
  if (isObj(v)) return toPath(pick(v, "path", "coordinates", "polyline", "latlngs"));
  return arr(v).map(toLatLng).filter((p): p is LatLng => p !== null);
}

/** Locates the RoutePlan object inside a response (`{route_plan}`, `{plan}`, bare plan). */
function findRoutePlan(raw: unknown, depth = 0): Obj | null {
  if (!isObj(raw) || depth > 3) return null;
  if (Array.isArray(raw.routes) && ("road_km" in raw || "km" in raw || "vehicles_used" in raw)) return raw;
  for (const key of ["route_plan", "plan", "routing", "result", "data"]) {
    const found = findRoutePlan(raw[key], depth + 1);
    if (found) return found;
  }
  return null;
}

export const isRoutePayload = (v: unknown) => findRoutePlan(v) !== null;

export function normalizeRoutePlan(raw: unknown): RoutePlanView | null {
  const plan = findRoutePlan(raw);
  if (!plan) return null;
  const outer = isObj(raw) ? raw : {};
  const geometry = (isObj(plan.geometry) ? plan.geometry : isObj(outer.geometry) ? outer.geometry : {}) as Obj;

  // Coordinate index for stops: orders and pickup points may be listed next to the plan.
  const coords = new Map<string, LatLng>();
  const pickupPoints: PickupNode[] = [];
  for (const source of [plan, outer, geometry]) {
    for (const o of arr(pick(source, "orders", "order_points"))) {
      if (!isObj(o)) continue;
      const ll = toLatLng(o);
      if (ll) coords.set(str(o.order_id), ll);
    }
    for (const p of arr(pick(source, "pickup_points", "lockers"))) {
      if (!isObj(p)) continue;
      const ll = toLatLng(p);
      const id = str(pick(p, "pickup_point_id", "point_id", "id"));
      if (!ll || !id || pickupPoints.some((x) => x.pickup_point_id === id)) continue;
      pickupPoints.push({ pickup_point_id: id, name: str(p.name, id), lat: ll[0], lng: ll[1] });
      coords.set(`pp:${id}`, ll);
    }
  }

  const storeRaw = pick(plan, "store", "depot") ?? pick(outer, "store", "depot") ?? pick(geometry, "store", "depot");
  const storeLL = toLatLng(storeRaw);
  const store = storeLL
    ? { lat: storeLL[0], lng: storeLL[1], name: str(isObj(storeRaw) ? storeRaw.name : "", str(plan.store_id)) }
    : null;

  const geoRoutes = arr(pick(geometry, "routes", "polylines", "paths"));
  const routes: VehicleRoute[] = arr(plan.routes).map((r, index) => {
    const ro = isObj(r) ? r : { stops: r };
    const stops: RouteStop[] = arr(ro.stops).filter(isObj).map((s) => {
      const ppid = str(s.pickup_point_id) || null;
      const ll = toLatLng(s) ?? coords.get(str(s.order_id)) ?? (ppid ? coords.get(`pp:${ppid}`) : undefined) ?? null;
      return {
        order_id: str(s.order_id),
        kind: str(s.kind) === "pickup" ? "pickup" : "home",
        pickup_point_id: ppid,
        eta_min: num0(s.eta_min),
        late: s.late === true,
        lat: ll ? ll[0] : null,
        lng: ll ? ll[1] : null,
      };
    });
    let path = toPath(pick(ro, "path", "geometry", "polyline", "coordinates"));
    if (!path.length && geoRoutes[index] !== undefined) path = toPath(geoRoutes[index]);
    if (!path.length) {
      const pts = stops.filter((s) => s.lat !== null).map((s) => [s.lat, s.lng] as LatLng);
      // Only draw a path when every stop is located; otherwise the line would skip stops.
      if (pts.length === stops.length && pts.length > 0 && store) {
        path = [[store.lat, store.lng], ...pts, [store.lat, store.lng]];
      }
    }
    return { index: index + 1, stops, path, km: num(pick(ro, "km", "road_km")) };
  });

  const atRisk: AtRiskOrder[] = arr(plan.at_risk ?? outer.at_risk).filter(isObj).map((a) => {
    const ll = toLatLng(a) ?? coords.get(str(a.order_id)) ?? null;
    return {
      order_id: str(a.order_id),
      reason: str(a.reason),
      reason_vi: str(a.reason_vi) || AT_RISK_REASON_VI[str(a.reason)] || str(a.reason),
      lat: ll ? ll[0] : null,
      lng: ll ? ll[1] : null,
    };
  });

  return {
    store_id: str(plan.store_id),
    store,
    solver: str(plan.solver),
    runtime_s: num(plan.runtime_s),
    km: num0(pick(plan, "road_km", "km")),
    vehicles: num0(pick(plan, "vehicles_used", "vehicles")),
    exceeds_fleet: plan.exceeds_fleet === true,
    baseline_km: num(pick(plan, "baseline_km") ?? pick(outer, "baseline_km")),
    saving_pct: num(pick(plan, "saving_pct") ?? pick(outer, "saving_pct")),
    routes,
    at_risk: atRisk,
    pickup_points: pickupPoints,
  };
}

/** DESIGN.md §2 at-risk reasons. */
const AT_RISK_REASON_VI: Record<string, string> = {
  invalid_demand: "số lượng không hợp lệ",
  over_capacity: "vượt tải một xe",
  window_closed: "khung giờ đã qua",
  unreachable_in_window: "không kịp giao trong khung giờ",
  unknown_pickup_point: "điểm nhận không tồn tại",
};

// ---------------------------------------------------------------- drafts, audit, tabs

const DRAFT_STATUSES: DraftStatus[] = ["draft", "approved", "rejected", "dispatched"];

export function normalizeDraft(raw: unknown): Draft {
  const o = isObj(raw) && isObj(raw.draft) ? raw.draft : isObj(raw) ? raw : {};
  let payload: unknown = o.payload ?? o.payload_json;
  if (typeof payload === "string") {
    try {
      payload = JSON.parse(payload);
    } catch {
      payload = { text: payload };
    }
  }
  const status = str(o.status) as DraftStatus;
  return {
    draft_id: str(o.draft_id ?? o.id),
    kind: str(o.kind),
    kind_label_vi: str(o.kind_label_vi) || undefined,
    payload: isObj(payload) ? payload : {},
    status: DRAFT_STATUSES.includes(status) ? status : "draft",
    created_by: str(o.created_by) || undefined,
    created_at: str(o.created_at) || undefined,
    decided_at: str(o.decided_at) || null,
    decided_by: str(o.decided_by) || null,
  };
}

export function normalizeDrafts(raw: unknown): Draft[] {
  const list = Array.isArray(raw) ? raw : isObj(raw) ? arr(raw.drafts ?? raw.items) : [];
  return list.map(normalizeDraft).filter((d) => d.draft_id);
}

export function normalizeAudit(raw: unknown): AuditEntry[] {
  const list = Array.isArray(raw) ? raw : isObj(raw) ? arr(raw.entries ?? raw.items ?? raw.audit) : [];
  return list.filter(isObj).map((e, i) => {
    let payload: unknown = e.payload ?? e.payload_json ?? null;
    if (typeof payload === "string") {
      try {
        payload = JSON.parse(payload);
      } catch {
        // Keep the raw string.
      }
    }
    return {
      audit_id: num(e.audit_id) ?? i,
      ts: str(e.ts),
      actor: str(e.actor),
      event: str(e.event),
      payload,
    };
  });
}

export function normalizeFl(raw: unknown): FlNetwork {
  const o = isObj(raw) ? raw : {};
  const imp = isObj(o.improvement_vs_local) ? o.improvement_vs_local : {};
  const chains = Array.isArray(o.chains_participating) ? strList(o.chains_participating) : strList(o.chains);
  const metrics: FlNetwork["metrics"] = {};
  if (isObj(o.metrics)) {
    for (const [k, m] of Object.entries(o.metrics)) {
      if (!isObj(m)) continue;
      metrics[k] = {
        wape: num(m.wape),
        pinball: num(m.pinball),
        coverage: num(m.coverage),
        new_store_wape: num(m.new_store_wape),
        new_store_pinball: num(m.new_store_pinball),
      };
    }
  }
  return {
    chains,
    chains_participating: Array.isArray(o.chains_participating) ? chains.length : num0(o.chains_participating),
    improvement_vs_local: {
      wape: num(imp.wape),
      pinball: num(imp.pinball),
      new_store: num(imp.new_store),
      new_store_pinball: num(imp.new_store_pinball),
    },
    metrics,
    epsilon: num(o.epsilon),
    fl_model_deployed: o.fl_model_deployed === true,
    forecast_model_active: str(o.forecast_model_active) || "local",
    rounds: num(o.rounds),
    seeds: num(o.seeds),
    dp_curve: arr(o.dp_curve).filter(isObj).map((d) => ({ epsilon: num(d.epsilon), wape: num(d.wape), pinball: num(d.pinball) })),
    protocol_note_vi: str(o.protocol_note_vi),
  };
}

export function normalizeAssumptions(raw: unknown): Assumptions {
  const o = isObj(raw) ? raw : {};
  const sections = arr(o.sections).filter(isObj).map((s) => ({
    title: str(pick(s, "title", "heading")),
    body: str(pick(s, "body", "content", "markdown", "text")),
  }));
  // Fallback: a single markdown document split on its "## " headings.
  if (!sections.length) {
    const md = str(pick(o, "markdown", "content", "text"));
    for (const chunk of md.split(/^## /m).slice(1)) {
      const [title, ...rest] = chunk.split("\n");
      sections.push({ title: title.trim(), body: rest.join("\n").trim() });
    }
  }
  return {
    label: str(pick(o, "label", "source"), "SIMULATED"),
    sections,
    roadmap: strList(o.roadmap),
    parameters: arr(o.parameters).filter(isObj).map((p) => ({
      key: str(p.key),
      value: typeof p.value === "object" && p.value !== null ? JSON.stringify(p.value) : str(p.value),
      description_vi: str(p.description_vi),
    })),
  };
}

// ---------------------------------------------------------------- answer template

// Port of agent/template.py `_HEADING` (same optional markdown heading, bold and colon handling).
const HEADING = new RegExp(
  String.raw`^[ \t]*(?:#{1,6}[ \t]*)?\**[ \t]*(` + ANSWER_SECTIONS.join("|") + String.raw`)[ \t]*\**[ \t]*:?[ \t]*\**[ \t]*`,
  "gm",
);

function parseAnswer(text: string): Record<AnswerSection, string> | null {
  const normalized = text.normalize("NFC");
  const matches = [...normalized.matchAll(HEADING)];
  const found: Partial<Record<AnswerSection, string>> = {};
  for (let i = 0; i < matches.length; i++) {
    const m = matches[i];
    const name = m[1] as AnswerSection;
    if (found[name] !== undefined) return null;
    const end = i + 1 < matches.length ? matches[i + 1].index : normalized.length;
    found[name] = normalized.slice(m.index + m[0].length, end).trim();
  }
  if (ANSWER_SECTIONS.some((s) => !found[s])) return null;
  return found as Record<AnswerSection, string>;
}

function toSections(v: unknown): Record<AnswerSection, string> | null {
  if (!isObj(v)) return null;
  if (ANSWER_SECTIONS.some((s) => typeof v[s] !== "string")) return null;
  return Object.fromEntries(ANSWER_SECTIONS.map((s) => [s, v[s] as string])) as Record<AnswerSection, string>;
}

// ---------------------------------------------------------------- agent turn

export interface TurnEvent {
  type: string;
  data: unknown;
}

export function emptyTurn(userMessage: string): AgentTurn {
  return {
    turn_id: null,
    user_message: userMessage,
    plan: null,
    plan_steps: [],
    tools: [],
    answer: null,
    sections: null,
    unverified: [],
    drafts: [],
    citations: [],
    stop_reason: null,
    error_vi: null,
    done: false,
  };
}

/** Pure reducer over agent/loop.py StepEvents. */
export function applyTurnEvent(turn: AgentTurn, event: TurnEvent): AgentTurn {
  const d = isObj(event.data) ? event.data : {};
  switch (event.type) {
    case "plan":
      return {
        ...turn,
        plan: str(d.text),
        plan_steps: arr(d.steps).filter(isObj).map((s) => ({ tool: str(s.tool), description_vi: str(s.description_vi) })),
      };
    case "tool_call": {
      const step: ToolStep = {
        id: str(d.id, `${turn.tools.length}`),
        name: str(d.name),
        kind: str(d.kind),
        args: isObj(d.args) ? d.args : {},
        status: "running",
        data: null,
        error: null,
        citations: [],
      };
      return { ...turn, tools: [...turn.tools, step] };
    }
    case "tool_result": {
      const id = str(d.id);
      const error = typeof d.error === "string" ? d.error : null;
      const patch = (t: ToolStep): ToolStep => ({
        ...t,
        status: error ? "error" : "done",
        data: d.data ?? null,
        error,
        citations: strList(d.citations),
      });
      const exists = turn.tools.some((t) => t.id === id);
      const tools = exists
        ? turn.tools.map((t) => (t.id === id ? patch(t) : t))
        : [...turn.tools, patch({ id, name: str(d.name), kind: str(d.kind), args: {}, status: "running", data: null, error: null, citations: [] })];
      return { ...turn, tools };
    }
    case "unverified_flag": {
      const raw = str(d.raw);
      return raw && !turn.unverified.includes(raw) ? { ...turn, unverified: [...turn.unverified, raw] } : turn;
    }
    case "answer":
      return finishTurn(turn, d);
    case "error":
      return { ...turn, error_vi: str(d.message_vi ?? (isObj(d.error) ? d.error.message_vi : ""), "Lượt trả lời bị gián đoạn."), done: true };
    case "final":
    case "turn":
      return mergeTurnDict(turn, d);
    default:
      return turn;
  }
}

function finishTurn(turn: AgentTurn, d: Obj): AgentTurn {
  const text = str(d.text ?? d.answer_text);
  const unverified = strList(d.unverified);
  return {
    ...turn,
    answer: text || turn.answer,
    sections: toSections(d.sections) ?? (text ? parseAnswer(text) : null),
    unverified: unverified.length ? unverified : turn.unverified,
    drafts: strList(d.drafts).length ? strList(d.drafts) : turn.drafts,
    citations: strList(d.citations).length ? strList(d.citations) : turn.citations,
    stop_reason: str(d.stop_reason) || turn.stop_reason,
    error_vi: str(d.error_vi) || turn.error_vi,
    done: true,
  };
}

/** Merges an AgentTurn.to_dict() payload (scenario endpoint or final SSE event). */
function mergeTurnDict(turn: AgentTurn, d: Obj): AgentTurn {
  const inner = isObj(d.turn) ? d.turn : d;
  const events = arr(inner.events ?? d.events);
  let next = turn;
  if (events.length && !turn.tools.length) {
    for (const e of events) if (isObj(e)) next = applyTurnEvent(next, { type: str(e.type), data: e.data });
  }
  const calls = arr(inner.tool_calls).filter(isObj);
  if (calls.length) {
    // tool_calls carry full (unredacted) outputs: prefer them over streamed copies.
    next = {
      ...next,
      tools: calls.map((c, i) => ({
        id: str(c.id, `${i}`),
        name: str(c.name),
        kind: str(c.kind),
        args: isObj(c.args) ? c.args : {},
        status: typeof c.error === "string" && c.error ? "error" : "done",
        data: c.data ?? null,
        error: typeof c.error === "string" && c.error ? c.error : null,
        citations: strList(c.citations),
      })),
    };
  }
  return {
    ...finishTurn(next, inner),
    turn_id: str(inner.turn_id) || next.turn_id,
    user_message: str(inner.user_message) || next.user_message,
    plan: str(inner.plan_vi) || next.plan,
    plan_steps: arr(inner.plan_steps).length
      ? arr(inner.plan_steps).filter(isObj).map((s) => ({ tool: str(s.tool), description_vi: str(s.description_vi) }))
      : next.plan_steps,
  };
}

export function normalizeTurn(raw: unknown): AgentTurn {
  return mergeTurnDict(emptyTurn(""), isObj(raw) ? raw : {});
}
