// Data provenance: what every number on screen is derived from. The gateway tags payloads with
// `sources` (dataset ids or objects) and `source_labels_vi` (Vietnamese labels, parallel list or map), and
// lists the datasets themselves at GET /api/provenance. Everything is normalised here, tolerant to the
// shapes above; nothing is invented — a payload without provenance fields yields an empty list.

import { createContext, useContext } from "react";
import type { Provenance, ProvenanceDataset, SourceKind, SourceRef } from "./types";

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

function toDataset(v: unknown, fallbackId: string): ProvenanceDataset | null {
  if (!isObj(v)) return null;
  const id = firstStr(v, "id", "dataset_id", "source_id", "key") || fallbackId;
  const name = firstStr(v, "name_vi", "name", "title_vi", "title", "label_vi", "label") || id;
  if (!id && !name) return null;
  const kindRaw = firstStr(v, "kind", "type", "category");
  const urlRaw = firstStr(v, "url", "source_url", "link", "homepage");
  const promptIds = [v.prompt_ids, v.prompts, v.prompt_id].flatMap((p) => (Array.isArray(p) ? p : p ? [p] : []));
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
