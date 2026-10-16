"use client";

import { useCallback, useEffect, useState } from "react";
import { approveDraft, errorMessage, listDrafts, rejectDraft } from "@/lib/api";
import type { Draft } from "@/lib/types";

type State = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; drafts: Draft[] };
export type DecideResult = { ok: true } | { ok: false; message: string };

/** Drafts still waiting for a decision (status "draft"), oldest first: the overview queue and the header bell. */
export function usePendingDrafts() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    // A refresh keeps the current list on screen until the new one arrives (no flash back to loading).
    listDrafts(ctrl.signal)
      .then((all) => {
        const pending = all
          .filter((d) => d.status === "draft")
          .sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
        setState({ status: "ready", drafts: pending });
      })
      .catch((err: unknown) => {
        if (!ctrl.signal.aborted) setState({ status: "error", message: errorMessage(err) });
      });
    return () => ctrl.abort();
  }, [version]);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  const decide = useCallback(async (id: string, action: "approve" | "reject"): Promise<DecideResult> => {
    try {
      await (action === "approve" ? approveDraft(id) : rejectDraft(id));
      setVersion((v) => v + 1);
      return { ok: true };
    } catch (err) {
      return { ok: false, message: errorMessage(err) };
    }
  }, []);

  const count = state.status === "ready" ? state.drafts.length : null;
  return { state, count, refresh, decide };
}

export type PendingDrafts = ReturnType<typeof usePendingDrafts>;
