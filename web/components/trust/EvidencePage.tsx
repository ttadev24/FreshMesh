"use client";

import type { Verdict } from "@/lib/trust-types";
import { ErrorState, Spinner } from "@/components/ui/primitives";
import EvidenceCard, { VERDICT_VI } from "./EvidenceCard";
import { useEvidence } from "./useEvidence";
import t from "./trust.module.css";

const VERDICT_ORDER: Verdict[] = ["pass", "mixed", "fail", "measured", "not_run"];
// Cards: what holds first (passed, then measured), what did not after; exploratory checks last. Nothing is hidden.
const CARD_RANK: Record<Verdict, number> = { pass: 0, measured: 1, mixed: 2, fail: 3, not_run: 4 };

/** "Bằng chứng": every claim FreshMesh makes, next to its measured result, PASS and FAIL alike. */
export default function EvidencePage() {
  const { state, retry } = useEvidence();
  const evidence = state.status === "ready" ? state.evidence : null;

  return (
    <div className={t.page} data-testid="evidence-page">
      <header className={t.heroText}>
        <h1 className={t.title}>Bằng chứng</h1>
        <p className={t.hook}>Cả chỗ chưa đạt, chúng tôi cũng công bố.</p>
        <p className={t.lead}>
          Mỗi kết luận có số đo và báo cáo thí nghiệm đầy đủ. Thí nghiệm nào đăng ký tiêu chí trước khi chạy đều được ghi
          rõ.
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
          {[...evidence.items]
            .sort((a, b) => Number(Boolean(a.exploratory)) - Number(Boolean(b.exploratory)) || CARD_RANK[a.verdict] - CARD_RANK[b.verdict])
            .map((item) => (
            <EvidenceCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
