"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, errorMessage } from "@/lib/api";

export type ResourceState<T> = { status: "loading" } | { status: "error"; message: string; code: string } | { status: "ready"; data: T };
type State<T> = ResourceState<T>;

export interface Resource<T> {
  state: ResourceState<T>;
  retry: () => void;
}

/** Fetch-on-mount with abort, retry and a reload key. */
export function useResource<T>(fetcher: (signal: AbortSignal) => Promise<T>, reloadKey: unknown = 0): Resource<T> {
  const [state, setState] = useState<State<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset to loading for the fetch started here
    setState((prev) => (prev.status === "loading" ? prev : { status: "loading" }));
    fetcher(ctrl.signal)
      .then((data) => setState({ status: "ready", data }))
      .catch((err) => {
        if (!ctrl.signal.aborted) setState({ status: "error", message: errorMessage(err), code: err instanceof ApiError ? err.code : "unknown" });
      });
    return () => ctrl.abort();
  }, [fetcher, reloadKey, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return useMemo(() => ({ state, retry }), [state, retry]);
}
