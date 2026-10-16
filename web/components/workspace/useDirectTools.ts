"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, errorMessage, getForecast, planInventory, planRoutes, planTransfer } from "@/lib/api";
import { sourced, type DashboardData } from "@/lib/dashboard";
import { normalizeForecast, normalizeInventory, normalizeRoutePlan, normalizeStockDecision } from "@/lib/normalize";

// Dashboard panels computed directly from the REST tool endpoints, from explicit buttons. These are the
// same real computations the agent's tools run (forecast model, Monte Carlo plans, PACO routing); no LLM
// is involved, so they stay usable when no LLM key is configured.

export type ToolSlot = keyof DashboardData;

export const TOOL_SLOTS = ["forecast", "inventory", "stock", "route"] as const satisfies readonly ToolSlot[];

/** Fixed scopes of the direct tools; draft requests reuse them so the server recomputes the same numbers. */
export const TOOL_SCOPE = {
  forecast: { categories: ["vegetable", "meat"], horizon_days: 7 },
  inventory: { categories: ["vegetable", "meat"], horizon_days: 1 },
  stock: { categories: ["vegetable"], now_hour: 14 },
  route: { now_minute: 0 },
} as const;

export const TOOL_META: Record<ToolSlot, { label: string; hint: string; endpoint: string }> = {
  forecast: { label: "Dự báo nhu cầu", hint: "Rau và thịt, 7 ngày tới, P10 đến P90", endpoint: "GET /api/forecast" },
  inventory: { label: "3 phương án nhập", hint: "Rau và thịt cho ngày mai", endpoint: "POST /api/inventory/plan" },
  stock: { label: "Giảm giá hay điều chuyển", hint: "Rau tồn lúc 14:00, so sánh tiền mặt", endpoint: "POST /api/transfer/plan" },
  route: { label: "Lộ trình giao", hint: "Gom đơn online đợt này, bộ giải PACO", endpoint: "POST /api/routing/plan" },
};

export type SlotState =
  | { status: "loading" }
  | { status: "error"; message: string; code: string }
  | { status: "ready" };

type StoreResults = { data: DashboardData; state: Partial<Record<ToolSlot, SlotState>> };

const EMPTY: StoreResults = { data: { forecast: null, inventory: null, stock: null, route: null }, state: {} };

async function compute(slot: ToolSlot, storeId: string, signal: AbortSignal): Promise<Partial<DashboardData>> {
  const endpoint = TOOL_META[slot].endpoint;
  switch (slot) {
    case "forecast": {
      const raw = await getForecast({ store_id: storeId, ...TOOL_SCOPE.forecast, categories: [...TOOL_SCOPE.forecast.categories] }, signal);
      return { forecast: sourced(normalizeForecast(raw), raw, endpoint) };
    }
    case "inventory": {
      const raw = await planInventory({ store_id: storeId, ...TOOL_SCOPE.inventory, categories: [...TOOL_SCOPE.inventory.categories] }, signal);
      return { inventory: sourced(normalizeInventory(raw), raw, endpoint) };
    }
    case "stock": {
      const raw = await planTransfer({ store_id: storeId, ...TOOL_SCOPE.stock, categories: [...TOOL_SCOPE.stock.categories] }, signal);
      return { stock: sourced(normalizeStockDecision(raw), raw, endpoint) };
    }
    case "route": {
      const raw = await planRoutes({ store_id: storeId, ...TOOL_SCOPE.route }, signal);
      const plan = normalizeRoutePlan(raw);
      if (!plan) throw new ApiError(502, "bad_route_plan", "Máy chủ trả lộ trình không đọc được, không vẽ bản đồ.");
      return { route: sourced(plan, raw, endpoint) };
    }
  }
}

/** Results of the direct tool buttons, kept per store so switching stores does not mix numbers. */
export function useDirectTools(storeId: string | null) {
  const [byStore, setByStore] = useState<Record<string, StoreResults>>({});
  const ctrls = useRef(new Map<string, AbortController>());

  useEffect(() => {
    const all = ctrls.current;
    return () => all.forEach((c) => c.abort());
  }, []);

  const update = useCallback((store: string, fn: (r: StoreResults) => StoreResults) => {
    setByStore((prev) => ({ ...prev, [store]: fn(prev[store] ?? EMPTY) }));
  }, []);

  // `forStore` lets a caller that is switching stores in the same event (a brief card about another store)
  // compute for the target store right away; results are kept per store either way.
  const run = useCallback(
    async (slot: ToolSlot, forStore?: string) => {
      const store = forStore ?? storeId;
      if (!store) return;
      const key = `${store}:${slot}`;
      ctrls.current.get(key)?.abort();
      const ctrl = new AbortController();
      ctrls.current.set(key, ctrl);
      update(store, (r) => ({ ...r, state: { ...r.state, [slot]: { status: "loading" } } }));
      try {
        const patch = await compute(slot, store, ctrl.signal);
        update(store, (r) => ({ data: { ...r.data, ...patch }, state: { ...r.state, [slot]: { status: "ready" } } }));
      } catch (err) {
        if (ctrl.signal.aborted) return;
        const code = err instanceof ApiError ? err.code : "unknown";
        update(store, (r) => ({ ...r, state: { ...r.state, [slot]: { status: "error", message: errorMessage(err), code } } }));
      } finally {
        if (ctrls.current.get(key) === ctrl) ctrls.current.delete(key);
      }
    },
    [storeId, update],
  );

  const current = storeId ? (byStore[storeId] ?? EMPTY) : EMPTY;
  return useMemo(() => ({ data: current.data, state: current.state, run }), [current, run]);
}

export type DirectTools = ReturnType<typeof useDirectTools>;
