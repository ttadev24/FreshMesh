"use client";

// Loaded with next/dynamic (ssr: false), like ForecastChart: ECharts needs `window`. One SKU at a time, so the
// band and the line never add up different units.
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { memo, useEffect, useRef } from "react";
import { fmtNum } from "@/lib/format";
import { cssVar, prefersReducedMotion } from "@/lib/theme";
import type { ForecastRow } from "@/lib/types";

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

const day = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

function DemandChart({ rows }: { rows: ForecastRow[] }) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, { renderer: "canvas" });
    const green = cssVar("--green", "#1f6b45");
    const lime = cssVar("--lime", "#a6e22e");
    const ink3 = cssVar("--ink-3", "#66736b");
    const line = cssVar("--line", "#dcdfd6");
    const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
    chart.setOption({
      animation: !prefersReducedMotion(),
      animationDuration: 900,
      grid: { left: 8, right: 16, top: 16, bottom: 24, containLabel: true },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: sorted.map((r) => day(r.date)),
        axisLine: { lineStyle: { color: line } },
        axisTick: { show: false },
        axisLabel: { color: ink3, fontSize: 11 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: line, type: "dashed" } },
        axisLabel: { color: ink3, fontSize: 11 },
      },
      tooltip: {
        trigger: "axis",
        formatter: (ps: { dataIndex: number }[]) => {
          const r = sorted[ps[0]?.dataIndex ?? 0];
          return r
            ? `<b>${day(r.date)}</b><br/>Dự báo P50: ${fmtNum(r.p50)}<br/>Khoảng P10 đến P90: ${fmtNum(r.p10)} đến ${fmtNum(r.p90)}<br/>Độ tin cậy: ${r.confidence}`
            : "";
        },
      },
      series: [
        // P10 base (invisible) + (P90 − P10) stacked on it = the uncertainty band.
        { type: "line", data: sorted.map((r) => r.p10), stack: "band", lineStyle: { opacity: 0 }, symbol: "none", silent: true },
        {
          type: "line",
          data: sorted.map((r) => Math.max(0, r.p90 - r.p10)),
          stack: "band",
          lineStyle: { opacity: 0 },
          symbol: "none",
          areaStyle: { color: lime, opacity: 0.28 },
          silent: true,
        },
        {
          type: "line",
          data: sorted.map((r) => r.p50),
          smooth: 0.3,
          symbol: "circle",
          symbolSize: 7,
          lineStyle: { color: green, width: 2.5 },
          itemStyle: { color: green },
        },
      ],
    });
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [rows]);

  return <div ref={box} style={{ width: "100%", height: 210 }} role="img" aria-label="Biểu đồ dự báo nhu cầu 7 ngày tới" />;
}

export default memo(DemandChart);
