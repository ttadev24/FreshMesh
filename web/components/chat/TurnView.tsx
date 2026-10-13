"use client";

import { memo } from "react";
import type { Role } from "@/lib/types";
import type { ConversationEntry } from "@/components/workspace/useConversation";
import type { DraftsApi } from "@/components/workspace/useDrafts";
import { ErrorState } from "@/components/ui/primitives";
import AnswerView from "./AnswerView";
import ProposalCard from "./ProposalCard";
import StepList from "./StepList";
import s from "./chat.module.css";

interface Props {
  entry: ConversationEntry;
  drafts: DraftsApi;
  role: Role;
  skuMoq: ReadonlyMap<string, number>;
  onDashboard: boolean;
  hasData: boolean;
  onShowDashboard: (id: string) => void;
}

function TurnView({ entry, drafts, role, skuMoq, onDashboard, hasData, onShowDashboard }: Props) {
  const { turn } = entry;
  return (
    <li className={s.turn} data-testid="turn">
      <div className={s.question}>
        <p>{entry.question}</p>
      </div>
      <div className={s.reply}>
        <StepList turn={turn} pending={entry.pending} />
        {entry.error ? (
          <ErrorState
            title={entry.errorCode === "llm_unavailable" ? "Trợ lý chưa sẵn sàng" : "Không hoàn tất lượt này"}
            message={entry.error}
            testId="turn-error"
          />
        ) : null}
        {turn.error_vi && !entry.error ? <p className={s.proposalError} role="alert">{turn.error_vi}</p> : null}
        <AnswerView turn={turn} />
        {turn.drafts.length ? (
          <div className={s.proposals} aria-label="Đề xuất chờ duyệt">
            {turn.drafts.map((id) => (
              <ProposalCard key={id} draftId={id} draft={drafts.byId.get(id)} drafts={drafts} role={role} skuMoq={skuMoq} />
            ))}
          </div>
        ) : null}
        {hasData ? (
          <button
            type="button"
            className={`btn btn-sm ${s.dashLink}`}
            aria-pressed={onDashboard}
            onClick={() => onShowDashboard(entry.id)}
            data-testid="show-dashboard"
          >
            {onDashboard ? "Đang hiển thị trên bảng điều khiển" : "Xem trên bảng điều khiển"}
          </button>
        ) : null}
      </div>
    </li>
  );
}

export default memo(TurnView);
