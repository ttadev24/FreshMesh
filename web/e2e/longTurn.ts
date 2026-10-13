import type { APIRequestContext, Locator, Page, Route } from "@playwright/test";
import { DEMO_PASSWORD } from "./fixtures";

// A long agent turn served through `page.route` on /api/agent/chat, in the SSE shape of
// docs/api-contract-notes.md (plan, tool_call / tool_result pairs, answer, final). The tool outputs, the
// drafts and the provenance ids are real: they are fetched from (and created on) the running API first, so
// the dashboard and the proposal cards render real numbers. Only the agent's prose is written here.

export const LONG_STORE = "A-CH1";

type Json = Record<string, unknown>;

export interface LongTurnData {
  forecast: Json;
  inventory: Json;
  draftIds: string[];
  /** Every registered dataset id (a long "Nguồn dữ liệu" list). */
  sources: string[];
  sourceLabels: string[];
}

async function ok(res: Awaited<ReturnType<APIRequestContext["get"]>>, what: string): Promise<Json> {
  if (!res.ok()) throw new Error(`${what}: HTTP ${res.status()} ${await res.text()}`);
  return (await res.json()) as Json;
}

/** Real tool outputs, drafts and dataset ids for the long turn (owner_a, store A-CH1). */
export async function loadLongTurnData(request: APIRequestContext, baseURL: string): Promise<LongTurnData> {
  const login = await ok(
    await request.post(`${baseURL}/api/auth/login`, { data: { username: "owner_a", password: DEMO_PASSWORD } }),
    "login",
  );
  const headers = { Authorization: `Bearer ${String(login.token)}` };
  const scope = { store_id: LONG_STORE, categories: ["vegetable", "meat"] };
  const [forecast, inventory, provenance] = await Promise.all([
    ok(await request.get(`${baseURL}/api/forecast?store_id=${LONG_STORE}&categories=vegetable,meat&horizon_days=7`, { headers }), "forecast"),
    ok(await request.post(`${baseURL}/api/inventory/plan`, { headers, data: { ...scope, horizon_days: 1 } }), "inventory"),
    ok(await request.get(`${baseURL}/api/provenance`, { headers }), "provenance"),
  ]);
  // Two real purchase-order drafts (Cân bằng, An toàn): the proposal cards of the turn.
  const drafts = await Promise.all(
    ["balanced", "safe"].map(async (plan_name) =>
      ok(
        await request.post(`${baseURL}/api/drafts`, {
          headers,
          data: { kind: "create_purchase_order", payload: { ...scope, horizon_days: 1, plan_name } },
        }),
        `${plan_name} purchase draft`,
      ),
    ),
  );
  const datasets = (provenance.datasets as Json[]) ?? [];
  return {
    forecast,
    inventory,
    draftIds: drafts.map((d) => String((d.draft as Json).draft_id)),
    sources: datasets.map((d) => String(d.id)),
    sourceLabels: datasets.map((d) => String(d.label_vi)),
  };
}

/** SSE body: `event: <type>` + `data: <JSON>` blocks, as the gateway streams them. */
const toSse = (events: readonly (readonly [string, unknown])[]) =>
  events.map(([type, d]) => `event: ${type}\ndata: ${JSON.stringify(d)}\n\n`).join("");

/** Answer text: the 5 sections in template order, then the server-written sources line. */
const answerText = (sections: Record<string, string>, sourcesLine: string) =>
  `${Object.entries(sections).map(([k, v]) => `**${k}:** ${v}`).join("\n\n")}\n\n**Nguồn dữ liệu:** ${sourcesLine}`;

const para = (n: number, line: string) => Array.from({ length: n }, (_, i) => `- ${line} (${i + 1}).`).join("\n");

/** The SSE body of one long turn: many tool steps, long sections, a long sources line and two drafts. */
export function longTurnSse(data: LongTurnData, question: string): string {
  const prov = { sources: data.sources, source_labels_vi: data.sourceLabels };
  const steps: { name: string; kind: string; data: Json }[] = [
    { name: "forecast_demand", kind: "read", data: data.forecast },
    { name: "plan_inventory", kind: "read", data: data.inventory },
    ...Array.from({ length: 6 }, (_, i) => ({
      name: "query_data",
      kind: "read",
      data: { rows: [], columns: [], tables: ["sales"], sql: `select ${i}`, ...prov },
    })),
    { name: "create_purchase_order", kind: "draft", data: { draft_id: data.draftIds[0] } },
    { name: "create_purchase_order", kind: "draft", data: { draft_id: data.draftIds[1] } },
  ];
  const sections = {
    "Đề xuất": `Nhập theo phương án **Cân bằng** cho ngày mai; phương án **An toàn** để bạn so sánh.\n${para(4, "Ưu tiên rau ăn lá và thịt heo theo dự báo")}`,
    "Vì sao": para(8, "Dự báo nhu cầu cho thấy nhu cầu ổn định, phương án cân bằng giữ tỉ lệ hàng bỏ thấp mà vẫn đủ hàng"),
    "Độ tin cậy": `Trung bình: dự báo rau có khoảng P10 đến P90 rộng.\n${para(5, "Độ phủ dự báo 7 ngày gần đây nằm trong ngưỡng")}`,
    "Giả định": para(6, "Nhà cung cấp giao đúng giờ và giá nhập không đổi"),
    "Việc cần bạn duyệt": "Duyệt một trong hai bản nháp đơn đặt hàng bên dưới (Cân bằng hoặc An toàn).",
  };
  const text = answerText(sections, data.sourceLabels.join("; "));
  const answer = {
    text,
    sections,
    template_ok: true,
    unverified: [],
    drafts: data.draftIds,
    citations: [],
    rewritten: false,
    stop_reason: "end_turn",
    error_vi: null,
    ...prov,
  };
  const events: [string, unknown][] = [
    ["plan", { text: "Kế hoạch: dự báo, lập phương án nhập, truy vấn số liệu bán và tạo hai bản nháp đơn đặt hàng.", steps: steps.map((s) => ({ tool: s.name, description_vi: "" })) }],
  ];
  steps.forEach((s, i) => {
    const id = `call_${i}`;
    events.push(["tool_call", { id, name: s.name, kind: s.kind, args: {} }]);
    events.push(["tool_result", { id, name: s.name, kind: s.kind, data: s.data, citations: [] }]);
  });
  events.push(["answer", answer]);
  events.push([
    "final",
    {
      turn_id: "t-long",
      user_message: question,
      plan_vi: (events[0][1] as Json).text,
      plan_steps: [],
      tool_calls: [],
      answer_text: text,
      rewrite_problems: [],
      events: [],
      model: "test-served",
      ...answer,
    },
  ]);
  return toSse(events);
}

/**
 * A short follow-up answer (no tools) in the same SSE shape. With `unverified`, the Giả định section quotes
 * that number and the guardrail flags it (`unverified_flag` event + `answer.unverified`).
 */
export function shortTurnSse(question: string, unverified?: string): string {
  const sections = {
    "Đề xuất": "Giữ nguyên kế hoạch đã đề xuất.",
    "Vì sao": "Không có thay đổi mới so với lượt trước.",
    "Độ tin cậy": "Trung bình.",
    "Giả định": unverified ? `Tỉ lệ hàng bỏ giữ ở mức ${unverified} như tuần trước.` : "Như lượt trước.",
    "Việc cần bạn duyệt": "Không có việc mới.",
  };
  const text = answerText(sections, "Không dùng dữ liệu (không có kết quả công cụ)");
  const flagged = unverified ? [unverified] : [];
  const answer = { text, sections, template_ok: true, unverified: flagged, drafts: [], citations: [], stop_reason: "end_turn", sources: [], source_labels_vi: [] };
  return toSse([
    ["plan", { text: "Trả lời trực tiếp, không cần công cụ.", steps: [] }],
    ...flagged.map((raw) => ["unverified_flag", { raw }] as const),
    ["answer", answer],
    ["final", { turn_id: "t-short", user_message: question, plan_vi: "", tool_calls: [], answer_text: text, events: [], ...answer }],
  ]);
}

/** Types a message in the chat composer and sends it with Enter. */
export async function sendChat(page: Page, message: string) {
  const input = page.getByTestId("chat-input");
  await input.fill(message);
  await input.press("Enter");
}

/** The region a disclosure button controls (`aria-controls`). */
export async function regionOf(page: Page, toggle: Locator) {
  return page.locator(`[id="${await toggle.getAttribute("aria-controls")}"]`);
}

/**
 * Serves the chat: the first request gets the long turn (or `reply` when given), later ones a short answer.
 * Returns the list of messages the page actually sent (one entry per observed request).
 */
export async function serveChat(page: Page, data: LongTurnData | null, reply?: (message: string) => string): Promise<string[]> {
  const sent: string[] = [];
  await page.route(/\/api\/agent\/chat$/, async (route: Route) => {
    const body = (route.request().postDataJSON() ?? {}) as { message?: string };
    const message = String(body.message ?? "");
    sent.push(message);
    await route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache" },
      body: reply ? reply(message) : sent.length === 1 && data ? longTurnSse(data, message) : shortTurnSse(message),
    });
  });
  return sent;
}
