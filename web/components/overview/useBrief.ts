"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, errorMessage, getBrief } from "@/lib/api";
import type { Brief } from "@/lib/brief-types";

export type BriefState =
  | { status: "loading" }
  | { status: "ready"; brief: Brief }
  /** The API has no /api/brief yet (404): the overview keeps its own computations. */
  | { status: "unavailable" }
  | { status: "error"; message: string };

/** Morning brief of a store. The first call can take ~30 s while PACO solves; the server caches it per store. */
export function useBrief(storeId: string | null) {
  const [state, setState] = useState<{ store: string | null; value: BriefState }>({ store: storeId, value: { status: "loading" } });
  const [attempt, setAttempt] = useState(0);

  // A new store starts from loading (state derived during render, not in the effect).
  if (state.store !== storeId) setState({ store: storeId, value: { status: "loading" } });

  useEffect(() => {
    if (!storeId) return;
    const ctrl = new AbortController();
    getBrief(storeId, ctrl.signal)
      .then((brief) => setState({ store: storeId, value: { status: "ready", brief } }))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        const value: BriefState =
          err instanceof ApiError && err.status === 404
            ? { status: "unavailable" }
            : { status: "error", message: errorMessage(err) };
        setState({ store: storeId, value });
      });
    return () => ctrl.abort();
  }, [storeId, attempt]);

  const retry = useCallback(() => {
    setState((s) => ({ ...s, value: { status: "loading" } }));
    setAttempt((n) => n + 1);
  }, []);

  return { state: state.value, retry };
}
