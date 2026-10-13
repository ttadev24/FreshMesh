"use client";

// Client-only (next/dynamic ssr:false): Leaflet needs `window`. CircleMarkers are used instead of the
// default image Marker, whose PNG assets do not resolve under the bundler.
import "leaflet/dist/leaflet.css";
import type { LatLngBoundsExpression } from "leaflet";
import { memo, useEffect, useMemo } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import { fmtKm } from "@/lib/format";
import { prefersReducedMotion, useThemeTokens } from "@/lib/theme";
import type { LatLng, RoutePlanView, Store } from "@/lib/types";
import { VEHICLE_COLORS } from "./routeColors";

function FitAndResize({ bounds }: { bounds: LatLngBoundsExpression | null }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [28, 28], maxZoom: 15, animate: !prefersReducedMotion() });
  }, [map, bounds]);
  useEffect(() => {
    // The map may be mounted in a hidden pane (mobile switch / tab): re-measure when it appears.
    const el = map.getContainer();
    const ro = new ResizeObserver(() => map.invalidateSize());
    ro.observe(el);
    return () => ro.disconnect();
  }, [map]);
  return null;
}

const MARKER_TOKENS = {
  store: ["--green-strong", "#134f35"],
  blue: ["--blue", "#1c5cb3"],
  amber: ["--amber-fill", "#e9971f"],
  red: ["--red", "#b0261b"],
  surface: ["--surface", "#fbfcfb"],
} as const;

/** Ho Chi Minh City centre (Bến Thành), used until the plan's own points are fitted. */
const HCMC: LatLng = [10.7725, 106.698];

interface Props {
  plan: RoutePlanView;
  storeName: string;
  stores?: Store[];
}

function RouteMap({ plan, storeName, stores }: Props) {
  const colors = useThemeTokens(MARKER_TOKENS);

  const points = useMemo(() => {
    const pts: LatLng[] = [];
    if (plan.store) pts.push([plan.store.lat, plan.store.lng]);
    plan.routes.forEach((r) => r.path.forEach((p) => pts.push(p)));
    plan.routes.forEach((r) => r.stops.forEach((st) => st.lat != null && st.lng != null && pts.push([st.lat, st.lng])));
    plan.pickup_points.forEach((p) => pts.push([p.lat, p.lng]));
    plan.at_risk.forEach((a) => a.lat != null && a.lng != null && pts.push([a.lat, a.lng]));
    return pts;
  }, [plan]);

  // Leaflet computes the bounding box of a point list itself.
  const bounds: LatLngBoundsExpression | null = points.length ? points : null;

  const center: LatLng = plan.store ? [plan.store.lat, plan.store.lng] : (points[0] ?? HCMC);
  // The other stores of the chain give the route its neighbourhood context; they do not move the fit.
  const otherStores = (stores ?? []).filter(
    (st) => st.store_id !== plan.store_id && Number.isFinite(st.lat) && Number.isFinite(st.lng),
  );

  return (
    <MapContainer
      center={center}
      zoom={13}
      scrollWheelZoom={false}
      style={{ height: "100%", width: "100%" }}
      attributionControl
    >
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='Bản đồ &copy; <a href="https://www.openstreetmap.org/copyright">Những người đóng góp OpenStreetMap</a>'
        maxZoom={19}
      />
      <FitAndResize bounds={bounds} />

      {otherStores.map((st) => (
        <CircleMarker
          key={`store-${st.store_id}`}
          center={[st.lat, st.lng]}
          radius={6}
          pathOptions={{ color: colors.store, weight: 2, fillColor: colors.surface, fillOpacity: 0.9 }}
        >
          <Tooltip direction="top" offset={[0, -6]}>
            {st.name}
          </Tooltip>
        </CircleMarker>
      ))}

      {plan.routes.map((r, i) =>
        r.path.length > 1 ? (
          <Polyline
            key={`path-${r.index}`}
            positions={r.path}
            pathOptions={{ color: VEHICLE_COLORS[i % VEHICLE_COLORS.length], weight: 4, opacity: 0.85 }}
          >
            <Tooltip sticky>
              Xe {r.index}: {r.stops.length} điểm dừng{r.km != null ? `, ${fmtKm(r.km)}` : ""}
            </Tooltip>
          </Polyline>
        ) : null,
      )}

      {plan.pickup_points.map((p) => (
        <CircleMarker
          key={`pp-${p.pickup_point_id}`}
          center={[p.lat, p.lng]}
          radius={8}
          pathOptions={{ color: colors.surface, weight: 2, fillColor: colors.blue, fillOpacity: 1 }}
        >
          <Popup>
            <b>Điểm nhận / tủ</b>
            <br />
            {p.name} (<code>{p.pickup_point_id}</code>)
          </Popup>
        </CircleMarker>
      ))}

      {plan.routes.flatMap((r, i) =>
        r.stops
          .filter((st) => st.lat != null && st.lng != null && st.kind === "home")
          .map((st) => (
            <CircleMarker
              key={`stop-${st.order_id}`}
              center={[st.lat!, st.lng!]}
              radius={5}
              pathOptions={{
                color: st.late ? colors.red : colors.surface,
                weight: st.late ? 3 : 1.5,
                fillColor: VEHICLE_COLORS[i % VEHICLE_COLORS.length],
                fillOpacity: 1,
              }}
            >
              <Popup>
                <b>Đơn {st.order_id}</b>
                <br />
                Xe {r.index}, giao tận nhà
                <br />
                ETA +{st.eta_min} phút{st.late ? " (trễ)" : ""}
              </Popup>
            </CircleMarker>
          )),
      )}

      {plan.at_risk
        .filter((a) => a.lat != null && a.lng != null)
        .map((a) => (
          <CircleMarker
            key={`risk-${a.order_id}`}
            center={[a.lat!, a.lng!]}
            radius={7}
            pathOptions={{ color: colors.surface, weight: 2, fillColor: colors.amber, fillOpacity: 1 }}
          >
            <Popup>
              <b>Đơn có nguy cơ {a.order_id}</b>
              <br />
              {a.reason_vi}
            </Popup>
          </CircleMarker>
        ))}

      {plan.store ? (
        <CircleMarker
          center={[plan.store.lat, plan.store.lng]}
          radius={10}
          pathOptions={{ color: colors.surface, weight: 3, fillColor: colors.store, fillOpacity: 1 }}
        >
          <Tooltip permanent direction="top" offset={[0, -10]}>
            {storeName}
          </Tooltip>
          <Popup>
            <b>Cửa hàng xuất phát</b>
            <br />
            {storeName}
          </Popup>
        </CircleMarker>
      ) : null}
    </MapContainer>
  );
}

export default memo(RouteMap);
