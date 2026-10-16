"use client";

// Client-only (next/dynamic ssr:false): VietMap GL JS (MapLibre based, WebGL) needs `window`. The route plan is
// drawn as two GeoJSON layers (vehicle paths, circle markers) built in routeGeo.ts. Vector styles are fetched with
// the browser-side key NEXT_PUBLIC_VIETMAP_API_KEY: restrict it by domain / IP in the VietMap console.
import vietmapgl from "@vietmap/vietmap-gl-js/dist/vietmap-gl";
import "@vietmap/vietmap-gl-js/dist/vietmap-gl.css";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { prefersReducedMotion, useThemeTokens } from "@/lib/theme";
import type { LatLng, RoutePlanView, Store } from "@/lib/types";
import { VEHICLE_COLORS } from "./routeColors";
import { buildRouteGeo, type RouteGeo } from "./routeGeo";
import s from "./dashboard.module.css";

const API_KEY = process.env.NEXT_PUBLIC_VIETMAP_API_KEY ?? "";

// lm = "SEA Map Light": the muted basemap the light-only UI is designed around (tm = street, dm = dark).
const STYLE_URL = `https://maps.vietmap.vn/maps/styles/lm/style.json?apikey=${encodeURIComponent(API_KEY)}`;

const MARKER_TOKENS = {
  store: ["--green-strong", "#134f35"],
  blue: ["--blue", "#1c5cb3"],
  amber: ["--amber-fill", "#e9971f"],
  red: ["--red", "#b0261b"],
  surface: ["--surface", "#fbfcfb"],
} as const;

/** Ho Chi Minh City centre (Bến Thành), used until the plan's own points are fitted. */
const HCMC: LatLng = [10.7725, 106.698];

const LOCALE = {
  "CooperativeGesturesHandler.WindowsHelpText": "Giữ Ctrl và cuộn chuột để thu phóng bản đồ",
  "CooperativeGesturesHandler.MacHelpText": "Giữ ⌘ và cuộn chuột để thu phóng bản đồ",
  "CooperativeGesturesHandler.MobileHelpText": "Dùng hai ngón tay để di chuyển bản đồ",
  "NavigationControl.ZoomIn": "Phóng to",
  "NavigationControl.ZoomOut": "Thu nhỏ",
  "FullscreenControl.Enter": "Phóng to toàn màn hình",
  "FullscreenControl.Exit": "Thoát toàn màn hình",
  "AttributionControl.ToggleAttribution": "Bật/tắt ghi nguồn bản đồ",
  "AttributionControl.MapFeedback": "Góp ý bản đồ",
};

const ROUTES = "fm-routes";
const POINTS = "fm-points";
const ARROW = "fm-arrow";
const FLOW = "fm-routes-flow";

// Flowing-light animation: short dashes (units of the line width) drift along the line direction. A dash
// array always starts at the line start, so each frame is the same dash pattern phase-shifted by `shift`.
const FLOW_DASH = 3;
const FLOW_PERIOD = 12;
const FLOW_STEPS = 24;
const FLOW_FRAME_MS = 60;
const FLOW_FRAMES: number[][] = Array.from({ length: FLOW_STEPS }, (_, k) => {
  const shift = (k * FLOW_PERIOD) / FLOW_STEPS;
  return shift + FLOW_DASH <= FLOW_PERIOD
    ? [0, shift, FLOW_DASH, FLOW_PERIOD - shift - FLOW_DASH]
    : [shift + FLOW_DASH - FLOW_PERIOD, FLOW_PERIOD - FLOW_DASH, FLOW_PERIOD - shift, 0];
});

/** Starts the flowing-light animation; returns its stop function. No-op with reduced motion. */
function startFlow(map: vietmapgl.Map): () => void {
  if (prefersReducedMotion()) return () => {};
  let raf = 0;
  let last = 0;
  let k = 0;
  const tick = (t: number) => {
    raf = requestAnimationFrame(tick);
    if (t - last < FLOW_FRAME_MS || !map.getLayer(FLOW)) return;
    last = t;
    k = (k + 1) % FLOW_FRAMES.length;
    map.setPaintProperty(FLOW, "line-dasharray", FLOW_FRAMES[k]);
  };
  raf = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(raf);
}

/** White chevron with a thin dark outline, pointing east; the line layout rotates it along the path. */
function addArrowImage(map: vietmapgl.Map) {
  if (map.hasImage(ARROW)) return;
  const size = 32;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.beginPath();
  ctx.moveTo(4, 3);
  ctx.lineTo(29, 16);
  ctx.lineTo(4, 29);
  ctx.lineTo(11, 16);
  ctx.closePath();
  ctx.lineJoin = "round";
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = "rgba(20,30,25,0.85)";
  ctx.stroke();
  ctx.fillStyle = "#fff";
  ctx.fill();
  map.addImage(ARROW, ctx.getImageData(0, 0, size, size), { pixelRatio: 2 });
}

/** (Re)adds the plan sources and layers: needed after every style load, since a style swap drops them. */
function addPlanLayers(map: vietmapgl.Map, geo: RouteGeo) {
  if (map.getSource(ROUTES)) return;
  map.addSource(ROUTES, { type: "geojson", data: geo.lines as never });
  map.addSource(POINTS, { type: "geojson", data: geo.points as never });
  const line = { "line-cap": "round", "line-join": "round" } as const;
  // Each vehicle is shifted sideways by its own `offset`, so two vehicles on the same road run side by side.
  // White casing under the coloured line keeps each colour readable on light and dark basemaps.
  map.addLayer({
    id: `${ROUTES}-casing`,
    type: "line",
    source: ROUTES,
    layout: line,
    paint: { "line-color": "#ffffff", "line-width": 8, "line-offset": ["get", "offset"], "line-opacity": ["*", 0.9, ["get", "opacity"]] },
  });
  map.addLayer({
    id: ROUTES,
    type: "line",
    source: ROUTES,
    layout: line,
    paint: { "line-color": ["get", "color"], "line-width": 5.5, "line-offset": ["get", "offset"], "line-opacity": ["*", 0.9, ["get", "opacity"]] },
  });
  // Direction of travel, kept calm: a thin light flows along each path from the start to the end (animated by
  // startFlow). With reduced motion nothing moves, so a few widely spaced chevrons show the direction instead.
  if (prefersReducedMotion()) {
    addArrowImage(map);
    map.addLayer({
      id: `${ROUTES}-arrows`,
      type: "symbol",
      source: ROUTES,
      layout: {
        "symbol-placement": "line",
        "symbol-spacing": 180,
        "icon-image": ARROW,
        "icon-size": 1.1,
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
        "icon-rotation-alignment": "map",
      },
      paint: { "icon-opacity": ["get", "opacity"] },
    });
  } else {
    map.addLayer({
      id: FLOW,
      type: "line",
      source: ROUTES,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#ffffff",
        "line-width": 2.2,
        "line-offset": ["get", "offset"],
        "line-opacity": ["*", 0.75, ["get", "opacity"]],
        "line-dasharray": FLOW_FRAMES[0],
      },
    });
  }
  map.addLayer({
    id: POINTS,
    type: "circle",
    source: POINTS,
    layout: { "circle-sort-key": ["get", "z"] },
    paint: {
      "circle-radius": ["get", "radius"],
      "circle-color": ["get", "fill"],
      "circle-stroke-color": ["get", "stroke"],
      "circle-stroke-width": ["get", "strokeWidth"],
      "circle-opacity": ["get", "opacity"],
      "circle-stroke-opacity": ["get", "opacity"],
    },
  });
  // Delivery order number inside the marker (same numbers as the stop list under the map).
  map.addLayer({
    id: `${POINTS}-labels`,
    type: "symbol",
    source: POINTS,
    filter: ["!=", ["get", "label"], ""],
    layout: {
      "text-field": ["get", "label"],
      "text-font": ["Noto Sans Bold"],
      "text-size": 11,
      "text-allow-overlap": true,
      "text-ignore-placement": true,
    },
    paint: { "text-color": "#ffffff" },
  });
}

/** Fits the plotted points; in fullscreen the floating summary bar covers the top, so leave room for it. */
function fitPlan(map: vietmapgl.Map, points: [number, number][]) {
  if (!points.length) return;
  const bounds = points.reduce((b, p) => b.extend(p), new vietmapgl.LngLatBounds(points[0], points[0]));
  const top = document.fullscreenElement ? 110 : 28;
  map.fitBounds(bounds, { padding: { top, bottom: 28, left: 28, right: 28 }, maxZoom: 15, animate: !prefersReducedMotion() });
}

/** Store label: the name, then one line per vehicle that leaves from it, in the vehicle's colour. */
function storeLabel(name: string, routes: RoutePlanView["routes"], focus: number | null) {
  const root = document.createElement("div");
  const b = document.createElement("b");
  b.textContent = name;
  root.append(b);
  routes.forEach((r, i) => {
    if (focus != null && focus !== r.index) return;
    const row = document.createElement("div");
    row.style.cssText = "display:flex;align-items:center;gap:6px;font-weight:500";
    const dot = document.createElement("span");
    dot.style.cssText = `width:12px;height:4px;border-radius:2px;background:${VEHICLE_COLORS[i % VEHICLE_COLORS.length]}`;
    row.append(dot, document.createTextNode(`Xe ${r.index} xuất phát`));
    root.append(row);
  });
  return root;
}

function popupContent(title: string, body: string) {
  // DOM nodes + textContent: server strings (store names, reasons) are never parsed as HTML.
  const root = document.createElement("div");
  const b = document.createElement("b");
  b.textContent = title;
  root.append(b);
  body.split("\n").forEach((line) => {
    root.append(document.createElement("br"), document.createTextNode(line));
  });
  return root;
}

function RouteMap({ plan, storeName, stores }: { plan: RoutePlanView; storeName: string; stores?: Store[] }) {
  const colors = useThemeTokens(MARKER_TOKENS);
  // One vehicle can be picked to look at it alone; the pick belongs to the plan it was made on.
  const [picked, setPicked] = useState<{ plan: RoutePlanView; index: number } | null>(null);
  const focus = picked && picked.plan === plan && plan.routes.some((r) => r.index === picked.index) ? picked.index : null;
  const geo = useMemo(() => buildRouteGeo(plan, storeName, stores, colors, focus), [plan, storeName, stores, colors, focus]);
  const fitRef = useRef<[number, number][]>([]);

  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<vietmapgl.Map | null>(null);
  const geoRef = useRef(geo);
  const labelRef = useRef<vietmapgl.Popup | null>(null);

  const start: LatLng = plan.store ? [plan.store.lat, plan.store.lng] : HCMC;

  useEffect(() => {
    const el = box.current;
    if (!el || !API_KEY) return;
    const map = new vietmapgl.Map({
      container: el,
      style: STYLE_URL,
      center: [start[1], start[0]],
      zoom: 13,
      cooperativeGestures: true,
      locale: LOCALE,
    });
    mapRef.current = map;
    // vietmapgl's Evented.fire() prints any "error" event straight to console.error when nobody is
    // listening (so internal errors are never silently dropped). remove() cancels the in-flight style
    // load, which fires exactly such an event; without a handler that is expected abort gets logged as
    // if it were a real failure. A real error (bad key, network down, broken style) still reaches the
    // console here, just via our own call instead of the library's fallback.
    map.on("error", (e) => {
      if (e.error?.name !== "AbortError") console.error("[RouteMap]", e.error);
    });
    // Controls sit on the right so the summary bar of the fullscreen view (top-left) never covers them. The
    // control takes the whole panel shell (summary + map) fullscreen; it also lifts cooperative gestures there.
    map.addControl(new vietmapgl.NavigationControl({ showCompass: false }), "top-right");
    const shell = el.closest<HTMLElement>("[data-map-shell]");
    map.addControl(new vietmapgl.FullscreenControl({ container: shell ?? undefined }), "top-right");

    const stopFlow = startFlow(map);
    map.on("style.load", () => {
      addPlanLayers(map, geoRef.current);
      el.dataset.layersReady = "true";
    });

    // Hover label (vehicle path / other store) and click popup (markers). One popup each, reused.
    const hover = new vietmapgl.Popup({ closeButton: false, closeOnClick: false, className: "fm-map-tip", offset: 10 });
    const click = new vietmapgl.Popup({ offset: 12 });
    const hit = (e: vietmapgl.MapMouseEvent) =>
      map.queryRenderedFeatures(e.point, { layers: [POINTS, ROUTES].filter((id) => map.getLayer(id)) });
    map.on("mousemove", (e) => {
      const found = hit(e);
      map.getCanvas().style.cursor = found.length ? "pointer" : "";
      const f = found.find((x) => x.properties?.tip);
      if (!f) return void hover.remove();
      hover
        .setLngLat(f.geometry.type === "Point" ? (f.geometry.coordinates as [number, number]) : e.lngLat)
        .setText(String(f.properties.tip))
        .addTo(map);
    });
    map.on("mouseout", () => hover.remove());
    map.on("click", (e) => {
      const f = hit(e).find((x) => x.properties?.title);
      if (!f || f.geometry.type !== "Point") return;
      hover.remove();
      click
        .setLngLat(f.geometry.coordinates as [number, number])
        .setDOMContent(popupContent(String(f.properties.title), String(f.properties.body ?? "")))
        .addTo(map);
    });

    // Entering / leaving fullscreen changes the map size. Event order against the layout change differs between
    // browsers, so wait for the new size to settle, then re-measure and refit the route to the new frame.
    let refit: ReturnType<typeof setTimeout> | undefined;
    const onFullscreen = () => {
      clearTimeout(refit);
      refit = setTimeout(() => {
        map.resize();
        fitPlan(map, fitRef.current);
      }, 250);
    };
    document.addEventListener("fullscreenchange", onFullscreen);

    // The map may be mounted in a hidden pane (mobile switch / tab): re-measure when it appears.
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);
    return () => {
      stopFlow();
      clearTimeout(refit);
      ro.disconnect();
      document.removeEventListener("fullscreenchange", onFullscreen);
      labelRef.current?.remove();
      labelRef.current = null;
      mapRef.current = null;
      // remove() cancels the in-flight style/sprite request; Style._remove() (vietmapgl internals) clears
      // its own link to the map before that request's rejection runs, so the resulting "error" event has
      // nobody left to catch it and vietmapgl prints it straight to console.error (harmless, but noisy —
      // hit on every mount in dev, since React Strict Mode mounts, cleans up and mounts again). Waiting for
      // the style to finish loading first removes that race entirely; the timeout bounds the wait in case
      // the style never loads (bad key, network down), so the map is still disposed either way.
      let removed = false;
      const removeOnce = () => {
        if (removed) return;
        removed = true;
        map.remove();
      };
      if (map.isStyleLoaded()) {
        removeOnce();
      } else {
        const timer = setTimeout(removeOnce, 8000);
        map.once("load", () => {
          clearTimeout(timer);
          removeOnce();
        });
      }
    };
    // The map is created once; plan, theme and size changes are applied by the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // New plan / colours: refresh the data the layers read.
  useEffect(() => {
    geoRef.current = geo;
    const map = mapRef.current;
    if (!map) return;
    if (box.current) {
      box.current.dataset.paths = String(geo.lines.features.length);
      box.current.dataset.markers = String(geo.points.features.length);
    }
    (map.getSource(ROUTES) as vietmapgl.GeoJSONSource | undefined)?.setData(geo.lines as never);
    (map.getSource(POINTS) as vietmapgl.GeoJSONSource | undefined)?.setData(geo.points as never);
  }, [geo]);

  // Refit when the plan or the picked vehicle changes, not when a theme flip rebuilds the marker colours.
  useEffect(() => {
    const map = mapRef.current;
    const pts = (focus != null ? geo.routeBounds.get(focus) : undefined) ?? geo.bounds;
    fitRef.current = pts;
    if (map) fitPlan(map, pts);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan, focus]);

  // Permanent label above the starting store: its name and which vehicles start from it.
  useEffect(() => {
    const map = mapRef.current;
    labelRef.current?.remove();
    labelRef.current = null;
    if (!map || !plan.store) return;
    labelRef.current = new vietmapgl.Popup({
      closeButton: false,
      closeOnClick: false,
      closeOnMove: false,
      className: "fm-map-tip",
      offset: 16,
      anchor: "bottom",
    })
      .setLngLat([plan.store.lng, plan.store.lat])
      .setDOMContent(storeLabel(storeName, plan.routes, focus))
      .addTo(map);
  }, [plan.store, plan.routes, storeName, focus]);

  if (!API_KEY) {
    return (
      <p className={s.mapEmpty} data-testid="map-key-missing">
        Chưa cấu hình khóa VietMap: đặt NEXT_PUBLIC_VIETMAP_API_KEY trong web/.env.local rồi build lại web.
      </p>
    );
  }
  return (
    <div style={{ position: "relative", height: "100%", width: "100%" }}>
      <div ref={box} style={{ height: "100%", width: "100%" }} />
      {plan.routes.length > 1 ? (
        <div className={s.mapChips} role="group" aria-label="Chọn xe để xem riêng" data-testid="vehicle-focus">
          <button type="button" aria-pressed={focus == null} onClick={() => setPicked(null)}>
            Tất cả xe
          </button>
          {plan.routes.map((r, i) => (
            <button
              key={r.index}
              type="button"
              aria-pressed={focus === r.index}
              onClick={() => setPicked(focus === r.index ? null : { plan, index: r.index })}
            >
              <span className={s.swatch} style={{ background: VEHICLE_COLORS[i % VEHICLE_COLORS.length] }} aria-hidden="true" />
              Xe {r.index}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default memo(RouteMap);
