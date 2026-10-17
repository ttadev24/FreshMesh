import { fmtNum } from "@/lib/format";
import type { VerifyCase } from "@/lib/trust-types";
import { CheckMark, CrossMark } from "./trust-icons";
import t from "./trust.module.css";

/** One live safety check: what was tried, what must happen, and what happened on this run. */
export default function VerifyCaseRow({ c }: { c: VerifyCase }) {
  return (
    <li className={t.case} data-pass={c.pass} data-testid={`verify-case-${c.id}`}>
      <span className={t.mark} aria-hidden="true">
        {c.pass ? <CheckMark /> : <CrossMark />}
      </span>
      <div className={t.caseBody}>
        <h3 className={t.caseTitle}>
          {c.title_vi}
          <span className="sr-only">{c.pass ? ": đạt" : ": không đạt"}</span>
        </h3>
        <p className={t.caseActual}>{c.actual_vi}</p>
        <dl className={t.caseMeta}>
          <div>
            <dt>Thử</dt>
            <dd>{c.input_vi}</dd>
          </div>
          <div>
            <dt>Yêu cầu</dt>
            <dd>{c.expected_vi}</dd>
          </div>
        </dl>
      </div>
      <span className={t.ms}>{fmtNum(c.duration_ms, 1)} ms</span>
    </li>
  );
}
