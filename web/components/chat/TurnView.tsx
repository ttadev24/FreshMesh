"use client";

import { memo } from "react";
import type { Role } from "@/lib/types";
import type { ConversationEntry } from "@/components/workspace/useConversation";
import type { DraftsApi } from "@/components/workspace/useDrafts";
import { Disclosure, ErrorState } from "@/components/ui/primitives";
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
    <li className={s.turn} data-testid="turn" data-turn>
      <div className={s.question} data-testid="turn-question">
        <p>{entry.question}</p>
      </div>
      <div className={s.reply}>
        {entry.pending ? <StepList turn={turn} pending /> : <FinishedSteps entry={entry} />}
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

/** A finished turn keeps its plan and tool steps one click away instead of a long list above the answer. */
function FinishedSteps({ entry }: { entry: ConversationEntry }) {
  const { tools } = entry.turn;
  const failed = tools.filter((t) => t.status === "error").length;
  return (
    <div className={s.stepsDone} data-testid="step-list">
      <Disclosure
        testId="steps-toggle"
        buttonClassName={s.stepsToggle}
        defaultOpen={failed > 0 || Boolean(entry.error)}
        label={
          <span>
            {tools.length ? `Đã chạy ${tools.length} bước công cụ` : "Kế hoạch xử lý (không dùng công cụ)"}
            {failed ? <span className={s.stepsFailed}>, {failed} bước lỗi</span> : null}
          </span>
        }
      >
        <StepList turn={entry.turn} pending={false} testId="" />
      </Disclosure>
    </div>
  );
}

export default memo(TurnView);
