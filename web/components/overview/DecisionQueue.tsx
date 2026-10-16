"use client";

import { useState } from "react";
import { DRAFT_KIND_VI, fmtTime } from "@/lib/format";
import type { Draft } from "@/lib/types";
import { draftLines } from "@/components/chat/draftModel";
import type { NavId } from "@/components/shell/nav";
import { ArrowRightIcon } from "@/components/shell/shell-icons";
import type { PendingDrafts } from "@/components/workspace/usePendingDrafts";
import { ErrorState, Spinner } from "@/components/ui/primitives";
import o from "./overview.module.css";

const SHOWN = 4;

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
  pending: PendingDrafts;
  storeNames: ReadonlyMap<string, string>;
  onNav: (id: NavId) => void;
}

export default function DecisionQueue({ pending, storeNames, onNav }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string } | null>(null);
  const { state } = pending;

  async function decide(id: string, action: "approve" | "reject") {
    setBusy(id);
    setMessage(null);
    const res = await pending.decide(id, action);
    setBusy(null);
    if (res.ok) setOpen(null);
    else setMessage({ id, text: res.message });
  }

  const drafts = state.status === "ready" ? state.drafts : [];
  return (
    <section className={o.queue} aria-labelledby="queue-title" data-testid="decision-queue">
      <div className={o.sectionHead}>
        <h2 id="queue-title" className={o.sectionTitle}>
          Cần quyết định
        </h2>
        <span className={o.queueCount}>{state.status === "ready" ? String(drafts.length).padStart(2, "0") : ""}</span>
      </div>

      {state.status === "error" ? (
        <ErrorState title="Không tải được đề xuất" message={state.message} onRetry={pending.refresh} />
      ) : state.status === "loading" ? (
        <div className={o.queueEmpty}>
          <Spinner /> Đang tải đề xuất chờ duyệt
        </div>
      ) : drafts.length === 0 ? (
        <div className={o.queueEmpty}>
          <p>Không có đề xuất nào đang chờ. Máy chỉ đề xuất, bạn là người duyệt.</p>
          <div className={o.queueStart}>
            <button type="button" className="btn btn-sm" onClick={() => onNav("import")}>
              Lập phương án nhập hàng
            </button>
            <button type="button" className="btn btn-sm" onClick={() => onNav("stock")}>
              Xử lý hàng tồn
            </button>
          </div>
        </div>
      ) : (
        <ol className={o.qList}>
          {drafts.slice(0, SHOWN).map((d, i) => {
            const expanded = open === d.draft_id;
            return (
              <li key={d.draft_id} className={o.qItem} data-open={expanded || undefined}>
                <button
                  type="button"
                  className={o.qRow}
                  aria-expanded={expanded}
                  onClick={() => setOpen(expanded ? null : d.draft_id)}
                >
                  <span className={o.qNum}>{String(i + 1).padStart(2, "0")}</span>
                  <span>
                    <span className={o.qTitle}>{d.kind_label_vi ?? DRAFT_KIND_VI[d.kind] ?? d.kind}</span>
                    <span className={o.qDetail}>{detail(d, storeNames)}</span>
                    {d.created_at ? (
                      <span className={o.qDue}>
                        <span className={o.dotMango} aria-hidden="true" />
                        Tạo lúc {fmtTime(d.created_at)}
                      </span>
                    ) : null}
                  </span>
                  <span className={o.qArrow}>
                    <ArrowRightIcon size={20} />
                  </span>
                </button>
                {expanded ? (
                  <div className={o.qActions}>
                    <button
                      type="button"
                      className={o.approve}
                      disabled={busy === d.draft_id}
                      onClick={() => void decide(d.draft_id, "approve")}
                    >
                      {busy === d.draft_id ? <Spinner /> : null}
                      Duyệt
                    </button>
                    <button type="button" className="btn btn-sm" disabled={busy === d.draft_id} onClick={() => void decide(d.draft_id, "reject")}>
                      Bỏ
                    </button>
                    <button type="button" className={o.linkBtn} onClick={() => onNav(NAV_FOR_KIND[d.kind] ?? "import")}>
                      Xem chi tiết
                    </button>
                    {message?.id === d.draft_id ? (
                      <p className={o.qError} role="alert">
                        {message.text}
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>
      )}

      <button type="button" className={o.cta} onClick={() => onNav("history")}>
        {drafts.length > SHOWN ? `Xem cả ${drafts.length} đề xuất và lịch sử` : "Xem lịch sử quyết định"}
        <ArrowRightIcon />
      </button>
    </section>
  );
}
