"use client";

import { useId, useState, type ReactNode } from "react";
import { KIND_HELP_VI, KIND_VI, resolveSources, useProvenanceIndex } from "@/lib/provenance";
import type { Confidence, SourceKind, SourceRef } from "@/lib/types";
import s from "./ui.module.css";

export type Tone = "neutral" | "green" | "amber" | "red" | "blue";

export function Badge({ tone = "neutral", children, testId, title }: { tone?: Tone; children: ReactNode; testId?: string; title?: string }) {
  return (
    <span className={`${s.badge} ${s[tone]}`} data-testid={testId} title={title}>
      {children}
    </span>
  );
}

/** Data-source kind chip. The kind is always written out; colour only reinforces it. */
export function KindChip({ kind }: { kind: SourceKind }) {
  return (
    <span className={`${s.kind} ${s[`kind_${kind}`]}`} data-testid="kind-chip" data-kind={kind} title={KIND_HELP_VI[kind]}>
      {KIND_VI[kind]}
    </span>
  );
}

/**
 * Button + region disclosure (WAI-ARIA pattern): `aria-expanded` on the button, `hidden` on the region.
 * The region's content is only rendered while open. The chevron turns with the state.
 */
export function Disclosure({ label, defaultOpen = false, children, buttonClassName, regionClassName, testId, after, headingClassName }: {
  label: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
  buttonClassName?: string;
  regionClassName?: string;
  testId?: string;
  /** Rendered between the button and the region (e.g. "tính bởi …" next to a sources toggle). */
  after?: ReactNode;
  /** Wraps the button in an h3 (accordion pattern) when given. */
  headingClassName?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const button = (
    <button
      type="button"
      className={`${s.disclosureBtn} ${buttonClassName ?? ""}`}
      aria-expanded={open}
      aria-controls={id}
      onClick={() => setOpen((v) => !v)}
      data-testid={testId}
    >
      <span className={s.chevron} aria-hidden="true" />
      {label}
    </button>
  );
  return (
    <>
      {headingClassName === undefined ? button : <h3 className={headingClassName}>{button}</h3>}
      {after}
      <div id={id} hidden={!open} className={regionClassName}>
        {open ? children : null}
      </div>
    </>
  );
}

/**
 * "Nguồn dữ liệu" of a panel or answer, from the payload's `sources` / `source_labels_vi`.
 * `compact`: one line "Nguồn dữ liệu (N)" with the distinct kinds, expanding to the labelled chips.
 */
export function SourcesLine({ sources, computedBy, testId = "sources-line", bare = false, compact = false }: {
  sources: readonly SourceRef[];
  computedBy?: string;
  testId?: string;
  /** Without the dashed rule above the line (when its container already separates it). */
  bare?: boolean;
  compact?: boolean;
}) {
  const index = useProvenanceIndex();
  const refs = resolveSources(sources, index);
  if (!refs.length && !computedBy) return null;
  const by = computedBy ? (
    <span className={s.sourcesBy}>
      tính bởi <code>{computedBy}</code>
    </span>
  ) : null;
  const list = (
    <ul className={s.sourcesList}>
      {refs.map((r) => (
        <li key={r.id} data-testid="source-ref">
          {r.kind ? <KindChip kind={r.kind} /> : null}
          <span>{r.label_vi}</span>
        </li>
      ))}
    </ul>
  );

  if (compact && refs.length) {
    const kinds = [...new Set(refs.map((r) => r.kind).filter((k): k is SourceKind => Boolean(k)))];
    return (
      <div className={`${s.sourcesLine} ${s.sourcesCompact} ${bare ? s.sourcesBare : ""}`} data-testid={testId}>
        <Disclosure
          testId="sources-toggle"
          buttonClassName={s.sourcesToggle}
          regionClassName={s.sourcesRegion}
          label={
            <>
              <span className={s.sourcesLabel}>Nguồn dữ liệu</span>
              <span className={s.sourcesCount}>({refs.length})</span>
              <span className={s.sourcesKinds}>
                {kinds.map((k) => (
                  <KindChip key={k} kind={k} />
                ))}
              </span>
            </>
          }
          after={by}
        >
          {list}
        </Disclosure>
      </div>
    );
  }

  return (
    <div className={`${s.sourcesLine} ${bare ? s.sourcesBare : ""}`} data-testid={testId}>
      <span className={s.sourcesLabel}>Nguồn dữ liệu:</span>
      {refs.length ? list : <span className={s.sourcesMissing}>máy chủ chưa gắn nguồn cho kết quả này</span>}
      {by}
    </div>
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

/** Number with a hover / focus tooltip naming the data it is derived from and the tool that computed it (spec §9). */
export function Sourced({ children, tool, citations, sources, note }: {
  children: ReactNode;
  tool: string;
  citations?: string[];
  sources?: readonly SourceRef[];
  note?: string;
}) {
  const index = useProvenanceIndex();
  const refs = resolveSources(sources ?? [], index);
  return (
    <span className={s.source} tabIndex={0}>
      {children}
      <span className={s.sourceTip} role="tooltip">
        {refs.length ? (
          <>
            <b>Nguồn dữ liệu:</b> {refs.map((r) => `${r.label_vi}${r.kind ? ` (${KIND_VI[r.kind]})` : ""}`).join("; ")}.{" "}
          </>
        ) : null}
        <b>Tính bởi:</b> <code>{tool}</code>.
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

/** Loading placeholder shaped like a dashboard panel: title, subtitle, a chart / table block. */
export function PanelSkeleton({ label }: { label: string }) {
  return (
    <div className={`${s.panel} ${s.panelSkeleton}`} role="status" aria-label={label}>
      <div className={s.skeletonHead}>
        <div className={s.skeletonLine} style={{ width: "38%", height: 14 }} />
        <div className={s.skeletonLine} style={{ width: "56%" }} />
      </div>
      <div className={`${s.skeletonLine} ${s.skeletonBlock}`} />
      <p className={s.skeletonLabel}>{label}</p>
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
