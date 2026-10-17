"use client";

import { useEffect, useState } from "react";
import { prefersReducedMotion } from "@/lib/theme";

/**
 * How many of `total` results are shown, one more every `stepMs` after `runKey` changes (a new run). Pacing only:
 * the results are already computed. Reduced motion shows everything at once.
 */
export function useReveal(total: number, runKey: number, stepMs = 150): number {
  const [state, setState] = useState({ key: -1, shown: 0 });

  useEffect(() => {
    if (!total) return;
    if (prefersReducedMotion()) {
      const id = window.setTimeout(() => setState({ key: runKey, shown: total }), 0);
      return () => window.clearTimeout(id);
    }
    let shown = 0;
    const id = window.setInterval(() => {
      shown += 1;
      setState({ key: runKey, shown });
      if (shown >= total) window.clearInterval(id);
    }, stepMs);
    return () => window.clearInterval(id);
  }, [total, runKey, stepMs]);

  return state.key === runKey ? state.shown : 0;
}
