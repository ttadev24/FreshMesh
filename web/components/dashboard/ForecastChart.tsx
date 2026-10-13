"use client";

// Loaded with next/dynamic (ssr: false): ECharts touches `window` and is ~300 kB, so it is only
// fetched once a forecast is on screen. Only the pieces used here are registered (tree-shaken core).
import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { memo, useEffect, useRef } from "react";
import { fmtDate, fmtNum } from "@/lib/format";
import { cssVar, prefersReducedMotion, useColorScheme } from "@/lib/theme";
import type { ForecastRow } from "@/lib/types";

echarts.use([LineChart, BarChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

interface Props {
  rows: ForecastRow[];
  /** "time": one SKU over several days (band). "sku": several SKUs on one day (horizontal range bars). */
  layout: "time" | "sku";
  skuNames: ReadonlyMap<string, string>;
  /** Plain-text provenance shown in the chart tooltip ("Nguồn: …"). */
  sourceNote: string;
}

const escapeHtml = (v: string) => v.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

const ROW_H = 30;
const chartHeight = (rows: number, layout: Props["layout"]) => (layout === "sku" ? Math.max(180, rows * ROW_H + 56) : 260);

function buildOption(rows: ForecastRow[], layout: Props["layout"], skuNames: Props["skuNames"], sourceNote: string): echarts.EChartsCoreOption {
  const green = cssVar("--green", "#1d6a46");
  const ink2 = cssVar("--ink-2", "#44554c");
  const line = cssVar("--line", "#d3dcd6");
  const surface = cssVar("--surface", "#fbfcfb");
  const ink = cssVar("--ink", "#12201a");
  const sku = layout === "sku";
  const categories = rows.map((r) => (sku ? (skuNames.get(r.sku_id) ?? r.sku_id) : fmtDate(r.date)));

  // SKU names are long ("Rau muống (bó 500g)"): a category axis on Y keeps every name readable at any
  // pane width, where rotated X labels collide on phones.
  const categoryAxis = {
    type: "category",
    data: categories,
    boundaryGap: sku,
    inverse: sku,
    axisLine: { lineStyle: { color: line } },
    axisTick: { show: false },
    axisLabel: { color: ink2, fontSize: 11, interval: 0, width: 150, overflow: "truncate" },
  };
  const valueAxis = {
    type: "value",
    splitLine: { lineStyle: { color: line, type: "dashed" } },
    axisLabel: { color: ink2, fontSize: 11 },
  };

  // Band = transparent P10 base + (P90 − P10) stacked on top of it.
  const kind = sku ? "bar" : "line";
  const baseSeries = {
    name: "P10",
    type: kind,
    stack: "band",
    data: rows.map((r) => r.p10),
    itemStyle: { color: "transparent" },
    lineStyle: { opacity: 0 },
    symbol: "none",
    silent: true,
    barWidth: 14,
    tooltip: { show: false },
  };
  const widthSeries = {
    name: "Khoảng P10-P90",
    type: kind,
    stack: "band",
    data: rows.map((r) => Math.max(0, r.p90 - r.p10)),
    symbol: "none",
    lineStyle: { opacity: 0 },
    areaStyle: sku ? undefined : { color: green, opacity: 0.18 },
    itemStyle: { color: sku ? `${green}33` : green, borderColor: green, borderWidth: sku ? 1 : 0, borderRadius: 2 },
    barWidth: 14,
  };
  const p50Series = sku
    ? { name: "P50", type: "scatter", data: rows.map((r) => r.p50), symbol: "rect", symbolSize: [3, 20], itemStyle: { color: green } }
    : { name: "P50", type: "line", data: rows.map((r) => r.p50), symbol: "circle", symbolSize: 5, lineStyle: { color: green, width: 2 }, itemStyle: { color: green } };

  return {
    animation: !prefersReducedMotion(),
    animationDuration: 400,
    textStyle: { fontFamily: getComputedStyle(document.body).fontFamily, color: ink2 },
    grid: { left: 8, right: 16, top: 30, bottom: 8, containLabel: true },
    legend: { top: 0, left: 0, itemWidth: 14, itemHeight: 8, textStyle: { color: ink2, fontSize: 12 }, data: ["Khoảng P10-P90", "P50"] },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: sku ? "shadow" : "line" },
      backgroundColor: surface,
      borderColor: line,
      textStyle: { color: ink, fontSize: 12 },
      formatter: (params: { dataIndex: number }[]) => {
        const i = params[0]?.dataIndex ?? 0;
        const r = rows[i];
        if (!r) return "";
        return [
          `<b>${categories[i]}</b>`,
          `P90: ${fmtNum(r.p90)}`,
          `P50: ${fmtNum(r.p50)}`,
          `P10: ${fmtNum(r.p10)}`,
          `Độ tin cậy: ${r.confidence}`,
          `<span style="opacity:.7">${escapeHtml(sourceNote)}</span>`,
        ].join("<br/>");
      },
    },
    xAxis: sku ? valueAxis : categoryAxis,
    yAxis: sku ? categoryAxis : valueAxis,
    series: [baseSeries, widthSeries, p50Series],
  };
}

function ForecastChart({ rows, layout, skuNames, sourceNote }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  // Colours are resolved from CSS tokens: rebuild the option when the system theme flips.
  const scheme = useColorScheme();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, { renderer: "canvas" });
    chartRef.current = chart;
    // Resize when the pane is shown again (mobile switch, tab change) or the layout changes.
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(buildOption(rows, layout, skuNames, sourceNote), true);
  }, [rows, layout, skuNames, sourceNote, scheme]);

  return (
    <div
      ref={ref}
      style={{ width: "100%", height: chartHeight(rows.length, layout) }}
      role="img"
      aria-label="Biểu đồ dự báo nhu cầu với dải P10 đến P90. Số liệu chi tiết ở bảng bên dưới."
    />
  );
}

export default memo(ForecastChart);
