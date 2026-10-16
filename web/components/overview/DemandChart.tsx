"use client";

// Loaded with next/dynamic (ssr: false), like ForecastChart: ECharts needs `window`. One SKU at a time, so the
// band and the lines never add up different units. Past days carry `actual`, future days the P10/P50/P90.
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { memo, useEffect, useRef } from "react";
import type { DemandPoint } from "@/lib/brief-types";
import { fmtNum } from "@/lib/format";
import { cssVar, prefersReducedMotion } from "@/lib/theme";

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

const day = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

function tooltip(p: DemandPoint): string {
  const head = `<b>${day(p.date)}</b>`;
  if (p.actual != null) return `${head}<br/>Thực tế: ${fmtNum(p.actual)}`;
  return `${head}<br/>Dự báo P50: ${fmtNum(p.p50)}<br/>Khoảng P10 đến P90: ${fmtNum(p.p10)} đến ${fmtNum(p.p90)}`;
}

function DemandChart({ points }: { points: DemandPoint[] }) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, { renderer: "canvas" });
    const green = cssVar("--green", "#1f6b45");
    const ink = cssVar("--ink", "#17221c");
    const lime = cssVar("--lime", "#a6e22e");
    const ink3 = cssVar("--ink-3", "#66736b");
    const line = cssVar("--line", "#dcdfd6");
    const pts = [...points].sort((a, b) => a.date.localeCompare(b.date));
    const lastActual = pts.reduce((k, p, i) => (p.actual != null ? i : k), -1);
    // The dashed forecast starts from the last actual point so the two lines read as one story.
    const forecast = pts.map((p, i) => (i === lastActual && p.p50 == null ? p.actual : p.p50));
    const hasActual = lastActual >= 0;
    chart.setOption({
      animation: !prefersReducedMotion(),
      animationDuration: 900,
      grid: { left: 8, right: 16, top: 16, bottom: 24, containLabel: true },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: pts.map((p) => day(p.date)),
        axisLine: { lineStyle: { color: line } },
        axisTick: { show: false },
        axisLabel: { color: ink3, fontSize: 11 },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { color: line, type: "dashed" } }, axisLabel: { color: ink3, fontSize: 11 } },
      tooltip: { trigger: "axis", formatter: (ps: { dataIndex: number }[]) => tooltip(pts[ps[0]?.dataIndex ?? 0]) },
      series: [
        // P10 base (invisible) + (P90 − P10) stacked on it = the uncertainty band (forecast days only).
        { type: "line", data: pts.map((p) => p.p10), stack: "band", lineStyle: { opacity: 0 }, symbol: "none", silent: true },
        {
          type: "line",
          data: pts.map((p) => (p.p10 != null && p.p90 != null ? Math.max(0, p.p90 - p.p10) : null)),
          stack: "band",
          lineStyle: { opacity: 0 },
          symbol: "none",
          areaStyle: { color: lime, opacity: 0.28 },
          silent: true,
        },
        {
          type: "line",
          data: forecast,
          smooth: 0.3,
          symbol: "circle",
          symbolSize: 7,
          lineStyle: { color: green, width: 2.5, type: hasActual ? "dashed" : "solid" },
          itemStyle: { color: green },
        },
        ...(hasActual
          ? [
              {
                type: "line",
                data: pts.map((p) => p.actual),
                smooth: 0.3,
                symbol: "circle",
                symbolSize: 7,
                lineStyle: { color: ink, width: 2.5 },
                itemStyle: { color: ink },
              },
            ]
          : []),
      ],
    });
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [points]);

  return <div ref={box} style={{ width: "100%", height: 210 }} role="img" aria-label="Biểu đồ nhu cầu thực tế và dự báo" />;
}

export default memo(DemandChart);
