import type { VerifyCase } from "@/lib/trust-types";

// The live safety checks grouped by what they protect. Case ids come from api/verify.py; a case added there later
// lands in "Kiểm chứng khác" until it is placed here, so nothing the API runs is ever hidden.
const GROUPS: { id: string; title: string; desc: string; cases: string[] }[] = [
  {
    id: "ai",
    title: "AI không bịa, không tự quyết",
    desc: "Số không có trong kết quả tính toán bị đánh dấu. AI chỉ được tạo bản nháp, không tự thực thi.",
    cases: ["fabricated_number", "true_numbers_pass", "execution_claim_flagged", "draft_not_executed"],
  },
  {
    id: "data",
    title: "Dữ liệu đúng người, đúng chỗ",
    desc: "Chỉ đọc, đúng chuỗi, đúng cửa hàng. Tên và số điện thoại khách được che trước khi gửi AI.",
    cases: ["sql_delete_blocked", "tenant_isolation", "manager_cross_store", "pii_redacted"],
  },
  {
    id: "human",
    title: "Con người quyết định",
    desc: "Vượt hạn mức thì chuyển chủ chuỗi. Mục tiêu mâu thuẫn hay thiếu dữ liệu thì hỏi lại. Hoàn tác có giới hạn.",
    cases: ["authority_needs_owner", "goal_conflict_asks", "thin_data_asks", "undo_window"],
  },
];

export interface VerifyGroup {
  id: string;
  title: string;
  desc: string;
  /** Checks of this group in the last run (empty before the first run). */
  cases: VerifyCase[];
  /** How many checks the group holds; before a run this is the known list. */
  size: number;
}

/** The groups as they look before anything ran: titles, what they protect, one empty slot per known check. */
export const GROUP_SHELLS: VerifyGroup[] = GROUPS.map((g) => ({ id: g.id, title: g.title, desc: g.desc, cases: [], size: g.cases.length }));

export const KNOWN_CHECKS = GROUPS.reduce((n, g) => n + g.cases.length, 0);

export function groupCases(cases: VerifyCase[]): VerifyGroup[] {
  const byId = new Map(cases.map((c) => [c.id, c]));
  const placed = new Set(GROUPS.flatMap((g) => g.cases));
  const groups: VerifyGroup[] = GROUPS.map((g) => {
    const found = g.cases.map((id) => byId.get(id)).filter((c): c is VerifyCase => Boolean(c));
    return { id: g.id, title: g.title, desc: g.desc, cases: found, size: found.length };
  });
  const other = cases.filter((c) => !placed.has(c.id));
  if (other.length) {
    groups.push({ id: "other", title: "Kiểm chứng khác", desc: "Các quy tắc mới thêm vào bộ kiểm chứng.", cases: other, size: other.length });
  }
  return groups.filter((g) => g.size > 0);
}
