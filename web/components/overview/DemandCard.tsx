"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import type { Sourced } from "@/lib/dashboard";
import type { ForecastResponse, ForecastRow } from "@/lib/types";
import type { SlotState } from "@/components/workspace/useDirectTools";
import { ErrorState, Spinner } from "@/components/ui/primitives";
import o from "./overview.module.css";

const DemandChart = dynamic(() => import("./DemandChart"), {
  ssr: false,
  loading: () => <div className={o.chartLoading}>Đang tải biểu đồ</div>,
});

const TOP = 3;

interface Props {
  forecast: Sourced<ForecastResponse> | null;
  state: SlotState | undefined;
  skuNames: ReadonlyMap<string, string>;
  onRetry: () => void;
}

export default function DemandCard({ forecast, state, skuNames, onRetry }: Props) {
  // The SKUs with the most expected demand over the horizon, one chart each (never summed across units).
  const bySku = useMemo(() => {
    const m = new Map<string, ForecastRow[]>();
    for (const r of forecast?.value.rows ?? []) m.set(r.sku_id, [...(m.get(r.sku_id) ?? []), r]);
    return [...m.entries()]
      .map(([sku, rows]) => ({ sku, rows, total: rows.reduce((n, r) => n + r.p50, 0) }))
      .sort((a, b) => b.total - a.total)
      .slice(0, TOP);
  }, [forecast]);
  const [picked, setPicked] = useState<string | null>(null);
  const current = bySku.find((x) => x.sku === picked) ?? bySku[0];
  const sources = forecast?.sources.map((s) => s.label_vi).join("; ");

  return (
    <div className={o.demand}>
      <div className={o.demandHead}>
        <h2 className={o.cardTitle}>Nhu cầu 7 ngày tới</h2>
        {bySku.length > 1 ? (
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
        <span className={o.legendLine} aria-hidden="true" /> Dự báo P50
        <span className={o.legendBand} aria-hidden="true" /> Khoảng P10 đến P90
      </p>

      {current ? (
        <DemandChart rows={current.rows} />
      ) : state?.status === "error" ? (
        <ErrorState title="Chưa dự báo được" message={state.message} onRetry={onRetry} />
      ) : (
        <div className={o.chartLoading}>
          <Spinner /> Đang chạy mô hình dự báo
        </div>
      )}
      {sources ? <p className={o.sourceNote}>Nguồn: {sources}</p> : null}
    </div>
  );
}
