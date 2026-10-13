// Chooses what the right pane shows: either the outputs of a chat turn's tools, or the results of the
// dashboard's direct tool buttons (REST endpoints, no LLM). Classification is by payload shape, so the
// panels do not depend on which endpoint or tool name produced the data.

import {
  isForecastPayload,
  isInventoryPayload,
  isObj,
  isRoutePayload,
  isStockPayload,
  normalizeForecast,
  normalizeInventory,
  normalizeRoutePlan,
  normalizeStockDecision,
} from "./normalize";
import { mergeSources, sourcesOf } from "./provenance";
import type { AgentTurn, ForecastResponse, InventoryPlanResponse, RoutePlanView, SourceRef, StockDecision, ToolStep } from "./types";

export interface Sourced<T> {
  value: T;
  /** Tool that produced the value and its citations: shown in the "nguồn số liệu" tooltips. */
  tool: string;
  citations: string[];
  /** Data sources of the payload (`sources` / `source_labels_vi`), shown in tooltips and source lines. */
  sources: SourceRef[];
}

export interface DashboardData {
  forecast: Sourced<ForecastResponse> | null;
  inventory: Sourced<InventoryPlanResponse> | null;
  stock: Sourced<StockDecision> | null;
  route: Sourced<RoutePlanView> | null;
}

const EMPTY_DASHBOARD: DashboardData = { forecast: null, inventory: null, stock: null, route: null };

/** What one finished tool step contributes to the dashboard. */
type StepView = Partial<DashboardData>;

// Stream events replace the turn and the step they touch but keep every other ToolStep object, so the
// normalised view is cached per step: panels showing earlier tools keep identical props (no chart or map
// rebuild) while later events of the same turn arrive.
const stepCache = new WeakMap<ToolStep, StepView>();
const turnCache = new WeakMap<AgentTurn, DashboardData>();

function viewOfStep(t: ToolStep): StepView {
  let view = stepCache.get(t);
  if (view) return view;
  view = {};
  // Draft tools echo plan data in their payload: the proposal card shows those, not the dashboard.
  if (t.status === "done" && t.kind !== "draft" && isObj(t.data)) {
    const meta = { tool: t.name, citations: t.citations, sources: t.sources.length ? t.sources : sourcesOf(t.data) };
    const data = t.data;
    if (isForecastPayload(data)) {
      view.forecast = { value: normalizeForecast(data), ...meta };
    } else if (isInventoryPayload(data)) {
      view.inventory = { value: normalizeInventory(data), ...meta };
    } else if (isStockPayload(data)) {
      view.stock = { value: normalizeStockDecision(data), ...meta };
      // A routed transfer carries the trip's route plan: show it on the map too.
      const trip = isRoutePayload(data) ? normalizeRoutePlan(data) : null;
      if (trip) view.route = { value: trip, ...meta };
    } else if (isRoutePayload(data)) {
      // Checked after stock: a transfer plan embeds the route plan of its trip.
      const route = normalizeRoutePlan(data);
      if (route) view.route = { value: route, ...meta };
    }
  }
  stepCache.set(t, view);
  return view;
}

/** Markdown and transfer tools of one turn are shown as a single comparison. */
function mergeStock(prev: Sourced<StockDecision>, next: Sourced<StockDecision>): Sourced<StockDecision> {
  const a = prev.value;
  const b = next.value;
  return {
    value: {
      markdown: [...a.markdown, ...b.markdown.filter((m) => !a.markdown.some((p) => p.store_id === m.store_id && p.sku_id === m.sku_id))],
      transfer: b.transfer ?? a.transfer,
      comparisons: [...a.comparisons, ...b.comparisons],
      summary: b.summary ?? a.summary,
    },
    tool: `${prev.tool}, ${next.tool}`,
    citations: [...prev.citations, ...next.citations],
    sources: mergeSources(prev.sources, next.sources),
  };
}

export function dashboardFromTurn(turn: AgentTurn | null): DashboardData {
  if (!turn) return EMPTY_DASHBOARD;
  let out = turnCache.get(turn);
  if (out) return out;
  out = { forecast: null, inventory: null, stock: null, route: null };
  for (const t of turn.tools) {
    const v = viewOfStep(t);
    if (v.forecast) out.forecast = v.forecast;
    if (v.inventory) out.inventory = v.inventory;
    if (v.stock) out.stock = out.stock ? mergeStock(out.stock, v.stock) : v.stock;
    // A transfer's trip only fills the map when no routing tool has drawn it first.
    if (v.route && (!v.stock || !out.route)) out.route = v.route;
  }
  turnCache.set(turn, out);
  return out;
}

export const hasDashboardData = (d: DashboardData) => Boolean(d.forecast || d.inventory || d.stock || d.route);

/** Wraps one REST tool response for a dashboard panel (direct computation, no LLM in the loop). */
export function sourced<T>(value: T, raw: unknown, endpoint: string): Sourced<T> {
  return { value, tool: endpoint, citations: [], sources: sourcesOf(raw) };
}
