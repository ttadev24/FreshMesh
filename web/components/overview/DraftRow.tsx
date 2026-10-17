"use client";

import { useState } from "react";
import { DRAFT_KIND_VI, fmtTime } from "@/lib/format";
import type { Draft } from "@/lib/types";
import { openEscalation } from "@/components/chat/ApprovalStatus";
import { draftLines } from "@/components/chat/draftModel";
import type { NavId } from "@/components/shell/nav";
import { ArrowRightIcon } from "@/components/shell/shell-icons";
import type { DecideResult } from "@/components/workspace/usePendingDrafts";
import { Spinner } from "@/components/ui/primitives";
import o from "./overview.module.css";

/** Where a draft of this kind is worked on in the workspace. */
const NAV_FOR_KIND: Record<string, NavId> = {
  create_purchase_order: "import",
  apply_markdown: "stock",
  create_transfer: "stock",
  dispatch_routes: "delivery",
};

function detail(d: Draft, storeNames: ReadonlyMap<string, string>): string {
  const store = typeof d.payload.store_id === "string" ? (storeNames.get(d.payload.store_id) ?? d.payload.store_id) : null;
  const lines = draftLines(d.payload).length;
  return [store, lines ? `${lines} mặt hàng` : null].filter(Boolean).join(", ");
}

interface Props {
  draft: Draft;
  index: number;
  storeNames: ReadonlyMap<string, string>;
  decide: (id: string, action: "approve" | "reject") => Promise<DecideResult>;
  onNav: (id: NavId) => void;
}

/** A draft awaiting approval: expands to approve / reject inline (server-side role checks still apply). */
export default function DraftRow({ draft: d, index, storeNames, decide, onNav }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function act(action: "approve" | "reject") {
    setBusy(true);
    setMessage(null);
    const res = await decide(d.draft_id, action);
    setBusy(false);
    if (!res.ok) setMessage(res.message);
  }

  return (
    <li className={o.qItem} data-open={open || undefined}>
      <button type="button" className={o.qRow} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className={o.qNum}>{String(index + 1).padStart(2, "0")}</span>
        <span>
          <span className={o.qTitle}>
            {d.kind_label_vi ?? DRAFT_KIND_VI[d.kind] ?? d.kind}
            {openEscalation(d) ? <span className={o.qEscalated}>Cần bạn quyết định</span> : null}
          </span>
          <span className={o.qDetail}>{detail(d, storeNames)}</span>
          {d.created_at ? (
            <span className={o.qDue}>
              <span className={o.dotMango} aria-hidden="true" />
              Chờ duyệt từ {fmtTime(d.created_at)}
            </span>
          ) : null}
        </span>
        <span className={o.qArrow}>
          <ArrowRightIcon size={20} />
        </span>
      </button>
      {open ? (
        <div className={o.qActions}>
          <button type="button" className={o.approve} disabled={busy} onClick={() => void act("approve")}>
            {busy ? <Spinner /> : null}
            Duyệt
          </button>
          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => void act("reject")}>
            Bỏ
          </button>
          <button type="button" className={o.linkBtn} onClick={() => onNav(NAV_FOR_KIND[d.kind] ?? "import")}>
            Xem chi tiết
          </button>
          {message ? (
            <p className={o.qError} role="alert">
              {message}
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
