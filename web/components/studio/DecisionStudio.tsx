"use client";

import { useState } from "react";
import { fmtDate, fmtVnd } from "@/lib/format";
import type { Role } from "@/lib/types";
import ProposalCard from "@/components/chat/ProposalCard";
import { ErrorState, Spinner } from "@/components/ui/primitives";
import type { DraftsApi } from "@/components/workspace/useDrafts";
import DriverChips from "./DriverChips";
import GoalPanel from "./GoalPanel";
import PlanPicks from "./PlanPicks";
import PosImportDialog from "./PosImportDialog";
import QuestionCard from "./QuestionCard";
import ScenarioCard from "./ScenarioCard";
import TradeoffChart from "./TradeoffChart";
import { STUDIO_SCOPE, pointFor, useStudio } from "./useStudio";
import st from "./studio.module.css";

interface Props {
  storeId: string | null;
  storeName: string | null;
  role: Role;
  drafts: DraftsApi;
  /** Purchase orders for this store shown under the action: created here, or pending (e.g. escalated) ones. */
  draftIds: readonly string[];
  skuMoq: ReadonlyMap<string, number>;
  onCreateDraft: (kind: string, payload: Record<string, unknown>) => Promise<{ ok: true; id: string } | { ok: false; message: string }>;
}

/** "Nhập hàng": goal → context → constraints → options → trade-off → a draft a person approves. */
export default function DecisionStudio({ storeId, storeName, role, drafts, draftIds, skuMoq, onCreateDraft }: Props) {
  const studio = useStudio(storeId);
  const { value: plan, selected } = studio;
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [posOpen, setPosOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  function answer(key: string, choices: string[], i: number, field?: string) {
    const text = choices[i];
    setAnswers((a) => ({ ...a, [key]: text }));
    if (!plan) return;
    if (field === "recent_sales" && i === 0) setPosOpen(true);
    // A conflict's answers name the order they mean ("Mức phục vụ 95%: …"); "dùng phương án An toàn" picks the safe plan.
    const named = plan.frontier.find((f) => text.includes(f.label_vi));
    const safe = /an toàn/i.test(text) ? pointFor(plan, "safe") : undefined;
    const target = named ?? safe;
    if (target) studio.pick(target.name);
  }

  async function createOrder() {
    if (!selected) return;
    setCreating(true);
    setCreateError(null);
    const res = await onCreateDraft("create_purchase_order", { ...STUDIO_SCOPE, plan_name: selected.name });
    setCreating(false);
    if (!res.ok) setCreateError(res.message);
  }

  return (
    <div className={st.page} data-testid="studio-page">
      <header className={st.head}>
        <h1 className={st.title}>Nhập hàng cho ngày mai</h1>
        <p className={st.sub}>
          {plan ? `Rau và thịt cho ${plan.store_name}, giao ${fmtDate(plan.order_date)}.` : storeName ? `Rau và thịt cho ${storeName}.` : ""}
        </p>
      </header>

      {studio.plan.status === "error" ? <ErrorState message={studio.plan.message} onRetry={studio.retry} /> : null}
      {!plan ? (
        <p className={st.loading}>
          <Spinner /> Đang tính phương án nhập
        </p>
      ) : (
        <>
          {plan.escalations.map((q, i) => {
            const key = `${q.kind}-${q.field ?? i}`;
            return <QuestionCard key={key} q={q} answer={answers[key] ?? null} onAnswer={(c) => answer(key, q.choices_vi, c, q.field)} />;
          })}

          <div className={st.grid}>
            <GoalPanel
              goals={studio.goals}
              onGoals={studio.setGoals}
              choice={plan.goal_choice}
              context={studio.context}
              onContext={studio.setContext}
              busy={studio.plan.status === "loading"}
            />
            <div className={st.main}>
              <section className={st.sheet} aria-labelledby="studio-tradeoff">
                <h2 id="studio-tradeoff" className={st.sheetTitle}>
                  Đánh đổi bằng tiền
                </h2>
                <TradeoffChart frontier={plan.frontier} selected={selected} goals={studio.goals} onSelect={studio.pick} />
                <PlanPicks plan={plan} selected={selected} onSelect={studio.pick} />
              </section>

              {studio.scenario.status === "ready" ? <ScenarioCard s={studio.scenario.value} /> : null}
              {studio.scenario.status === "loading" ? (
                <p className={st.loading}>
                  <Spinner /> Đang tính tình huống
                </p>
              ) : null}

              <DriverChips rows={plan.forecast} />

              <section className={st.action} aria-label="Tạo đơn đặt hàng">
                <button type="button" className={st.primary} onClick={createOrder} disabled={!selected || creating} data-testid="studio-create">
                  {creating ? <Spinner /> : null}
                  Tạo đơn đặt hàng: {selected?.label_vi} ({selected ? fmtVnd(selected.total_cost_vnd) : ""})
                </button>
                <p className={st.note}>Đơn chỉ được thực thi khi có người bấm Duyệt.</p>
                {createError ? <p className={st.error}>{createError}</p> : null}
              </section>

              {draftIds.map((id) => (
                <ProposalCard key={id} draftId={id} draft={drafts.byId.get(id)} drafts={drafts} role={role} skuMoq={skuMoq} />
              ))}
            </div>
          </div>
        </>
      )}

      {posOpen && storeId ? <PosImportDialog storeId={storeId} onClose={() => setPosOpen(false)} /> : null}
    </div>
  );
}
