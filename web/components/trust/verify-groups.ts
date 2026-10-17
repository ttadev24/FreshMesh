import type { VerifyCase } from "@/lib/trust-types";

// The live safety checks grouped by what they protect. Case ids come from api/verify.py; a case added there later
// lands in "Kiểm chứng khác" until it is placed here, so nothing the API runs is ever hidden.
const GROUPS: { id: string; title: string; cases: string[] }[] = [
  { id: "ai", title: "AI không được bịa", cases: ["fabricated_number", "true_numbers_pass", "execution_claim_flagged"] },
  {
    id: "data",
    title: "Dữ liệu đúng người, đúng chỗ",
    cases: ["sql_delete_blocked", "tenant_isolation", "manager_cross_store", "pii_redacted"],
  },
  {
    id: "human",
    title: "Con người quyết định",
    cases: ["draft_not_executed", "authority_needs_owner", "goal_conflict_asks", "thin_data_asks", "undo_window"],
  },
];

export interface VerifyGroup {
  id: string;
  title: string;
  cases: VerifyCase[];
}

export function groupCases(cases: VerifyCase[]): VerifyGroup[] {
  const byId = new Map(cases.map((c) => [c.id, c]));
  const placed = new Set(GROUPS.flatMap((g) => g.cases));
  const groups = GROUPS.map((g) => ({
    id: g.id,
    title: g.title,
    cases: g.cases.map((id) => byId.get(id)).filter((c): c is VerifyCase => Boolean(c)),
  }));
  const other = cases.filter((c) => !placed.has(c.id));
  if (other.length) groups.push({ id: "other", title: "Kiểm chứng khác", cases: other });
  return groups.filter((g) => g.cases.length > 0);
}
