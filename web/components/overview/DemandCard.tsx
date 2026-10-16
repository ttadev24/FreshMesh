"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import type { Demand7d, DemandPoint } from "@/lib/brief-types";
import type { Sourced } from "@/lib/dashboard";
import type { ForecastResponse } from "@/lib/types";
import type { SlotState } from "@/components/workspace/useDirectTools";
import { ErrorState, Spinner } from "@/components/ui/primitives";
import o from "./overview.module.css";

const DemandChart = dynamic(() => import("./DemandChart"), {
  ssr: false,
  loading: () => <div className={o.chartLoading}>Đang tải biểu đồ</div>,
});

const TOP = 3;

interface Props {
  /** Brief's top-selling fresh SKU: past actuals + forecast. Preferred when present. */
  demand: Demand7d | null;
  /** Fallback without the brief: the overview's own forecast, one SKU at a time. */
  forecast: Sourced<ForecastResponse> | null;
  state: SlotState | undefined;
  skuNames: ReadonlyMap<string, string>;
  onRetry: () => void;
}

export default function DemandCard({ demand, forecast, state, skuNames, onRetry }: Props) {
  // Forecast-only fallback: the SKUs with the most expected demand, never summed across units.
  const bySku = useMemo(() => {
    const m = new Map<string, DemandPoint[]>();
    for (const r of forecast?.value.rows ?? []) {
      m.set(r.sku_id, [...(m.get(r.sku_id) ?? []), { date: r.date, actual: null, p10: r.p10, p50: r.p50, p90: r.p90 }]);
    }
    return [...m.entries()]
      .map(([sku, points]) => ({ sku, points, total: points.reduce((n, p) => n + (p.p50 ?? 0), 0) }))
      .sort((a, b) => b.total - a.total)
      .slice(0, TOP);
  }, [forecast]);
  const [picked, setPicked] = useState<string | null>(null);
  const current = bySku.find((x) => x.sku === picked) ?? bySku[0];

  const points = demand?.points ?? current?.points ?? null;
  const sources = demand ? demand.source_labels_vi : (forecast?.sources.map((s) => s.label_vi) ?? []);
  const hasActual = Boolean(demand?.points.some((p) => p.actual != null));

  return (
    <div className={o.demand}>
      <div className={o.demandHead}>
        <h2 className={o.cardTitle}>
          {demand ? (
            <>
              Nhu cầu 7 ngày <span className={o.cardSub}>{demand.sku_name}</span>
            </>
          ) : (
            "Nhu cầu 7 ngày tới"
          )}
        </h2>
        {!demand && bySku.length > 1 ? (
          <div className={o.chips} role="group" aria-label="Chọn mặt hàng">
            {bySku.map((x) => (
              <button key={x.sku} type="button" aria-pressed={x.sku === current?.sku} onClick={() => setPicked(x.sku)}>
                {skuNames.get(x.sku) ?? x.sku}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <p className={o.legend}>
        {hasActual ? (
          <>
            <span className={o.legendActual} aria-hidden="true" /> Thực tế
          </>
        ) : null}
        <span className={hasActual ? o.legendDashed : o.legendLine} aria-hidden="true" /> Dự báo P50
        <span className={o.legendBand} aria-hidden="true" /> Khoảng P10 đến P90
      </p>

      {points ? (
        <DemandChart points={points} />
      ) : state?.status === "error" ? (
        <ErrorState title="Chưa dự báo được" message={state.message} onRetry={onRetry} />
      ) : (
        <div className={o.chartLoading}>
          <Spinner /> Đang chạy mô hình dự báo
        </div>
      )}
      {sources.length ? (
        <details className={o.sources}>
          <summary>Nguồn: {sources.length} bộ dữ liệu</summary>
          <ul>
            {sources.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
