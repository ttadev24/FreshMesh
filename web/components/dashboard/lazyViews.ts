import type { FlowId } from "@/components/workspace/useConversation";

// Warms the heavy client-only chunks (ECharts ~300 kB, Leaflet ~150 kB) when the user points at a demo
// flow, so they download while the agent turn runs instead of after its panel mounts. The panels keep
// their own inline next/dynamic(() => import(...)) calls; the bundler serves both from one chunk.

/** Flow 1 draws the forecast chart; flows 2 (routed transfer) and 3 draw the route map. */
export function preloadForFlow(flow: FlowId) {
  void (flow === 1 ? import("./ForecastChart") : import("./RouteMap"));
}
