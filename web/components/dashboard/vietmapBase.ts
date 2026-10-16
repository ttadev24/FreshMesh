// Shared VietMap GL setup for every map of the app (route map, network map). Client-only modules import this.
import type vietmapgl from "@vietmap/vietmap-gl-js/dist/vietmap-gl";

export const VIETMAP_KEY = process.env.NEXT_PUBLIC_VIETMAP_API_KEY ?? "";

// lm = "SEA Map Light": the muted basemap the light-only UI is designed around (tm = street, dm = dark).
export const STYLE_URL = `https://maps.vietmap.vn/maps/styles/lm/style.json?apikey=${encodeURIComponent(VIETMAP_KEY)}`;

export const MAP_LOCALE = {
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

/** Quiet basemap: hide the POI icons (clinics, banks, cafés...) so the app's own layers read first. */
export function quietBasemap(map: vietmapgl.Map) {
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.type === "symbol" && (layer as { "source-layer"?: string })["source-layer"] === "poi") {
      map.setLayoutProperty(layer.id, "visibility", "none");
    }
  }
}

/** Logs real map errors only: an aborted style request on unmount is expected, not a failure. */
export function logMapErrors(map: vietmapgl.Map, tag: string) {
  map.on("error", (e) => {
    if (e.error?.name !== "AbortError") console.error(`[${tag}]`, e.error);
  });
}

/**
 * Disposes a map without the abort race: remove() during an in-flight style load fires an "error" event with
 * no listener left, which vietmapgl prints to console.error. Waits for the style (bounded) before removing.
 */
export function disposeMap(map: vietmapgl.Map) {
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
}
