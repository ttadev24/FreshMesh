// Vietnamese number formatting. Matches the forms the number guardrail accepts (1.234.567 đ, 12,5%),
// so what the user reads in the dashboard is the same string they read in the agent's answer.

const int = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });
const dec1 = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
const dec2 = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });

export const NO_DATA = "không có dữ liệu";

export function fmtVnd(v: number | null | undefined): string {
  return v == null ? NO_DATA : `${int.format(Math.round(v))} đ`;
}

/** `v` is already a percentage (0–100), as every *_pct field of the backend. */
export function fmtPct(v: number | null | undefined): string {
  return v == null ? NO_DATA : `${dec1.format(v)}%`;
}

export function fmtNum(v: number | null | undefined, digits: 0 | 1 | 2 = 1): string {
  if (v == null) return NO_DATA;
  return (digits === 0 ? int : digits === 1 ? dec1 : dec2).format(v);
}

export function fmtKm(v: number | null | undefined): string {
  return v == null ? NO_DATA : `${dec1.format(v)} km`;
}

export function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit", year: "numeric" });
}

export function fmtDate(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("vi-VN", { weekday: "short", day: "2-digit", month: "2-digit" });
}

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

/** Exact wording for the transfer's avoided-stockout value: it must never read as money. */
export const NON_CASH_LABEL = "giá trị tránh thiếu hàng, không phải tiền mặt";

export const ROLE_VI: Record<string, string> = { owner: "Chủ chuỗi", store_manager: "Quản lý cửa hàng" };

export const AREA_VI: Record<string, string> = { residential: "dân cư", market: "gần chợ", office: "văn phòng" };

export const DRAFT_STATUS_VI: Record<string, string> = {
  draft: "Bản nháp, chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Đã bỏ",
  dispatched: "Đã gửi",
};

export const DRAFT_KIND_VI: Record<string, string> = {
  purchase_order: "Đơn đặt hàng",
  create_purchase_order: "Đơn đặt hàng",
  markdown: "Giảm giá theo khung giờ",
  apply_markdown: "Giảm giá theo khung giờ",
  transfer: "Điều chuyển hàng",
  transfer_stock: "Điều chuyển hàng",
  dispatch_routes: "Gửi lộ trình cho shipper",
  route_dispatch: "Gửi lộ trình cho shipper",
  routes: "Gửi lộ trình cho shipper",
};
