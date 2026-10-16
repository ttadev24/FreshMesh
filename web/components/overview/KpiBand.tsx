"use client";

import { useEffect, useState, type ReactNode } from "react";
import { prefersReducedMotion } from "@/lib/theme";
import o from "./overview.module.css";

export interface Kpi {
  label: string;
  /** null while the number is still being computed (or failed: see `error`). */
  value: number | null;
  format: (n: number) => string;
  unit?: string;
  sub: ReactNode;
  /** Where the number comes from, read out on hover and by screen readers. */
  source: string;
  error?: string | null;
  testId: string;
}

const COUNT_MS = 900;

/** Counts from 0 to `target` once, the first time it is known (the page's single load moment). */
function useCountUp(target: number | null): number | null {
  const [shown, setShown] = useState<number | null>(null);
  const still = typeof window === "undefined" || prefersReducedMotion();
  useEffect(() => {
    if (target == null || still) return;
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / COUNT_MS);
      setShown(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    // Background tabs pause rAF: a timer (which still runs, throttled) lands the final value regardless.
    const land = setTimeout(() => setShown(target), COUNT_MS + 150);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(land);
    };
  }, [target, still]);
  if (target == null) return null;
  return still ? target : (shown ?? 0);
}

function KpiCell({ kpi }: { kpi: Kpi }) {
  const shown = useCountUp(kpi.value);
  return (
    <div className={o.kpi} data-testid={kpi.testId} title={kpi.source}>
      <p className={o.kpiLabel}>{kpi.label}</p>
      <p className={o.kpiValue} aria-live="polite">
        {kpi.error ? (
          <span className={o.kpiError}>Chưa tính được</span>
        ) : shown == null ? (
          <span className={o.kpiSkeleton} aria-label="Đang tính" />
        ) : (
          <>
            {kpi.format(shown)}
            {kpi.unit ? <span className={o.kpiUnit}>{kpi.unit}</span> : null}
          </>
        )}
      </p>
      <p className={o.kpiSub}>{kpi.error ?? kpi.sub}</p>
      <span className="sr-only">Nguồn: {kpi.source}</span>
    </div>
  );
}

export default function KpiBand({ items }: { items: Kpi[] }) {
  return (
    <section className={o.kpis} aria-label="Chỉ số chính">
      {items.map((k) => (
        <KpiCell key={k.testId} kpi={k} />
      ))}
    </section>
  );
}
