"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { decideInventory, errorMessage, inventoryScenario } from "@/lib/api";
import type { FrontierPoint, Goals, ScenarioResult, StudioPlan } from "@/lib/studio-types";
import { TOOL_SCOPE } from "@/components/workspace/useDirectTools";

/** Same scope as the dashboard's "3 phương án nhập": vegetables and meat for tomorrow. */
export const STUDIO_SCOPE = { categories: [...TOOL_SCOPE.inventory.categories], horizon_days: TOOL_SCOPE.inventory.horizon_days };

type Load<T> = { status: "idle" } | { status: "loading" } | { status: "ready"; value: T } | { status: "error"; message: string };

export interface Context {
  promo: boolean;
  holiday: boolean;
}

/** The frontier point that is the same order as a named plan (or the goal's choice); else the cheapest one. */
export function pointFor(plan: StudioPlan, name: string | null | undefined): FrontierPoint | undefined {
  if (!name) return undefined;
  const direct = plan.frontier.find((f) => f.name === name);
  if (direct) return direct;
  const option = plan.plans.find((p) => p.name === name);
  if (!option) return undefined;
  return plan.frontier.reduce<FrontierPoint | undefined>(
    (best, f) =>
      !best || Math.abs(f.total_cost_vnd - option.total_cost_vnd) < Math.abs(best.total_cost_vnd - option.total_cost_vnd) ? f : best,
    undefined,
  );
}

export function useStudio(storeId: string | null) {
  const [goals, setGoals] = useState<Goals>({});
  const [plan, setPlan] = useState<Load<StudioPlan>>({ status: "idle" });
  const [picked, setPicked] = useState<string | null>(null);
  const [context, setContext] = useState<Context>({ promo: false, holiday: false });
  const [scenario, setScenario] = useState<Load<ScenarioResult>>({ status: "idle" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!storeId) return;
    const ctrl = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading flag for the request started here
    setPlan({ status: "loading" });
    decideInventory({ store_id: storeId, ...STUDIO_SCOPE, ...goals }, ctrl.signal)
      .then((value) => {
        setPlan({ status: "ready", value });
        setPicked(value.goal_choice?.met ? value.goal_choice.name : (pointFor(value, value.recommended_plan)?.name ?? null));
      })
      .catch((err) => {
        if (!ctrl.signal.aborted) setPlan({ status: "error", message: errorMessage(err) });
      });
    return () => ctrl.abort();
  }, [storeId, goals, attempt]);

  useEffect(() => {
    if (!storeId || (!context.promo && !context.holiday)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- no scenario asked: clear the previous one
      setScenario({ status: "idle" });
      return;
    }
    const ctrl = new AbortController();
    setScenario({ status: "loading" });
    inventoryScenario({ store_id: storeId, ...STUDIO_SCOPE, promo: context.promo, is_holiday: context.holiday }, ctrl.signal)
      .then((value) => setScenario({ status: "ready", value }))
      .catch((err) => {
        if (!ctrl.signal.aborted) setScenario({ status: "error", message: errorMessage(err) });
      });
    return () => ctrl.abort();
  }, [storeId, context]);

  const value = plan.status === "ready" ? plan.value : null;
  const selected = useMemo(() => (value ? (pointFor(value, picked) ?? value.frontier[0]) : undefined), [value, picked]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return { goals, setGoals, plan, value, selected, pick: setPicked, context, setContext, scenario, retry };
}
