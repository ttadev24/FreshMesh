"use client";

import { useState, type ReactNode } from "react";
import type { Role } from "@/lib/types";
import type { DraftsApi } from "@/components/workspace/useDrafts";
import { Spinner } from "@/components/ui/primitives";
import ProposalCard from "@/components/chat/ProposalCard";
import s from "./dashboard.module.css";

export interface DraftButton {
  kind: string;
  label: string;
  payload: Record<string, unknown>;
  /** Why the server would refuse this draft right now (shown instead of a dead click). */
  disabledReason?: string;
  testId: string;
}

export type CreateDraft = (kind: string, payload: Record<string, unknown>) => Promise<{ ok: true; id: string } | { ok: false; message: string }>;

interface Props {
  buttons: DraftButton[];
  /** Inputs that shape the payload (e.g. which purchase plan), rendered before the buttons. */
  controls?: ReactNode;
  draftIds: readonly string[];
  drafts: DraftsApi;
  role: Role;
  skuMoq: ReadonlyMap<string, number>;
  onCreate: CreateDraft;
}

/**
 * Turns a direct tool result into proposal cards (Duyệt / Sửa / Bỏ). The draft request carries the same
 * arguments as the panel's request; the server recomputes the payload from the DB, nothing executes before
 * approval.
 */
export default function PanelDrafts({ buttons, controls, draftIds, drafts, role, skuMoq, onCreate }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function create(b: DraftButton) {
    setBusy(b.kind);
    setError(null);
    const res = await onCreate(b.kind, b.payload);
    setBusy(null);
    if (!res.ok) setError(res.message);
  }

  return (
    <div className={s.panelDrafts} data-testid="panel-drafts">
      <div className={s.draftBar}>
        {controls}
        {buttons.map((b) => (
          <span key={b.kind} className={s.draftBtnWrap}>
            <button
              type="button"
              className="btn btn-sm"
              disabled={busy !== null || Boolean(b.disabledReason)}
              aria-describedby={b.disabledReason ? `${b.testId}-why` : undefined}
              onClick={() => void create(b)}
              data-testid={b.testId}
            >
              {busy === b.kind ? <Spinner /> : null}
              {b.label}
            </button>
            {b.disabledReason ? (
              <span id={`${b.testId}-why`} className={s.draftWhy}>
                {b.disabledReason}
              </span>
            ) : null}
          </span>
        ))}
      </div>
      {error ? (
        <p className={s.draftError} role="alert" data-testid="panel-draft-error">
          {error}
        </p>
      ) : null}
      {draftIds.length ? (
        <div className={s.panelProposals} aria-label="Đề xuất chờ duyệt">
          {draftIds.map((id) => (
            <ProposalCard key={id} draftId={id} draft={drafts.byId.get(id)} drafts={drafts} role={role} skuMoq={skuMoq} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
