"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { decideInventory, errorMessage, inventoryScenario } from "@/lib/api";
import type { Choice, FrontierPoint, Goals, ScenarioResult, StudioPlan } from "@/lib/studio-types";
import { TOOL_SCOPE } from "@/components/workspace/useDirectTools";

/** Same scope as the dashboard's "3 phương án nhập": vegetables and meat for tomorrow. */
export const STUDIO_SCOPE = { categories: [...TOOL_SCOPE.inventory.categories], horizon_days: TOOL_SCOPE.inventory.horizon_days };

type Load<T> = { status: "idle" } | { status: "loading" } | { status: "ready"; value: T } | { status: "error"; message: string };

export interface Context {
  promo: boolean;
  holiday: boolean;
}

/** A pick by name: a frontier point ("target_80") or a named plan ("balanced"); both can become a purchase order. */
export function choiceFor(plan: StudioPlan, name: string | null | undefined): Choice | undefined {
  if (!name) return undefined;
  const point = plan.frontier.find((f) => f.name === name);
  if (point) return point;
  const option = plan.plans.find((p) => p.name === name);
  return option ? { ...option, expected_leftover_units: option.expected_leftover_units ?? 0 } : undefined;
}

/** The frontier point closest in money to a pick (where the slider rests for a named plan). */
export function nearestPoint(plan: StudioPlan, c: Choice | undefined): FrontierPoint | undefined {
  if (!c) return undefined;
  return plan.frontier.reduce<FrontierPoint | undefined>(
    (best, f) =>
      !best || Math.abs(f.total_cost_vnd - c.total_cost_vnd) < Math.abs(best.total_cost_vnd - c.total_cost_vnd) ? f : best,
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
        setPicked(value.goal_choice?.met ? value.goal_choice.name : value.recommended_plan);
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
  const selected = useMemo(() => (value ? (choiceFor(value, picked) ?? value.frontier[0]) : undefined), [value, picked]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return { goals, setGoals, plan, value, selected, pick: setPicked, context, setContext, scenario, retry };
}
