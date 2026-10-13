import type { ToolSlot } from "@/components/workspace/useDirectTools";

// Warms the heavy client-only chunks (ECharts ~300 kB, Leaflet ~150 kB) when the user points at a tool
// button, so they download while the computation runs instead of after its panel mounts. The panels keep
// their own inline next/dynamic(() => import(...)) calls; the bundler serves both from one chunk.

export function preloadForSlot(slot: ToolSlot) {
  if (slot === "forecast") void import("./ForecastChart");
  else if (slot === "route") void import("./RouteMap");
}
