// Route plan -> GeoJSON for the VietMap GL map. The API (and the rest of the web app) uses [lat, lng];
// GeoJSON and the GL SDK use [lng, lat], so every coordinate is flipped here and nowhere else.
import type { LatLng, RoutePlanView, Store } from "@/lib/types";
import { fmtKm } from "@/lib/format";
import { VEHICLE_COLORS } from "./routeColors";

export interface RouteColors {
  store: string;
  blue: string;
  amber: string;
  red: string;
  surface: string;
}

type Feature<G> = {
  type: "Feature";
  geometry: G;
  properties: Record<string, string | number | boolean>;
};
type Point = { type: "Point"; coordinates: [number, number] };
type Line = { type: "LineString"; coordinates: [number, number][] };
export interface Collection<G> {
  type: "FeatureCollection";
  features: Feature<G>[];
}

export interface RouteGeo {
  lines: Collection<Line>;
  points: Collection<Point>;
  /** Every plotted point as [lng, lat], for fitting the view. */
  bounds: [number, number][];
  /** Points of each vehicle ("Xe n" = route index n) as [lng, lat]: the view when one vehicle is picked. */
  routeBounds: Map<number, [number, number][]>;
}

const lngLat = ([lat, lng]: LatLng): [number, number] => [lng, lat];

// Draw order inside the single circle layer (higher = on top).
const Z = { otherStore: 0, pickup: 1, stop: 2, atRisk: 3, store: 4 } as const;

/** Sideways gap (px) between vehicle lines: where two vehicles share a road they run side by side. */
export const LINE_GAP_PX = 5.5;
const DIM = 0.18;

function point(
  at: LatLng,
  z: number,
  style: { radius: number; fill: string; stroke: string; strokeWidth: number; opacity?: number },
  text: { tip?: string; title?: string; body?: string; label?: string },
): Feature<Point> {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: lngLat(at) },
    properties: {
      z,
      radius: style.radius,
      fill: style.fill,
      stroke: style.stroke,
      strokeWidth: style.strokeWidth,
      opacity: style.opacity ?? 1,
      // Hover label, and click popup (title + body lines separated by \n). Plain text: the map never builds HTML from it.
      tip: text.tip ?? "",
      title: text.title ?? "",
      body: text.body ?? "",
      // Delivery order number drawn inside the marker ("" = none).
      label: text.label ?? "",
    },
  };
}

/**
 * `focus` = route index of the one vehicle to show ("Xe n"); the others fade out. null shows every vehicle.
 */
export function buildRouteGeo(
  plan: RoutePlanView,
  storeName: string,
  stores: Store[] | undefined,
  colors: RouteColors,
  focus: number | null = null,
): RouteGeo {
  const vehicle = (i: number) => VEHICLE_COLORS[i % VEHICLE_COLORS.length];
  const points: Feature<Point>[] = [];
  const lines: Feature<Line>[] = [];
  const bounds: [number, number][] = [];
  const routeBounds = new Map<number, [number, number][]>();
  const plot = (at: LatLng, route?: number) => {
    bounds.push(lngLat(at));
    if (route != null) routeBounds.set(route, [...(routeBounds.get(route) ?? []), lngLat(at)]);
  };
  const fade = (route: number) => (focus == null || focus === route ? 1 : DIM);

  if (plan.store) plot([plan.store.lat, plan.store.lng]);

  // Delivery numbers per locker: "2, 5" = the 2nd and 5th stops of the vehicles that drop off there.
  const lockerStops = new Map<string, number[]>();
  const lockerRoutes = new Map<string, Set<number>>();

  plan.routes.forEach((r, i) => {
    const offset = (i - (plan.routes.length - 1) / 2) * LINE_GAP_PX;
    r.path.forEach((p) => plot(p, r.index));
    if (r.path.length > 1) {
      lines.push({
        type: "Feature",
        geometry: { type: "LineString", coordinates: r.path.map(lngLat) },
        properties: {
          color: vehicle(i),
          offset,
          opacity: fade(r.index),
          tip: `Xe ${r.index}: ${r.stops.length} điểm dừng${r.road_path_km != null ? `, ${fmtKm(r.road_path_km)} theo đường bộ` : ""}`,
        },
      });
    }
    r.stops.forEach((st, k) => {
      const n = k + 1; // same number as in the stop list under the map
      if (st.lat == null || st.lng == null) return;
      plot([st.lat, st.lng], r.index);
      if (st.kind === "pickup" && st.pickup_point_id) {
        lockerStops.set(st.pickup_point_id, [...(lockerStops.get(st.pickup_point_id) ?? []), n]);
        lockerRoutes.set(st.pickup_point_id, new Set([...(lockerRoutes.get(st.pickup_point_id) ?? []), r.index]));
      }
      if (st.kind !== "home") return;
      points.push(
        point(
          [st.lat, st.lng],
          Z.stop,
          {
            // The vehicle's first delivery is drawn larger: it shows which way the vehicle leaves the store.
            radius: n === 1 ? 12 : 9,
            fill: vehicle(i),
            stroke: st.late ? colors.red : colors.surface,
            strokeWidth: st.late ? 3 : n === 1 ? 2.5 : 1.5,
            opacity: fade(r.index),
          },
          {
            tip: n === 1 ? `Xe ${r.index}: điểm giao đầu tiên` : undefined,
            title: `Đơn ${st.order_id}`,
            body: `Xe ${r.index}, điểm dừng ${n}${n === 1 ? " (đầu tiên)" : ""}, giao tận nhà\nETA +${st.eta_min} phút${st.late ? " (trễ)" : ""}`,
            label: focus == null || focus === r.index ? String(n) : "",
          },
        ),
      );
    });
  });

  plan.pickup_points.forEach((p) => {
    plot([p.lat, p.lng]);
    const nums = lockerStops.get(p.pickup_point_id) ?? [];
    const used = lockerRoutes.get(p.pickup_point_id);
    const shown = focus == null || (used?.has(focus) ?? false);
    points.push(
      point(
        [p.lat, p.lng],
        Z.pickup,
        { radius: nums.length ? 9 : 8, fill: colors.blue, stroke: colors.surface, strokeWidth: 2, opacity: shown ? 1 : DIM },
        {
          title: "Điểm nhận / tủ",
          body: `${p.name} (${p.pickup_point_id})${nums.length ? `\nĐiểm dừng số ${nums.join(", ")}` : ""}`,
          label: shown && nums.length ? (nums.length > 1 ? `${nums[0]}+` : String(nums[0])) : "",
        },
      ),
    );
  });

  plan.at_risk.forEach((a) => {
    if (a.lat == null || a.lng == null) return;
    plot([a.lat, a.lng]);
    points.push(
      point(
        [a.lat, a.lng],
        Z.atRisk,
        { radius: 7, fill: colors.amber, stroke: colors.surface, strokeWidth: 2, opacity: focus == null ? 1 : DIM },
        { title: `Đơn có nguy cơ ${a.order_id}`, body: a.reason_vi },
      ),
    );
  });

  // The other stores of the chain give the route its neighbourhood context; they do not move the fit.
  (stores ?? [])
    .filter((st) => st.store_id !== plan.store_id && Number.isFinite(st.lat) && Number.isFinite(st.lng))
    .forEach((st) =>
      points.push(
        point([st.lat, st.lng], Z.otherStore, { radius: 6, fill: colors.surface, stroke: colors.store, strokeWidth: 2, opacity: 0.9 }, { tip: st.name }),
      ),
    );

  if (plan.store) {
    points.push(
      point(
        [plan.store.lat, plan.store.lng],
        Z.store,
        { radius: 10, fill: colors.store, stroke: colors.surface, strokeWidth: 3 },
        { title: "Cửa hàng xuất phát", body: storeName },
      ),
    );
  }

  return {
    lines: { type: "FeatureCollection", features: lines },
    points: { type: "FeatureCollection", features: points },
    bounds,
    routeBounds,
  };
}
