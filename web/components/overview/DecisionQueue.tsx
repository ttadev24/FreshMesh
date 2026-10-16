"use client";

import type { BriefCard, BriefPanel } from "@/lib/brief-types";
import type { NavId } from "@/components/shell/nav";
import { ArrowRightIcon } from "@/components/shell/shell-icons";
import type { PendingDrafts } from "@/components/workspace/usePendingDrafts";
import { ErrorState, Spinner } from "@/components/ui/primitives";
import BriefRow from "./BriefRow";
import DraftRow from "./DraftRow";
import o from "./overview.module.css";

const SHOWN_DRAFTS = 3;

interface Props {
  /** Today's brief suggestions; null when the brief is not available (only drafts are listed then). */
  cards: BriefCard[] | null;
  briefLoading: boolean;
  pending: PendingDrafts;
  storeNames: ReadonlyMap<string, string>;
  onNav: (id: NavId) => void;
  onAction: (panel: BriefPanel, storeId: string) => void;
}

export default function DecisionQueue({ cards, briefLoading, pending, storeNames, onNav, onAction }: Props) {
  const { state } = pending;
  const drafts = state.status === "ready" ? state.drafts : [];
  const todo = (cards ?? []).filter((c) => c.status !== "none").length + drafts.length;
  const nothing = !briefLoading && !(cards && cards.length) && state.status === "ready" && drafts.length === 0;

  return (
    <section className={o.queue} aria-labelledby="queue-title" data-testid="decision-queue">
      <div className={o.sectionHead}>
        <h2 id="queue-title" className={o.sectionTitle}>
          Cần quyết định
        </h2>
        <span className={o.queueCount}>{briefLoading || state.status !== "ready" ? "" : String(todo).padStart(2, "0")}</span>
      </div>

      {briefLoading ? (
        <div className={o.queueEmpty}>
          <span>
            <Spinner /> Đang lập bản tin buổi sáng (lần đầu có thể mất tới 30 giây)
          </span>
        </div>
      ) : cards && cards.length ? (
        <ol className={o.qList} data-testid="brief-cards">
          {cards.map((c, i) => (
            <BriefRow key={c.kind} card={c} index={i} onAction={onAction} />
          ))}
        </ol>
      ) : null}

      {state.status === "error" ? (
        <ErrorState title="Không tải được đề xuất" message={state.message} onRetry={pending.refresh} />
      ) : drafts.length ? (
        <>
          {cards && cards.length ? <h3 className={o.groupTitle}>Chờ bạn duyệt</h3> : null}
          <ol className={o.qList}>
            {drafts.slice(0, SHOWN_DRAFTS).map((d, i) => (
              <DraftRow key={d.draft_id} draft={d} index={i} storeNames={storeNames} decide={pending.decide} onNav={onNav} />
            ))}
          </ol>
        </>
      ) : null}

      {nothing ? (
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
      ) : null}

      <button type="button" className={o.cta} onClick={() => onNav("history")}>
        {drafts.length > SHOWN_DRAFTS ? `Xem cả ${drafts.length} đề xuất và lịch sử` : "Xem lịch sử quyết định"}
        <ArrowRightIcon />
      </button>
    </section>
  );
}
