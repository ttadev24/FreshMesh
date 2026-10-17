"use client";

import { useCallback, useEffect, useState } from "react";
import { errorMessage, getEvidence } from "@/lib/api";
import type { Evidence } from "@/lib/trust-types";

export type EvidenceState = { status: "loading" } | { status: "ready"; evidence: Evidence } | { status: "error"; message: string };

export function useEvidence() {
  const [state, setState] = useState<EvidenceState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    getEvidence(ctrl.signal)
      .then((evidence) => setState({ status: "ready", evidence }))
      .catch((err: unknown) => {
        if (!ctrl.signal.aborted) setState({ status: "error", message: errorMessage(err) });
      });
    return () => ctrl.abort();
  }, [attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((x) => x + 1);
  }, []);

  return { state, retry };
}
