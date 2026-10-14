"use client";

import { useEffect, useId, useMemo, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { errorMessage, getPromptEvidence } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { PROMPT_STATUS_VI } from "@/lib/provenance";
import type { PromptEvidence, PromptStatus, PromptSummary, ProvenanceDataset } from "@/lib/types";
import { Disclosure, ErrorState, Skeleton } from "@/components/ui/primitives";
import p from "./prompt.module.css";

// "Bằng chứng prompt": the logged AI calls behind a dataset (GET /api/provenance summaries), and a viewer for one
// call (GET /api/provenance/prompts/{id}): full prompt, the saved raw response, the server-side SHA-256 check,
// request parameters and the notes recorded in the registry. Nothing here is hard-coded evidence: every text,
// hash and note comes from the API.

const USAGE_VI: Record<string, string> = {
  input_tokens: "Token vào",
  output_tokens: "Token ra",
  cache_creation_input_tokens: "Token ghi cache",
  cache_read_input_tokens: "Token đọc cache",
};

const fmtInt = (n: number) => n.toLocaleString("vi-VN");

function StatusTag({ status }: { status: PromptStatus }) {
  return (
    <span className={p.status} data-status={status} data-testid="prompt-status">
      <span className={p.statusDot} aria-hidden="true" />
      {PROMPT_STATUS_VI[status]}
    </span>
  );
}

/** Disclosure listing the prompts of one dataset; each opens the evidence viewer. */
export function PromptEvidenceList({ dataset, defaultOpen = false }: { dataset: ProvenanceDataset; defaultOpen?: boolean }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const { prompts } = dataset;

  function open(id: string, e: MouseEvent<HTMLButtonElement>) {
    opener.current = e.currentTarget;
    setOpenId(id);
  }

  return (
    <div className={p.evidence} data-testid="prompt-evidence">
      <Disclosure
        defaultOpen={defaultOpen}
        testId="prompt-evidence-toggle"
        buttonClassName={p.evidenceToggle}
        regionClassName={p.evidenceRegion}
        label={
          <>
            <span>Bằng chứng prompt</span>
            <span className={p.count}>({prompts.length})</span>
          </>
        }
      >
        {prompts.length ? (
          <ul className={p.list} aria-label={`Các lượt gọi AI tạo ra ${dataset.name}`}>
            {prompts.map((q) => (
              <li key={q.id}>
                <button
                  type="button"
                  className={p.item}
                  onClick={(e) => open(q.id, e)}
                  aria-haspopup="dialog"
                  data-testid="prompt-evidence-item"
                  data-prompt-id={q.id}
                >
                  <span className={p.itemTask}>{q.task ?? "Lượt gọi AI"}</span>
                  <StatusTag status={q.status} />
                  <span className={p.itemMeta}>
                    {q.model ? <span>{q.model}</span> : null}
                    {q.ts ? <time dateTime={q.ts}>{fmtDateTime(q.ts)}</time> : null}
                    {q.attempt !== null ? <span>lượt {q.attempt}</span> : null}
                  </span>
                  <code className={p.itemId}>{q.id}</code>
                  <span className={p.itemOpen} aria-hidden="true">
                    Xem
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className={p.none}>Bộ dữ liệu này chưa ghi lượt gọi AI nào trong nhật ký prompt.</p>
        )}
      </Disclosure>
      {openId ? (
        <PromptViewer
          promptId={openId}
          onClose={() => {
            setOpenId(null);
            // Focus returns to the row that opened the viewer.
            requestAnimationFrame(() => opener.current?.focus());
          }}
        />
      ) : null}
    </div>
  );
}

type Load = { status: "loading" } | { status: "error"; message: string; notFound: boolean } | { status: "ready"; data: PromptEvidence };

/** Modal viewer (native <dialog>: focus stays inside, Esc closes, focus returns to the opener). */
export function PromptViewer({ promptId, onClose }: { promptId: string; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const titleId = useId();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    if (!dlg.open) dlg.showModal();
    titleRef.current?.focus();
    const closed = () => onCloseRef.current();
    dlg.addEventListener("close", closed);
    return () => {
      dlg.removeEventListener("close", closed);
      if (dlg.open) dlg.close();
    };
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    getPromptEvidence(promptId, ctrl.signal)
      .then((data) => setLoad({ status: "ready", data }))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        const notFound = typeof err === "object" && err !== null && "status" in err && (err as { status: number }).status === 404;
        setLoad({ status: "error", message: errorMessage(err), notFound });
      });
    return () => ctrl.abort();
  }, [promptId, attempt]);

  function retry() {
    setLoad({ status: "loading" });
    setAttempt((n) => n + 1);
  }

  const data = load.status === "ready" ? load.data : null;

  return (
    <dialog
      ref={dialogRef}
      className={p.dialog}
      aria-labelledby={titleId}
      data-testid="prompt-viewer"
      onClick={(e) => {
        // A click on the backdrop (the dialog element itself, outside its content) closes it.
        if (e.target === e.currentTarget) e.currentTarget.close();
      }}
    >
      <div className={p.sheet}>
        <header className={p.head}>
          <div className={p.headText}>
            <p className={p.eyebrow}>Bằng chứng prompt · dữ liệu do AI sinh</p>
            <h2 id={titleId} ref={titleRef} tabIndex={-1} className={p.title}>
              {data?.task ? <>Tác vụ <span className={p.titleTask}>{data.task}</span></> : "Lượt gọi AI"}
            </h2>
            <code className={p.headId} data-testid="prompt-viewer-id">
              {promptId}
            </code>
          </div>
          <button type="button" className={`btn btn-sm ${p.close}`} onClick={() => dialogRef.current?.close()} data-testid="prompt-viewer-close">
            <span aria-hidden="true">✕</span>
            <span>Đóng</span>
          </button>
        </header>

        <div className={p.body} data-testid="prompt-viewer-body">
          {load.status === "loading" ? <Skeleton lines={6} label="Đang tải bằng chứng prompt" /> : null}
          {load.status === "error" ? (
            <ErrorState
              title={load.notFound ? "Không tìm thấy prompt này" : "Không tải được bằng chứng prompt"}
              message={load.message}
              onRetry={load.notFound ? undefined : retry}
              testId="prompt-viewer-error"
            />
          ) : null}
          {data ? <EvidenceBody data={data} /> : null}
        </div>
      </div>
    </dialog>
  );
}

function HashRow({ label, hash, ok, testId }: { label: string; hash: string | null; ok: boolean | null; testId: string }) {
  const verdict =
    ok === true ? (
      <span className={p.verified} data-testid={`${testId}-ok`}>
        <span aria-hidden="true">✓</span> Đã xác minh
      </span>
    ) : ok === false ? (
      <span className={p.mismatch} data-testid={`${testId}-bad`}>
        <span aria-hidden="true">✗</span> Không khớp
      </span>
    ) : (
      <span className={p.unverified}>Không có câu trả lời để kiểm tra</span>
    );
  return (
    <div className={p.hashRow} data-testid={testId}>
      <span className={p.hashLabel}>{label}</span>
      {verdict}
      <code className={p.hash}>{hash ?? "không ghi"}</code>
    </div>
  );
}

function EvidenceBody({ data }: { data: PromptEvidence }) {
  const [pretty, setPretty] = useState(false);
  const parsed = useJson(data.response_text);
  // Known counters first, in reading order (in → out → cache), then anything else the log recorded.
  const order = Object.keys(USAGE_VI);
  const rank = (k: string) => (order.includes(k) ? order.indexOf(k) : order.length);
  const usage = Object.entries(data.usage).sort(([a], [b]) => rank(a) - rank(b));

  return (
    <>
      <dl className={p.meta}>
        <Meta label="Mô hình">
          <code>{data.model ?? "không ghi"}</code>
        </Meta>
        <Meta label="Thời điểm gọi">{data.ts ? <time dateTime={data.ts}>{fmtDateTime(data.ts)}</time> : "không ghi"}</Meta>
        <Meta label="Kết quả">
          <StatusTag status={data.status} />
          {data.attempt !== null ? <span className={p.metaSub}> lượt thử {data.attempt}</span> : null}
        </Meta>
        {data.purpose ? (
          <Meta label="Mục đích">
            <code>{data.purpose}</code>
          </Meta>
        ) : null}
        {data.stop_reason ? (
          <Meta label="Lý do dừng">
            <code>{data.stop_reason}</code>
          </Meta>
        ) : null}
        {usage.length ? (
          <Meta label="Số token">
            <span className={p.usage}>
              {usage.map(([k, n]) => (
                <span key={k}>
                  {USAGE_VI[k] ?? k}: <b>{fmtInt(n)}</b>
                </span>
              ))}
            </span>
          </Meta>
        ) : null}
      </dl>

      {data.error ? (
        <p className={p.errorNote} role="note">
          <b>Lỗi được ghi lại:</b> {data.error}
        </p>
      ) : null}

      <section className={p.integrity} aria-label="Kiểm tra toàn vẹn (SHA-256, máy chủ tính lại)">
        <HashRow label="SHA-256 câu trả lời" hash={data.response_sha256} ok={data.sha256_ok} testId="prompt-response-sha" />
        <HashRow label="SHA-256 prompt" hash={data.prompt_sha256} ok={data.prompt_sha256_ok} testId="prompt-text-sha" />
        <p className={p.integrityHint}>Máy chủ tính lại SHA-256 từ tệp đã lưu mỗi lần mở; “Đã xác minh” nghĩa là nội dung khớp với nhật ký lúc gọi.</p>
      </section>

      {data.notes.length ? (
        <ul className={p.notes} aria-label="Ghi chú tái lập" data-testid="prompt-notes">
          {data.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}

      {data.dataset_ids.length ? (
        <div className={p.usedBy}>
          <span className={p.usedByLabel}>Bộ dữ liệu dùng prompt này</span>
          <span className={p.usedByList}>
            {data.dataset_ids.map((id) => (
              <code key={id}>{id}</code>
            ))}
          </span>
        </div>
      ) : null}

      {data.system_text ? <TextPanel title="Prompt hệ thống" text={data.system_text} testId="prompt-system" compact /> : null}
      <TextPanel title="Prompt" text={data.prompt_text} testId="prompt-text" />
      {data.response_text !== null ? (
        <TextPanel
          title="Câu trả lời gốc"
          sub="nguyên văn tệp đã lưu (đối chiếu SHA-256)"
          text={data.response_text}
          shown={pretty && parsed !== undefined ? JSON.stringify(parsed, null, 2) : undefined}
          testId="prompt-response"
          tools={
            parsed !== undefined ? (
              <button type="button" className="btn btn-sm" aria-pressed={pretty} onClick={() => setPretty((v) => !v)} data-testid="prompt-response-format">
                {pretty ? "Xem nguyên văn" : "Định dạng JSON"}
              </button>
            ) : null
          }
        />
      ) : (
        <p className={p.none}>Không có câu trả lời đã lưu cho lượt gọi này.</p>
      )}
      <TextPanel title="Tham số gọi" text={JSON.stringify(data.params, null, 2)} testId="prompt-params" compact />
      {data.schema !== null ? (
        <details className={p.schema}>
          <summary>JSON schema yêu cầu mô hình tuân theo</summary>
          <TextPanel title="JSON schema" text={JSON.stringify(data.schema, null, 2)} testId="prompt-schema" />
        </details>
      ) : null}

      {data.attempts.length > 1 ? <Attempts current={data.id} attempts={data.attempts} /> : null}
    </>
  );
}

function Attempts({ current, attempts }: { current: string; attempts: PromptSummary[] }) {
  return (
    <section className={p.attempts} aria-label="Các lượt thử của cùng tác vụ">
      <h3>Các lượt thử của cùng tác vụ</h3>
      <ol>
        {attempts.map((a) => (
          <li key={a.id} aria-current={a.id === current ? "true" : undefined}>
            <code>{a.id}</code>
            <StatusTag status={a.status} />
            {a.ts ? <time dateTime={a.ts}>{fmtDateTime(a.ts)}</time> : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** Parsed JSON of a text, or undefined when it is not JSON. */
function useJson(text: string | null): unknown {
  return useMemo(() => {
    if (text === null) return undefined;
    try {
      return JSON.parse(text) as unknown;
    } catch {
      return undefined;
    }
  }, [text]);
}

/** Monospace panel with its own scroll; the copy button always copies `text` (the exact logged bytes). */
function TextPanel({ title, sub, text, shown, testId, tools, compact = false }: {
  title: string;
  sub?: string;
  text: string;
  shown?: string;
  testId: string;
  tools?: ReactNode;
  compact?: boolean;
}) {
  const headingId = useId();
  return (
    <section className={p.panel} aria-labelledby={headingId} data-testid={testId}>
      <header className={p.panelHead}>
        <h3 id={headingId}>
          {title}
          <span className={p.panelSize}> · {fmtInt(text.length)} ký tự</span>
        </h3>
        {sub ? <span className={p.panelSub}>{sub}</span> : null}
        <span className={p.panelTools}>
          {tools}
          <CopyButton text={text} what={title} testId={`${testId}-copy`} />
        </span>
      </header>
      <pre className={`${p.pre} ${compact ? p.preCompact : ""}`} tabIndex={0} aria-label={`${title} (cuộn để xem toàn bộ)`} data-testid={`${testId}-content`}>
        {shown ?? text}
      </pre>
    </section>
  );
}

async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Permission denied or insecure context: fall through to the selection-based copy.
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    // Inside a modal dialog only its subtree is interactive: append the helper there.
    (document.querySelector("dialog[open]") ?? document.body).appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  } catch {
    return false;
  }
}

function CopyButton({ text, what, testId }: { text: string; what: string; testId: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  useEffect(() => {
    if (state === "idle") return;
    const t = setTimeout(() => setState("idle"), 2400);
    return () => clearTimeout(t);
  }, [state]);
  return (
    <>
      <button
        type="button"
        className={`btn btn-sm ${p.copy}`}
        data-state={state}
        data-testid={testId}
        aria-label={`Chép ${what.toLowerCase()}`}
        onClick={async () => setState((await writeClipboard(text)) ? "copied" : "failed")}
      >
        {state === "copied" ? "Đã chép ✓" : "Chép"}
      </button>
      <span className="sr-only" role="status">
        {state === "copied" ? `Đã chép ${what.toLowerCase()}` : state === "failed" ? "Không chép được, hãy chọn văn bản và chép thủ công" : ""}
      </span>
      {state === "failed" ? <span className={p.copyFail}>Không chép được</span> : null}
    </>
  );
}
