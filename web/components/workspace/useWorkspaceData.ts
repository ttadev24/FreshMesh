"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, errorMessage, getHealth, getMe, getSkus, getStores } from "@/lib/api";
import type { Health, Sku, Store, User } from "@/lib/types";

export interface WorkspaceData {
  me: User;
  health: Health;
  stores: Store[];
  skus: Sku[];
}

type State =
  | { status: "loading" }
  | { status: "error"; message: string; network: boolean }
  | { status: "ready"; data: WorkspaceData };

/** Loads the workspace context in parallel (no waterfall): health, me, stores, skus. */
export function useWorkspaceData() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    Promise.all([getHealth(ctrl.signal), getMe(ctrl.signal), getStores(ctrl.signal), getSkus(ctrl.signal)])
      .then(([health, me, stores, skus]) => setState({ status: "ready", data: { health, me, stores, skus } }))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        setState({ status: "error", message: errorMessage(err), network: err instanceof ApiError && err.isNetwork });
      });
    return () => ctrl.abort();
  }, [attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  return { state, retry };
}
