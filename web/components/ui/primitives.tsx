import type { ReactNode } from "react";
import type { Confidence } from "@/lib/types";
import s from "./ui.module.css";

export type Tone = "neutral" | "green" | "amber" | "red" | "blue";

export function Badge({ tone = "neutral", children, testId, title }: { tone?: Tone; children: ReactNode; testId?: string; title?: string }) {
  return (
    <span className={`${s.badge} ${s[tone]}`} data-testid={testId} title={title}>
      {children}
    </span>
  );
}

export function SimulatedBadge({ testId }: { testId?: string }) {
  return (
    <span
      className={`${s.badge} ${s.simulated}`}
      data-testid={testId}
      title="Toàn bộ dữ liệu là dữ liệu giả lập, chưa phải dữ liệu bán hàng thật."
    >
      SIMULATED
    </span>
  );
}

const CONF_TONE: Record<Confidence, Tone> = { Cao: "green", "Trung bình": "amber", Thấp: "red" };

export function ConfidenceBadge({ level, reason }: { level: Confidence; reason?: string }) {
  return (
    <Badge tone={CONF_TONE[level]} testId="confidence-badge" title={reason}>
      Độ tin cậy: {level}
    </Badge>
  );
}

/** Number with a hover / focus tooltip naming where it comes from (spec §9). */
export function Sourced({ children, tool, citations, note }: { children: ReactNode; tool: string; citations?: string[]; note?: string }) {
  return (
    <span className={s.source} tabIndex={0}>
      {children}
      <span className={s.sourceTip} role="tooltip">
        <b>Nguồn:</b> công cụ <code>{tool}</code>, dữ liệu SIMULATED.
        {note ? <> {note}</> : null}
        {citations && citations.length ? <> Trích dẫn: {citations.slice(0, 3).join("; ")}.</> : null}
      </span>
    </span>
  );
}

export function Panel({ title, sub, actions, children, testId, labelId }: {
  title: string;
  sub?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  testId?: string;
  labelId: string;
}) {
  return (
    <section className={s.panel} data-testid={testId} aria-labelledby={labelId}>
      <header className={s.panelHead}>
        <div>
          <h2 id={labelId}>{title}</h2>
          {sub ? <p className={s.panelSub}>{sub}</p> : null}
        </div>
        {actions}
      </header>
      {children}
    </section>
  );
}

export function Skeleton({ lines = 3, block = false, label = "Đang tải dữ liệu" }: { lines?: number; block?: boolean; label?: string }) {
  return (
    <div className={s.skeleton} role="status" aria-label={label}>
      {block ? <div className={`${s.skeletonLine} ${s.skeletonBlock}`} /> : null}
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className={s.skeletonLine} style={{ width: `${92 - i * 17}%` }} />
      ))}
    </div>
  );
}

export function Spinner() {
  return <span className={s.spinner} aria-hidden="true" />;
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className={s.state}>
      <h3>{title}</h3>
      {children ? <div>{children}</div> : null}
    </div>
  );
}

export function ErrorState({ title = "Không tải được dữ liệu", message, onRetry, testId }: {
  title?: string;
  message: string;
  onRetry?: () => void;
  testId?: string;
}) {
  return (
    <div className={`${s.state} ${s.stateError}`} role="alert" data-testid={testId}>
      <h3>{title}</h3>
      <p>{message}</p>
      {onRetry ? (
        <button type="button" className="btn btn-sm" onClick={onRetry}>
          Thử lại
        </button>
      ) : null}
    </div>
  );
}
