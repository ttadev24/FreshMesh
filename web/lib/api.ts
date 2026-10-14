"use client";

import { clearSession, getSession } from "./session";
import {
  normalizeAssumptions,
  normalizeAudit,
  normalizeDraft,
  normalizeDrafts,
  normalizeFl,
  type TurnEvent,
} from "./normalize";
import { normalizePromptEvidence, normalizeProvenance } from "./provenance";
import type {
  Assumptions,
  AuditEntry,
  Draft,
  FlNetwork,
  Health,
  LoginResponse,
  PromptEvidence,
  Provenance,
  Sku,
  Store,
  User,
} from "./types";

const API_DOWN_MESSAGE =
  "Không kết nối được máy chủ FreshMesh (API cổng 8100). Kiểm tra dịch vụ backend rồi thử lại.";

/** Error carrying the gateway's Vietnamese message (`{"error": {"code", "message_vi"}}`). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly messageVi: string;

  constructor(status: number, code: string, messageVi: string) {
    super(messageVi);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.messageVi = messageVi;
  }

  get isNetwork() {
    return this.code === "network";
  }
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.messageVi;
  if (err instanceof Error && err.name === "AbortError") return "Yêu cầu đã bị hủy.";
  return "Đã xảy ra lỗi không xác định. Vui lòng thử lại.";
}

const STATUS_FALLBACK_VI: Record<number, string> = {
  400: "Yêu cầu không hợp lệ.",
  401: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
  403: "Bạn không có quyền thực hiện thao tác này.",
  404: "Không tìm thấy dữ liệu yêu cầu.",
  409: "Trạng thái đã thay đổi, vui lòng tải lại.",
  422: "Dữ liệu gửi lên không hợp lệ.",
};

/** Gateway error codes with a known Vietnamese explanation, used when the body carries no message_vi. */
const CODE_FALLBACK_VI: Record<string, string> = {
  model_not_ready:
    "Mô hình dự báo của chuỗi chưa sẵn sàng (chưa huấn luyện). Người vận hành cần chạy scripts/bootstrap.sh rồi thử lại.",
  solver_unavailable: "Bộ giải định tuyến PACO chưa sẵn sàng, chưa lập được lộ trình. Vui lòng thử lại sau.",
  llm_unavailable: "Chưa cấu hình khóa LLM: đặt ANTHROPIC_API_KEY cho API rồi khởi động lại.",
};

/** Exact setup message shown whenever the gateway has no LLM key (health.llm false or 503 llm_unavailable). */
export const LLM_SETUP_VI = CODE_FALLBACK_VI.llm_unavailable;

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  signal?: AbortSignal;
  auth?: boolean;
  accept?: string;
}

async function send(path: string, opts: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: opts.accept ?? "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.auth !== false) {
    const token = getSession()?.token;
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  try {
    return await fetch(path, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      signal: opts.signal,
      cache: "no-store",
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new ApiError(0, "network", API_DOWN_MESSAGE);
  }
}

async function toError(res: Response, auth: boolean): Promise<ApiError> {
  const text = await res.text().catch(() => "");
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  const err = (body as { error?: { code?: string; message_vi?: string } } | null)?.error;
  if (err && typeof err.message_vi === "string" && err.message_vi) {
    return new ApiError(res.status, err.code ?? `http_${res.status}`, err.message_vi);
  }
  if (err?.code && CODE_FALLBACK_VI[err.code]) return new ApiError(res.status, err.code, CODE_FALLBACK_VI[err.code]);
  // A non-JSON 5xx comes from the Next rewrite proxy when the gateway is not running.
  if (res.status >= 500 && body === null) return new ApiError(res.status, "network", API_DOWN_MESSAGE);
  if (res.status === 401 && auth) return new ApiError(401, "unauthorized", STATUS_FALLBACK_VI[401]);
  const detail = (body as { detail?: unknown } | null)?.detail;
  const message =
    typeof detail === "string" ? detail : (STATUS_FALLBACK_VI[res.status] ?? `Máy chủ trả lỗi ${res.status}.`);
  return new ApiError(res.status, `http_${res.status}`, message);
}

/** Throws the gateway error of a failed response; an expired token also ends the session. */
async function throwIfFailed(res: Response, opts: RequestOptions): Promise<void> {
  if (res.ok) return;
  const auth = opts.auth !== false;
  const error = await toError(res, auth);
  if (res.status === 401 && auth) clearSession();
  throw error;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await send(path, opts);
  await throwIfFailed(res, opts);
  if (res.status === 204) return undefined as T;
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError(res.status, "bad_json", "Máy chủ trả dữ liệu không đọc được.");
  }
}

// ---------------------------------------------------------------- auth & context

export function login(username: string, password: string, signal?: AbortSignal) {
  return request<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: { username, password },
    auth: false,
    signal,
  });
}

export const getHealth = (signal?: AbortSignal) => request<Health>("/api/health", { auth: false, signal });
export const getMe = (signal?: AbortSignal) => request<User>("/api/me", { signal });
export const getStores = (signal?: AbortSignal) =>
  request<Store[] | { stores: Store[] }>("/api/stores", { signal }).then((r) => (Array.isArray(r) ? r : r.stores));
export const getSkus = (signal?: AbortSignal) =>
  request<Sku[] | { skus: Sku[] }>("/api/skus", { signal }).then((r) => (Array.isArray(r) ? r : r.skus));

// ---------------------------------------------------------------- drafts (human approval)

export async function listDrafts(signal?: AbortSignal): Promise<Draft[]> {
  return normalizeDrafts(await request<unknown>("/api/drafts", { signal }));
}

export async function approveDraft(id: string): Promise<Draft> {
  return normalizeDraft(await request<unknown>(`/api/drafts/${encodeURIComponent(id)}/approve`, { method: "POST" }));
}

export async function rejectDraft(id: string): Promise<Draft> {
  return normalizeDraft(await request<unknown>(`/api/drafts/${encodeURIComponent(id)}/reject`, { method: "POST" }));
}

export async function editDraft(id: string, payload: Record<string, unknown>): Promise<Draft> {
  return normalizeDraft(
    await request<unknown>(`/api/drafts/${encodeURIComponent(id)}`, { method: "PATCH", body: { payload } }),
  );
}

// ---------------------------------------------------------------- direct tool endpoints (no LLM)
// Real computations on the gateway (forecast model, Monte Carlo plans, PACO routing). The dashboard
// calls them from explicit buttons; they work whether or not an LLM key is configured.

export interface StockArgs {
  store_id: string;
  categories?: string[];
  now_hour?: number;
}

export const getForecast = (
  args: { store_id: string; categories?: string[]; horizon_days?: number },
  signal?: AbortSignal,
) => {
  const q = new URLSearchParams({ store_id: args.store_id, horizon_days: String(args.horizon_days ?? 1) });
  if (args.categories?.length) q.set("categories", args.categories.join(","));
  return request<unknown>(`/api/forecast?${q}`, { signal });
};

export const planInventory = (
  args: { store_id: string; categories?: string[]; horizon_days?: number },
  signal?: AbortSignal,
) => request<unknown>("/api/inventory/plan", { method: "POST", body: args, signal });

export const planTransfer = (args: StockArgs, signal?: AbortSignal) =>
  request<unknown>("/api/transfer/plan", { method: "POST", body: args, signal });

export const planRoutes = (args: { store_id: string; now_minute?: number }, signal?: AbortSignal) =>
  request<unknown>("/api/routing/plan", { method: "POST", body: args, signal });

/** POST /api/drafts: the payload is the draft tool's input; the server recomputes everything from the DB. */
export async function createDraft(kind: string, payload: Record<string, unknown>): Promise<Draft> {
  return normalizeDraft(await request<unknown>("/api/drafts", { method: "POST", body: { kind, payload } }));
}

// ---------------------------------------------------------------- agent

/**
 * POST /api/agent/chat answers with an SSE stream. EventSource cannot POST or send an
 * Authorization header, so the stream is read from fetch and split on blank lines.
 * The mode is always "llm": the agent chooses its tools itself. Without a key the gateway answers
 * 503 llm_unavailable (never a canned reply).
 */
export async function streamChat(
  message: string,
  opts: { storeId?: string | null; signal?: AbortSignal; onEvent: (event: TurnEvent) => void },
): Promise<void> {
  const req: RequestOptions = {
    method: "POST",
    body: { message, mode: "llm", ...(opts.storeId ? { store_id: opts.storeId } : {}) },
    signal: opts.signal,
    accept: "text/event-stream",
  };
  const res = await send("/api/agent/chat", req);
  await throwIfFailed(res, req);
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("text/event-stream") || !res.body) {
    // A gateway may answer with the finished turn as plain JSON.
    opts.onEvent({ type: "final", data: await res.json() });
    return;
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    for (let m = SSE_BOUNDARY.exec(buffer); m; m = SSE_BOUNDARY.exec(buffer)) {
      const block = buffer.slice(0, m.index);
      buffer = buffer.slice(m.index + m[0].length);
      dispatchSse(block, opts.onEvent);
    }
  }
  if (buffer.trim()) dispatchSse(buffer, opts.onEvent);
}

const SSE_BOUNDARY = /\r?\n\r?\n/;

function dispatchSse(block: string, onEvent: (event: TurnEvent) => void) {
  let eventName = "";
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith(":")) continue;
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  if (!data.length) return;
  const joined = data.join("\n");
  let parsed: unknown = joined;
  try {
    parsed = JSON.parse(joined);
  } catch {
    // Plain-text data line (e.g. a text delta).
  }
  const obj = parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
  const type = eventName || (typeof obj?.type === "string" ? (obj.type as string) : "message");
  onEvent({ type, data: parsed });
}

// ---------------------------------------------------------------- tabs

export async function getAudit(signal?: AbortSignal): Promise<AuditEntry[]> {
  return normalizeAudit(await request<unknown>("/api/audit", { signal }));
}

export async function getFlNetwork(signal?: AbortSignal): Promise<FlNetwork> {
  return normalizeFl(await request<unknown>("/api/network/fl", { signal }));
}

export async function getAssumptions(signal?: AbortSignal): Promise<Assumptions> {
  return normalizeAssumptions(await request<unknown>("/api/assumptions", { signal }));
}

export async function getProvenance(signal?: AbortSignal): Promise<Provenance> {
  return normalizeProvenance(await request<unknown>("/api/provenance", { signal }));
}

/** Evidence of one logged AI call (full prompt, raw response, server-checked SHA-256). 404 unknown_prompt if absent. */
export async function getPromptEvidence(promptId: string, signal?: AbortSignal): Promise<PromptEvidence> {
  return normalizePromptEvidence(await request<unknown>(`/api/provenance/prompts/${encodeURIComponent(promptId)}`, { signal }));
}
