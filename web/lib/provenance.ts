// Data provenance: what every number on screen is derived from. The gateway tags payloads with
// `sources` (dataset ids or objects) and `source_labels_vi` (Vietnamese labels, parallel list or map), and
// lists the datasets themselves at GET /api/provenance. Everything is normalised here, tolerant to the
// shapes above; nothing is invented — a payload without provenance fields yields an empty list.

import { createContext, useContext } from "react";
import type { PromptEvidence, PromptStatus, PromptSummary, Provenance, ProvenanceDataset, SourceKind, SourceRef } from "./types";

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v.trim() : typeof v === "number" ? String(v) : "");
const firstStr = (o: Obj, ...keys: string[]) => {
  for (const k of keys) {
    const v = str(o[k]);
    if (v) return v;
  }
  return "";
};

/** Vietnamese chip text per kind (user-facing wording fixed by the product brief). */
export const KIND_VI: Record<SourceKind, string> = {
  public: "Công khai",
  ai_generated: "AI sinh",
  simulated: "Chương trình mô phỏng",
  computed: "Tính toán",
  other: "Khác",
};

export const KIND_HELP_VI: Record<SourceKind, string> = {
  public: "Dữ liệu công khai, có đường dẫn và giấy phép gốc.",
  ai_generated: "Dữ liệu do mô hình AI sinh ra theo prompt đã ghi lại; cần đối chiếu trước khi dùng thật.",
  simulated: "Dữ liệu do chương trình mô phỏng tạo ra theo tham số công bố.",
  computed: "Kết quả tính toán từ các nguồn khác (dự báo, tối ưu, mô phỏng Monte Carlo).",
  other: "Nguồn chưa phân loại.",
};

/** Maps a backend kind string (English id or Vietnamese label) to a chip kind. */
/** Exact kinds of provenance/registry.py (KINDS); the patterns below only cover labels outside that vocabulary. */
const REGISTRY_KINDS: Record<string, SourceKind> = {
  public: "public",
  ai_generated: "ai_generated",
  synthetic_code: "simulated",
  derived: "computed",
};

export function toKind(raw: unknown): SourceKind | null {
  const k = str(raw).toLowerCase();
  if (!k) return null;
  if (REGISTRY_KINDS[k]) return REGISTRY_KINDS[k];
  if (/public|open|công khai|cong_khai/.test(k)) return "public";
  if (/\bai\b|ai_|llm|generat|sinh/.test(k)) return "ai_generated";
  if (/simul|synthetic|mô phỏng|mo_phong|giả lập/.test(k)) return "simulated";
  if (/comput|derived|calc|model|tính|forecast|optim/.test(k)) return "computed";
  return "other";
}

/** Only absolute http(s) URLs become links; anything else (javascript:, data:, relative) stays text. */
export function safeUrl(raw: unknown): string | null {
  const v = str(raw);
  if (!v) return null;
  try {
    const u = new URL(v);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

const PROMPT_STATUS: readonly PromptStatus[] = ["accepted", "invalid", "api_error"];

export const PROMPT_STATUS_VI: Record<PromptStatus, string> = {
  accepted: "Được chấp nhận",
  invalid: "Bị loại (không hợp lệ)",
  api_error: "Lỗi gọi API",
  unknown: "Không rõ trạng thái",
};

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const toStatus = (v: unknown): PromptStatus => {
  const st = str(v) as PromptStatus;
  return PROMPT_STATUS.includes(st) ? st : "unknown";
};

function toPromptSummary(v: unknown): PromptSummary | null {
  if (!isObj(v)) {
    const id = str(v);
    return id ? { id, task: null, ts: null, model: null, status: "unknown", attempt: null } : null;
  }
  const id = firstStr(v, "id", "prompt_id");
  if (!id) return null;
  return {
    id,
    task: firstStr(v, "task") || null,
    ts: firstStr(v, "ts", "created_at") || null,
    model: firstStr(v, "model") || null,
    status: toStatus(v.status),
    attempt: num(v.attempt),
  };
}

/** Summaries from `prompts[]` first (they carry task/model/time), then any `prompt_ids` without one. */
function toPromptSummaries(v: Obj): PromptSummary[] {
  const out: PromptSummary[] = [];
  const lists = [v.prompts, v.prompt_ids, v.prompt_id].flatMap((p) => (Array.isArray(p) ? p : p ? [p] : []));
  for (const item of lists) {
    const sum = toPromptSummary(item);
    if (sum && !out.some((p) => p.id === sum.id)) out.push(sum);
  }
  return out;
}

export function normalizePromptEvidence(raw: unknown): PromptEvidence {
  const v = isObj(raw) ? raw : {};
  const base = toPromptSummary({ ...v, id: firstStr(v, "prompt_id", "id") }) ?? {
    id: "",
    task: null,
    ts: null,
    model: null,
    status: "unknown" as const,
    attempt: null,
  };
  const params = isObj(v.params) ? v.params : isObj(v.parameters) ? v.parameters : {};
  // The JSON schema is large: shown in its own panel, replaced by a pointer in the parameters view.
  const outputConfig = isObj(params.output_config) ? params.output_config : null;
  const format = outputConfig && isObj(outputConfig.format) ? outputConfig.format : null;
  const schema = format && "schema" in format ? format.schema : null;
  const shownParams =
    schema !== null && outputConfig && format
      ? { ...params, output_config: { ...outputConfig, format: { ...format, schema: "(xem mục JSON schema)" } } }
      : params;
  const usage: Record<string, number> = {};
  if (isObj(v.usage)) for (const [k, n] of Object.entries(v.usage)) if (num(n) !== null) usage[k] = n as number;
  const bool = (b: unknown) => (typeof b === "boolean" ? b : null);
  const strs = (a: unknown) => (Array.isArray(a) ? a.map(str).filter(Boolean) : []);
  return {
    ...base,
    purpose: firstStr(v, "purpose") || null,
    error: firstStr(v, "error") || null,
    stop_reason: firstStr(v, "stop_reason") || null,
    params: shownParams,
    schema,
    system_text: typeof v.system_text === "string" ? v.system_text : null,
    prompt_text: typeof v.prompt_text === "string" ? v.prompt_text : "",
    prompt_sha256: firstStr(v, "prompt_sha256") || null,
    prompt_sha256_ok: bool(v.prompt_sha256_ok),
    response_text: typeof v.response_text === "string" ? v.response_text : null,
    response_sha256: firstStr(v, "response_sha256") || null,
    sha256_ok: bool(v.sha256_ok),
    dataset_ids: strs(v.dataset_ids),
    usage,
    notes: strs(v.notes_vi),
    attempts: (Array.isArray(v.attempts) ? v.attempts : []).map(toPromptSummary).filter((p): p is PromptSummary => p !== null),
  };
}

function toDataset(v: unknown, fallbackId: string): ProvenanceDataset | null {
  if (!isObj(v)) return null;
  const id = firstStr(v, "id", "dataset_id", "source_id", "key") || fallbackId;
  const name = firstStr(v, "name_vi", "name", "title_vi", "title", "label_vi", "label") || id;
  if (!id && !name) return null;
  const kindRaw = firstStr(v, "kind", "type", "category");
  const urlRaw = firstStr(v, "url", "source_url", "link", "homepage");
  const promptIds = [v.prompt_ids, v.prompts, v.prompt_id].flatMap((p) => (Array.isArray(p) ? p : p ? [p] : []));
  const prompts = toPromptSummaries(v);
  return {
    id,
    name,
    kind: toKind(kindRaw) ?? "other",
    kind_raw: firstStr(v, "kind_vi", "kind_label_vi") || kindRaw,
    url: safeUrl(urlRaw),
    url_text: urlRaw || null,
    licence: firstStr(v, "licence", "license", "licence_vi", "license_vi") || null,
    retrieved_at: firstStr(v, "retrieved_at", "fetched_at", "generated_at", "created_at") || null,
    description: firstStr(v, "description_vi", "description", "desc_vi", "note_vi") || null,
    prompt_ids: [...new Set(promptIds.map((p) => (isObj(p) ? firstStr(p, "id", "prompt_id") : str(p))).filter(Boolean))],
    prompts,
  };
}

export function normalizeProvenance(raw: unknown): Provenance {
  const o = isObj(raw) ? raw : { datasets: raw };
  const list = o.datasets ?? o.sources ?? o.items;
  const entries: [string, unknown][] = Array.isArray(list)
    ? list.map((v, i) => [String(i), v])
    : isObj(list)
      ? Object.entries(list)
      : [];
  const datasets = entries
    .map(([key, v]) => toDataset(v, Array.isArray(list) ? "" : key))
    .filter((d): d is ProvenanceDataset => d !== null);
  const notes = o.notes_vi ?? o.notes;
  return { datasets, notes: (Array.isArray(notes) ? notes : notes ? [notes] : []).map(str).filter(Boolean) };
}

/** Element id of a dataset card in the "Nguồn & giả định dữ liệu" tab (ids are free text: keep it a safe token). */
export const datasetAnchor = (id: string) => `dataset-${id.replace(/[^A-Za-z0-9_-]/g, "_")}`;

/** Opens the sources tab at one dataset (kind chips next to numbers link there). Null outside the workspace. */
export const SourcesNavContext = createContext<((datasetId: string) => void) | null>(null);
export const useSourcesNav = () => useContext(SourcesNavContext);

/** Dataset lookup shared by the header badge, the sources tab and every Sourced tooltip. */
export type ProvenanceIndex = ReadonlyMap<string, ProvenanceDataset>;

export const ProvenanceContext = createContext<ProvenanceIndex>(new Map());
export const useProvenanceIndex = () => useContext(ProvenanceContext);

export function indexProvenance(p: Provenance | null): ProvenanceIndex {
  return new Map((p?.datasets ?? []).map((d) => [d.id, d]));
}

/**
 * Provenance refs of one payload. Accepts `sources: ["id", ...]` with `source_labels_vi` as a parallel list
 * or an {id: label} map, `sources: [{id, label_vi, kind}]`, or a single string. A legacy `source: "SIMULATED"`
 * scalar is not provenance and is ignored.
 */
export function sourcesOf(payload: unknown): SourceRef[] {
  if (!isObj(payload)) return [];
  const raw = payload.sources ?? (isObj(payload.provenance) ? payload.provenance.sources : undefined);
  const labels = payload.source_labels_vi ?? (isObj(payload.provenance) ? payload.provenance.source_labels_vi : undefined);
  const list = Array.isArray(raw) ? raw : typeof raw === "string" && raw ? [raw] : [];
  const labelAt = (id: string, i: number): string =>
    Array.isArray(labels) ? str(labels[i]) : isObj(labels) ? str(labels[id]) : "";

  const out: SourceRef[] = [];
  list.forEach((item, i) => {
    let ref: SourceRef | null = null;
    if (typeof item === "string" && item.trim()) {
      const id = item.trim();
      ref = { id, label_vi: labelAt(id, i), kind: null };
    } else if (isObj(item)) {
      const id = firstStr(item, "id", "dataset_id", "source_id", "key");
      const label = firstStr(item, "label_vi", "name_vi", "name", "label", "title");
      if (id || label) ref = { id: id || label, label_vi: label || labelAt(id, i), kind: toKind(item.kind ?? item.type) };
    }
    if (ref && !out.some((r) => r.id === ref!.id)) out.push(ref);
  });
  // Labels without ids (a bare `source_labels_vi` list) are still provenance worth showing.
  if (!out.length && Array.isArray(labels)) {
    labels.map(str).filter(Boolean).forEach((label) => out.push({ id: label, label_vi: label, kind: null }));
  }
  return out;
}

/** Fills label and kind of refs from the dataset index (the payload often carries ids only). */
export function resolveSources(refs: readonly SourceRef[], index: ProvenanceIndex): SourceRef[] {
  return refs.map((r) => {
    const d = index.get(r.id);
    return { id: r.id, label_vi: r.label_vi || d?.name || r.id, kind: r.kind ?? d?.kind ?? null };
  });
}

export function mergeSources(...lists: readonly (readonly SourceRef[])[]): SourceRef[] {
  const out: SourceRef[] = [];
  for (const list of lists) for (const r of list) if (!out.some((x) => x.id === r.id)) out.push(r);
  return out;
}
