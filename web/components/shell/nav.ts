import type { TabId } from "@/components/dashboard/RightPane";
import type { ToolSlot } from "@/components/workspace/useDirectTools";

// Sidebar destinations. Everything except the overview opens the two-pane workspace (chat + dashboard) on
// the matching right-pane tab, and the three operations items bring their tool into view.
export type NavId = "overview" | "import" | "stock" | "delivery" | "network" | "history" | "sources";

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
  { id: "import", label: "Nhập hàng", title: "Nhập hàng", tab: "dashboard", slot: "inventory" },
  { id: "stock", label: "Tồn kho", title: "Xử lý tồn", tab: "dashboard", slot: "stock" },
  { id: "delivery", label: "Giao hàng", title: "Giao hàng", tab: "dashboard", slot: "route" },
  { id: "network", label: "Mạng lưới", title: "Mạng lưới học liên kết", tab: "fl" },
  { id: "history", label: "Lịch sử", title: "Lịch sử quyết định", tab: "audit" },
];

export const NAV_SOURCES: NavItem = { id: "sources", label: "Nguồn dữ liệu", title: "Nguồn và giả định dữ liệu", tab: "sources" };

export const NAV_BY_ID = Object.fromEntries([...NAV_MAIN, NAV_SOURCES].map((n) => [n.id, n])) as Record<NavId, NavItem>;

/** Which sidebar item a right-pane tab belongs to (keeps the highlight in sync when tabs are switched inside). */
export function navForTab(tab: TabId, current: NavId): NavId {
  if (tab === "audit") return "history";
  if (tab === "fl") return "network";
  if (tab === "sources") return "sources";
  return current === "import" || current === "stock" || current === "delivery" ? current : "import";
}
