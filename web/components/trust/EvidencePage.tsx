"use client";

import type { Verdict } from "@/lib/trust-types";
import { ErrorState, Spinner } from "@/components/ui/primitives";
import EvidenceCard, { VERDICT_VI } from "./EvidenceCard";
import { useEvidence } from "./useEvidence";
import t from "./trust.module.css";

const VERDICT_ORDER: Verdict[] = ["pass", "mixed", "fail", "measured", "not_run"];

/** "Bằng chứng": every claim FreshMesh makes, next to its measured result, PASS and FAIL alike. */
export default function EvidencePage() {
  const { state, retry } = useEvidence();
  const evidence = state.status === "ready" ? state.evidence : null;

  return (
    <div className={t.page} data-testid="evidence-page">
      <header className={t.heroText}>
        <h1 className={t.title}>Bằng chứng</h1>
        <p className={t.lead}>
          {evidence?.note_vi ?? "Kết quả không đạt được công bố cùng kết quả đạt."} Mỗi kết luận dẫn tới báo cáo thí
          nghiệm đầy đủ.
        </p>
        {evidence ? (
          <ul className={t.counts} aria-label="Tổng hợp kết quả">
            {VERDICT_ORDER.filter((v) => evidence.counts[v]).map((v) => (
              <li key={v} data-verdict={v}>
                <strong>{evidence.counts[v]}</strong> {VERDICT_VI[v].toLowerCase()}
              </li>
            ))}
          </ul>
        ) : null}
      </header>

      {state.status === "error" ? (
        <ErrorState title="Không tải được bằng chứng" message={state.message} onRetry={retry} />
      ) : !evidence ? (
        <p className={t.loading}>
          <Spinner /> Đang tải bằng chứng
        </p>
      ) : (
        <div className={t.cards}>
          {evidence.items.map((item) => (
            <EvidenceCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
