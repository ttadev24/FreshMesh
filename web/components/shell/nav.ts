import type { TabId } from "@/components/dashboard/RightPane";
import type { ToolSlot } from "@/components/workspace/useDirectTools";

// Sidebar destinations. The overview, the "Nhập hàng" decision studio, the network and the two trust pages (verify,
// evidence) are pages of their own; everything else opens the two-pane workspace (chat + dashboard) on the matching
// right-pane tab, and the operations items bring their tool into view.
export type NavId =
  | "overview"
  | "import"
  | "stock"
  | "delivery"
  | "assistant"
  | "network"
  | "history"
  | "verify"
  | "evidence"
  | "sources";

export interface NavItem {
  id: NavId;
  label: string;
  /** Page title shown in the header for workspace destinations. */
  title: string;
  tab?: TabId;
  slot?: ToolSlot;
}

export const NAV_MAIN: NavItem[] = [
  { id: "overview", label: "Tổng quan", title: "Toàn cảnh vận hành" },
  { id: "import", label: "Nhập hàng", title: "Nhập hàng cho ngày mai" },
  { id: "stock", label: "Tồn kho", title: "Xử lý tồn", tab: "dashboard", slot: "stock" },
  { id: "delivery", label: "Giao hàng", title: "Giao hàng", tab: "dashboard", slot: "route" },
  { id: "assistant", label: "Trợ lý", title: "Trợ lý và bảng tính", tab: "dashboard" },
  { id: "network", label: "Mạng lưới", title: "Mạng lưới học liên kết" },
  { id: "history", label: "Lịch sử", title: "Lịch sử quyết định", tab: "audit" },
];

/** How a judge or a new owner checks FreshMesh: the safety rules run live, and every claim with its result. */
export const NAV_TRUST: NavItem[] = [
  { id: "verify", label: "Kiểm chứng", title: "Kiểm chứng 90 giây" },
  { id: "evidence", label: "Bằng chứng", title: "Bằng chứng" },
];

export const NAV_SOURCES: NavItem = { id: "sources", label: "Nguồn dữ liệu", title: "Nguồn và giả định dữ liệu", tab: "sources" };

export const NAV_BY_ID = Object.fromEntries([...NAV_MAIN, ...NAV_TRUST, NAV_SOURCES].map((n) => [n.id, n])) as Record<
  NavId,
  NavItem
>;

/** Which sidebar item a right-pane tab belongs to (keeps the highlight in sync when tabs are switched inside). */
export function navForTab(tab: TabId, current: NavId): NavId {
  if (tab === "audit") return "history";
  if (tab === "sources") return "sources";
  // "dashboard" and the in-workspace FL tab keep the operations item the user came from.
  return current === "stock" || current === "delivery" || current === "assistant" ? current : "assistant";
}

/** Destinations rendered as full pages (own large title) instead of the chat + dashboard workspace. */
export const PAGE_NAVS: readonly NavId[] = ["overview", "import", "network", "verify", "evidence"];
