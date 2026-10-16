"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, errorMessage, getNetwork } from "@/lib/api";
import type { NetworkView } from "@/lib/brief-types";

export type NetworkState =
  | { status: "loading" }
  | { status: "ready"; view: NetworkView }
  /** The API has no /api/network yet (404): the page falls back to the FL summary tab. */
  | { status: "unavailable" }
  | { status: "error"; message: string };

export function useNetwork() {
  const [state, setState] = useState<NetworkState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    getNetwork(ctrl.signal)
      .then((view) => setState({ status: "ready", view }))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        setState(err instanceof ApiError && err.status === 404 ? { status: "unavailable" } : { status: "error", message: errorMessage(err) });
      });
    return () => ctrl.abort();
  }, [attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((x) => x + 1);
  }, []);

  return { state, retry };
}
