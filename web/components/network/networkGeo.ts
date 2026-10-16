// GeoJSON for the network map: own stores (exact), other chains (anonymised cells drawn as soft discs),
// today's transfers (curved arcs). Coordinates are [lng, lat] as GeoJSON expects.
import type { NetworkView } from "@/lib/brief-types";
import type { Collection } from "@/components/dashboard/routeGeo";

type Lnglat = [number, number];
type Point = { type: "Point"; coordinates: Lnglat };
type Line = { type: "LineString"; coordinates: Lnglat[] };
type Polygon = { type: "Polygon"; coordinates: Lnglat[][] };
const M_PER_DEG_LAT = 111_320;

/** Cells come rounded to 0.01° (~1.1 km) or, when that would expose a lone store, merged to 0.1° (~11 km). */
function cellRadiusM(lat: number, lng: number): number {
  const onTenth = (v: number) => Math.abs(v * 10 - Math.round(v * 10)) < 1e-6;
  return onTenth(lat) && onTenth(lng) ? 5_500 : 650;
}

function disc(lat: number, lng: number, radiusM: number, steps = 64): Lnglat[] {
  const dLat = radiusM / M_PER_DEG_LAT;
  const dLng = radiusM / (M_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180));
  const ring: Lnglat[] = [];
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    ring.push([lng + dLng * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return ring;
}

/** Quadratic arc bending to the left of the travel direction, so A→B and B→A never overlap. */
function arc(from: Lnglat, to: Lnglat, bend = 0.22, steps = 40): Lnglat[] {
  const mx = (from[0] + to[0]) / 2;
  const my = (from[1] + to[1]) / 2;
  const cx = mx - (to[1] - from[1]) * bend;
  const cy = my + (to[0] - from[0]) * bend;
  const pts: Lnglat[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const u = 1 - t;
    pts.push([u * u * from[0] + 2 * u * t * cx + t * t * to[0], u * u * from[1] + 2 * u * t * cy + t * t * to[1]]);
  }
  return pts;
}

export interface NetworkGeo {
  stores: Collection<Point>;
  cells: Collection<Polygon>;
  flows: Collection<Line>;
  /** Label anchors (HTML markers): stores, cells, flow midpoints. */
  labels: { kind: "store" | "cell" | "flow"; at: Lnglat; text: string; isNew?: boolean }[];
  bounds: Lnglat[];
}

export function buildNetworkGeo(view: NetworkView): NetworkGeo {
  const byId = new Map(view.stores.map((s) => [s.store_id, s]));
  const labels: NetworkGeo["labels"] = [];
  const bounds: Lnglat[] = [];

  const stores = view.stores.map((s) => {
    const at: Lnglat = [s.lng, s.lat];
    bounds.push(at);
    labels.push({ kind: "store", at, text: s.name, isNew: Boolean(s.is_new) });
    return { type: "Feature" as const, geometry: { type: "Point" as const, coordinates: at }, properties: { id: s.store_id, isNew: Boolean(s.is_new) } };
  });

  // Several chains can share a merged cell: one label per centre, listing each chain.
  const cellText = new Map<string, { at: Lnglat; parts: string[] }>();
  const cells = view.network.others.flatMap((o) =>
    o.cells.map((c) => {
      const key = `${c.lat},${c.lng}`;
      const entry = cellText.get(key) ?? { at: [c.lng, c.lat] as Lnglat, parts: [] };
      entry.parts.push(`${o.label_vi}: ${c.stores} cửa hàng`);
      cellText.set(key, entry);
      return {
        type: "Feature" as const,
        geometry: { type: "Polygon" as const, coordinates: [disc(c.lat, c.lng, cellRadiusM(c.lat, c.lng))] },
        properties: { label: o.label_vi, stores: c.stores },
      };
    }),
  );
  for (const { at, parts } of cellText.values()) labels.push({ kind: "cell", at, text: parts.join(", ") });

  const flows = view.flows_today.flatMap((f) => {
    const a = byId.get(f.from);
    const b = byId.get(f.to);
    if (!a || !b) return [];
    const line = arc([a.lng, a.lat], [b.lng, b.lat]);
    labels.push({ kind: "flow", at: line[Math.floor(line.length / 2)], text: `${f.units}` });
    return [{ type: "Feature" as const, geometry: { type: "LineString" as const, coordinates: line }, properties: { units: f.units } }];
  });

  return {
    stores: { type: "FeatureCollection", features: stores },
    cells: { type: "FeatureCollection", features: cells },
    flows: { type: "FeatureCollection", features: flows },
    labels,
    bounds,
  };
}
