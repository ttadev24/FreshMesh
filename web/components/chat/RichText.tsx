import { Fragment, type ReactNode } from "react";
import { splitInline } from "@/lib/inline";
import s from "./chat.module.css";

// Minimal renderer for the agent's answer text: paragraphs, "- " bullets, **bold**, `code`, and
// highlighting of numbers the guardrail could not verify ("chưa kiểm chứng"). No HTML is injected.

function escapeRe(v: string) {
  return v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function markUnverified(text: string, unverified: readonly string[], keyBase: string): ReactNode[] {
  if (!unverified.length) return [text];
  const re = new RegExp(`(${unverified.map(escapeRe).join("|")})`, "g");
  return text.split(re).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={`${keyBase}-u${i}`} className={s.unverified} title="Số liệu chưa kiểm chứng: không khớp kết quả công cụ của lượt này">
        {part}
        <span className="sr-only"> (chưa kiểm chứng)</span>
      </mark>
    ) : (
      <Fragment key={`${keyBase}-t${i}`}>{part}</Fragment>
    ),
  );
}

function inline(text: string, unverified: readonly string[], keyBase: string): ReactNode[] {
  return splitInline(text).flatMap((tok, i): ReactNode[] => {
    const key = `${keyBase}-${i}`;
    if (tok.kind === "bold") return [<strong key={key}>{markUnverified(tok.text, unverified, key)}</strong>];
    if (tok.kind === "code") return [<code key={key}>{tok.text}</code>];
    return markUnverified(tok.text, unverified, key);
  });
}

export default function RichText({ text, unverified = [] }: { text: string; unverified?: readonly string[] }) {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  const flush = (key: string) => {
    if (!bullets.length) return;
    blocks.push(
      <ul key={key} className={s.rtList}>
        {bullets.map((b, i) => (
          <li key={i}>{inline(b, unverified, `${key}-${i}`)}</li>
        ))}
      </ul>,
    );
    bullets = [];
  };
  text.split("\n").forEach((line, i) => {
    const bullet = /^\s*(?:[-*•]|\d+[.)])\s+(.*)$/.exec(line);
    if (bullet) {
      bullets.push(bullet[1]);
      return;
    }
    flush(`l${i}`);
    if (line.trim()) blocks.push(<p key={`p${i}`}>{inline(line, unverified, `p${i}`)}</p>);
  });
  flush("end");
  return <div className={s.rt}>{blocks}</div>;
}
