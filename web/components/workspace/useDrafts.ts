"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { approveDraft, createDraft, editDraft, errorMessage, listDrafts, rejectDraft } from "@/lib/api";
import type { Draft } from "@/lib/types";

export type DraftAction = "approve" | "reject" | "edit";

export interface DraftsApi {
  byId: ReadonlyMap<string, Draft>;
  loading: boolean;
  loadError: string | null;
  refresh: () => void;
  act: (id: string, action: DraftAction, payload?: Record<string, unknown>) => Promise<{ ok: true } | { ok: false; message: string; forbidden: boolean }>;
  /** POST /api/drafts from a dashboard tool panel; the server recomputes the payload from the DB. */
  create: (kind: string, payload: Record<string, unknown>) => Promise<{ ok: true; id: string } | { ok: false; message: string }>;
}

/** Drafts are created by agent turns or by the dashboard tool panels, and only change through the approval endpoints. */
export function useDrafts(wantedIds: readonly string[]): DraftsApi {
  const [byId, setById] = useState<ReadonlyMap<string, Draft>>(new Map());
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const ctrlRef = useRef<AbortController | null>(null);

  // Refetch when a turn references a draft we have not seen yet.
  const missingKey = wantedIds.filter((id) => !byId.has(id)).join(",");

  useEffect(() => {
    if (!missingKey && tick === 0) return;
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading flag for the fetch started here
    setLoading(true);
    listDrafts(ctrl.signal)
      .then((list) => {
        setById(new Map(list.map((d) => [d.draft_id, d])));
        setLoadError(null);
      })
      .catch((err) => {
        if (!ctrl.signal.aborted) setLoadError(errorMessage(err));
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [missingKey, tick]);

  const refresh = useCallback(() => setTick((n) => n + 1), []);

  const act = useCallback<DraftsApi["act"]>(async (id, action, payload) => {
    try {
      const updated =
        action === "approve" ? await approveDraft(id) : action === "reject" ? await rejectDraft(id) : await editDraft(id, payload ?? {});
      setById((prev) => {
        const next = new Map(prev);
        const before = prev.get(id);
        const updatedPayload = Object.keys(updated.payload).length ? updated.payload : null;
        next.set(id, {
          ...before,
          ...updated,
          draft_id: id,
          kind: updated.kind || before?.kind || "",
          sources: updated.sources.length ? updated.sources : (before?.sources ?? []),
          payload: updatedPayload ?? (action === "edit" && payload ? payload : (before?.payload ?? {})),
        });
        return next;
      });
      return { ok: true };
    } catch (err) {
      const status = (err as { status?: number }).status;
      return { ok: false, message: errorMessage(err), forbidden: status === 403 };
    }
  }, []);

  const create = useCallback<DraftsApi["create"]>(async (kind, payload) => {
    try {
      const draft = await createDraft(kind, payload);
      if (!draft.draft_id) return { ok: false, message: "Máy chủ không trả mã bản nháp." };
      setById((prev) => new Map(prev).set(draft.draft_id, draft));
      return { ok: true, id: draft.draft_id };
    } catch (err) {
      return { ok: false, message: errorMessage(err) };
    }
  }, []);

  return useMemo(() => ({ byId, loading, loadError, refresh, act, create }), [byId, loading, loadError, refresh, act, create]);
}
