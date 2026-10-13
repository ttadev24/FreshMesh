"use client";

import dynamic from "next/dynamic";
import { memo, useMemo, useState } from "react";
import type { Sourced as SourcedData } from "@/lib/dashboard";
import { fmtDate, fmtNum, fmtPct } from "@/lib/format";
import { KIND_VI, resolveSources, useProvenanceIndex } from "@/lib/provenance";
import type { Confidence, ForecastResponse } from "@/lib/types";
import { ConfidenceBadge, Panel, Skeleton, Sourced, SourcesLine } from "@/components/ui/primitives";
import s from "./dashboard.module.css";

const ForecastChart = dynamic(() => import("./ForecastChart"), {
  ssr: false,
  loading: () => <Skeleton lines={0} block label="Đang tải biểu đồ" />,
});

const RANK: Record<Confidence, number> = { Thấp: 0, "Trung bình": 1, Cao: 2 };

function ForecastPanel({ forecast, skuNames }: { forecast: SourcedData<ForecastResponse>; skuNames: ReadonlyMap<string, string> }) {
  const { rows, drift } = forecast.value;
  const skus = useMemo(() => [...new Set(rows.map((r) => r.sku_id))], [rows]);
  const dates = useMemo(() => [...new Set(rows.map((r) => r.date))].sort(), [rows]);
  const index = useProvenanceIndex();
  const sourceNote = useMemo(() => {
    const refs = resolveSources(forecast.sources, index);
    const labels = refs.map((r) => `${r.label_vi}${r.kind ? ` (${KIND_VI[r.kind]})` : ""}`).join("; ");
    return `${labels ? `Nguồn: ${labels}. ` : ""}Tính bởi ${forecast.tool}`;
  }, [forecast.sources, forecast.tool, index]);
  const [sku, setSku] = useState<string>("");
  const [date, setDate] = useState<string>("");
  const layout: "time" | "sku" = dates.length > 1 && (skus.length === 1 || sku) ? "time" : "sku";
  const activeSku = sku || skus[0];
  const activeDate = date || dates[0];

  const shown = useMemo(
    () =>
      layout === "time"
        ? rows.filter((r) => r.sku_id === activeSku).sort((a, b) => a.date.localeCompare(b.date))
        : rows.filter((r) => r.date === activeDate),
    [rows, layout, activeSku, activeDate],
  );

  // Panel-level badge: the weakest confidence among the rows on screen, with its reason.
  const weakest = shown.reduce<(typeof shown)[number] | null>((w, r) => (!w || RANK[r.confidence] < RANK[w.confidence] ? r : w), null);

  if (!rows.length) {
    return (
      <Panel title="Dự báo nhu cầu" labelId="forecast-title" testId="forecast-chart">
        <p className={s.muted}>Công cụ dự báo không trả về dòng nào cho lựa chọn này.</p>
        <SourcesLine sources={forecast.sources} computedBy={forecast.tool} />
      </Panel>
    );
  }

  return (
    <Panel
      title="Dự báo nhu cầu"
      sub={`${layout === "time" ? `${skuNames.get(activeSku) ?? activeSku}, ${dates.length} ngày` : `Ngày ${fmtDate(activeDate)}, ${shown.length} mặt hàng`}, đơn vị bán/ngày`}
      labelId="forecast-title"
      testId="forecast-chart"
      actions={weakest ? <ConfidenceBadge level={weakest.confidence} reason={weakest.reason} /> : null}
    >
      {drift?.alert ? (
        <div className={s.warn} role="alert" data-testid="drift-warning">
          <b>Cảnh báo lệch dự báo.</b> {drift.message_vi}
          {drift.coverage_7d != null ? (
            <>
              {" "}
              Độ phủ 7 ngày: <Sourced tool={forecast.tool} sources={forecast.sources}>{fmtPct(drift.coverage_7d <= 1 ? drift.coverage_7d * 100 : drift.coverage_7d)}</Sourced>.
            </>
          ) : null}{" "}
          Nên cân nhắc phương án <b>An toàn</b>.
        </div>
      ) : null}

      {(skus.length > 1 && dates.length > 1) || dates.length > 1 ? (
        <div className={s.controls}>
          {skus.length > 1 && dates.length > 1 ? (
            <label>
              Mặt hàng{" "}
              <select className={s.miniSelect} value={sku} onChange={(e) => setSku(e.target.value)}>
                <option value="">Tất cả (theo ngày)</option>
                {skus.map((id) => (
                  <option key={id} value={id}>
                    {skuNames.get(id) ?? id}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {layout === "sku" && dates.length > 1 ? (
            <label>
              Ngày{" "}
              <select className={s.miniSelect} value={activeDate} onChange={(e) => setDate(e.target.value)}>
                {dates.map((d) => (
                  <option key={d} value={d}>
                    {fmtDate(d)}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
      ) : null}

      <ForecastChart rows={shown} layout={layout} skuNames={skuNames} sourceNote={sourceNote} />

      <details className={s.details}>
        <summary>Bảng số liệu dự báo</summary>
        <div className={s.tableScroll}>
          <table className={s.table}>
            <thead>
              <tr>
                <th scope="col">{layout === "time" ? "Ngày" : "Mặt hàng"}</th>
                <th scope="col">P10</th>
                <th scope="col">P50</th>
                <th scope="col">P90</th>
                <th scope="col">Tin cậy</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={`${r.sku_id}-${r.date}`}>
                  <th scope="row">{layout === "time" ? fmtDate(r.date) : (skuNames.get(r.sku_id) ?? r.sku_id)}</th>
                  <td>
                    <Sourced tool={forecast.tool} citations={forecast.citations} sources={forecast.sources}>{fmtNum(r.p10)}</Sourced>
                  </td>
                  <td>
                    <Sourced tool={forecast.tool} citations={forecast.citations} sources={forecast.sources}>{fmtNum(r.p50)}</Sourced>
                  </td>
                  <td>
                    <Sourced tool={forecast.tool} citations={forecast.citations} sources={forecast.sources}>{fmtNum(r.p90)}</Sourced>
                  </td>
                  <td title={r.reason}>{r.confidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      {weakest?.reason ? <p className={s.muted}>{weakest.reason}</p> : null}
      <SourcesLine sources={forecast.sources} computedBy={forecast.tool} />
    </Panel>
  );
}

export default memo(ForecastPanel);
