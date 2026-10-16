"use client";

// Client-only (next/dynamic ssr:false): VietMap GL needs `window`. Own stores are exact points; other chains are
// only soft discs over anonymised cells (never points); today's transfers are mango arcs with their unit count.
import vietmapgl from "@vietmap/vietmap-gl-js/dist/vietmap-gl";
import "@vietmap/vietmap-gl-js/dist/vietmap-gl.css";
import { memo, useEffect, useMemo, useRef } from "react";
import type { NetworkView } from "@/lib/brief-types";
import { prefersReducedMotion } from "@/lib/theme";
import { disposeMap, logMapErrors, MAP_LOCALE, quietBasemap, STYLE_URL, VIETMAP_KEY } from "@/components/dashboard/vietmapBase";
import { buildNetworkGeo, type NetworkGeo } from "./networkGeo";
import n from "./network.module.css";

const COLORS = { forest: "#1f6b45", lime: "#a6e22e", mango: "#ffa41b", cell: "#5d6b63", white: "#ffffff" };

function addLayers(map: vietmapgl.Map, geo: NetworkGeo) {
  map.addSource("fm-cells", { type: "geojson", data: geo.cells as never });
  map.addSource("fm-flows", { type: "geojson", data: geo.flows as never });
  map.addSource("fm-stores", { type: "geojson", data: geo.stores as never });
  map.addLayer({ id: "fm-cells-fill", type: "fill", source: "fm-cells", paint: { "fill-color": COLORS.cell, "fill-opacity": 0.08 } });
  map.addLayer({
    id: "fm-cells-line",
    type: "line",
    source: "fm-cells",
    paint: { "line-color": COLORS.cell, "line-opacity": 0.45, "line-width": 1.2, "line-dasharray": [2, 2] },
  });
  map.addLayer({
    id: "fm-flows",
    type: "line",
    source: "fm-flows",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": COLORS.mango,
      "line-width": ["interpolate", ["linear"], ["get", "units"], 1, 2.5, 80, 6],
      "line-opacity": 0.95,
    },
  });
  map.addLayer({
    id: "fm-stores",
    type: "circle",
    source: "fm-stores",
    paint: {
      "circle-radius": 8,
      "circle-color": COLORS.forest,
      "circle-stroke-width": 3,
      "circle-stroke-color": ["case", ["get", "isNew"], COLORS.lime, COLORS.white],
    },
  });
}

function labelEl(l: NetworkGeo["labels"][number]): HTMLElement {
  const el = document.createElement("div");
  el.className = l.kind === "store" ? n.storeLabel : l.kind === "cell" ? n.cellLabel : n.flowLabel;
  el.textContent = l.text;
  if (l.isNew) {
    const tag = document.createElement("span");
    tag.textContent = "mới mở";
    el.append(" ", tag);
  }
  return el;
}

function NetworkMap({ view }: { view: NetworkView }) {
  const geo = useMemo(() => buildNetworkGeo(view), [view]);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el || !VIETMAP_KEY) return;
    const map = new vietmapgl.Map({ container: el, style: STYLE_URL, center: [106.69, 10.8], zoom: 12, cooperativeGestures: true, locale: MAP_LOCALE });
    logMapErrors(map, "NetworkMap");
    map.addControl(new vietmapgl.NavigationControl({ showCompass: false }), "top-right");
    const markers = geo.labels.map((l) =>
      new vietmapgl.Marker({ element: labelEl(l), anchor: l.kind === "store" ? "left" : "center", offset: l.kind === "store" ? [12, 0] : [0, 0] })
        .setLngLat(l.at)
        .addTo(map),
    );
    map.on("style.load", () => {
      quietBasemap(map);
      addLayers(map, geo);
      const pts = geo.bounds;
      if (pts.length) {
        const b = pts.reduce((acc, p) => acc.extend(p), new vietmapgl.LngLatBounds(pts[0], pts[0]));
        map.fitBounds(b, { padding: 72, maxZoom: 14, animate: !prefersReducedMotion(), duration: 1600 });
      }
    });
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      markers.forEach((m) => m.remove());
      disposeMap(map);
    };
  }, [geo]);

  if (!VIETMAP_KEY) {
    return <p className={n.mapEmpty}>Chưa cấu hình khóa VietMap: đặt NEXT_PUBLIC_VIETMAP_API_KEY rồi build lại web.</p>;
  }
  return <div ref={box} className={n.mapCanvas} data-testid="network-map" />;
}

export default memo(NetworkMap);
