// Inline grammar of the agent's answers and of docs/data-assumptions.md: **bold** and `code` only.
// Renderers turn the tokens into React nodes (no HTML is injected).

export type InlineToken = { kind: "bold" | "code" | "text"; text: string };

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`)/g;

export function splitInline(text: string): InlineToken[] {
  return text.split(INLINE).map((part): InlineToken => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return { kind: "bold", text: part.slice(2, -2) };
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return { kind: "code", text: part.slice(1, -1) };
    return { kind: "text", text: part };
  });
}

/** The same text without its markers (one-line summaries). */
export const toPlainText = (text: string) => splitInline(text).map((t) => t.text).join("");
