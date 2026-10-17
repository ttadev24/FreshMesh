import { repoFileUrl } from "@/lib/repo";
import type { EvidenceItem, Verdict } from "@/lib/trust-types";
import { ArrowUpRightIcon } from "@/components/shell/shell-icons";
import t from "./trust.module.css";

export const VERDICT_VI: Record<Verdict, string> = {
  pass: "Đạt",
  mixed: "Đạt một phần",
  fail: "Không đạt",
  measured: "Đã đo",
  not_run: "Chưa chạy",
};

/** One claim with its measured result. A FAIL gets exactly the same card as a PASS. */
export default function EvidenceCard({ item }: { item: EvidenceItem }) {
  return (
    <article className={t.card} data-verdict={item.verdict} data-testid={`evidence-${item.id}`}>
      <div className={t.cardTop}>
        <span className={t.verdict}>{VERDICT_VI[item.verdict] ?? item.verdict}</span>
        {item.pre_registered ? <span className={t.prereg}>Đăng ký trước khi chạy</span> : null}
        {item.exploratory ? <span className={t.prereg}>Thăm dò</span> : null}
      </div>
      <h2 className={t.cardTitle}>{item.title_vi}</h2>
      {item.impact ? (
        <div className={t.impact}>
          <p className={t.impactValue}>{item.impact.value_vi}</p>
          {item.impact.before_vi && item.impact.after_vi ? (
            <p className={t.impactMove}>
              <span>{item.impact.before_vi}</span>
              <span aria-hidden="true">→</span>
              <b>{item.impact.after_vi}</b>
            </p>
          ) : null}
          <p className={t.impactLabel}>{item.impact.label_vi}</p>
          {item.impact.second_vi ? <p className={t.impactSecond}>{item.impact.second_vi}</p> : null}
        </div>
      ) : (
        <p className={t.headline}>{item.headline_vi}</p>
      )}
      {item.impact ? (
        <details className={t.details}>
          <summary>Xem chi tiết</summary>
          <p className={t.headline}>{item.headline_vi}</p>
        </details>
      ) : null}
      <p className={t.data}>{item.data_vi}</p>
      <a className={t.report} href={repoFileUrl(item.report)} target="_blank" rel="noreferrer">
        Đọc báo cáo <ArrowUpRightIcon size={16} />
      </a>
    </article>
  );
}
