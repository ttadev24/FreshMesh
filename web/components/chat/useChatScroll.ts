"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { prefersReducedMotion, useMediaQuery } from "@/lib/theme";

// Scroll behaviour of the conversation, for both layouts (chat.module.css):
//  - desktop: the conversation scrolls inside its own element (`.scroll`);
//  - stacked (< 1024px): the document scrolls and the composer is sticky at the bottom of the viewport.
// While a turn streams, the view follows the newest content but never scrolls the newest question past
// its scroll-margin-top (CSS), so a long answer is read from its start. Scrolling up by hand stops the
// following; reaching the end again (or sending a message) resumes it.

/** Same breakpoint as the stacked layout in workspace.module.css / chat.module.css. */
const STACKED = "(max-width: 1023px)";

export function useChatScroll(turnCount: number) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLFormElement>(null);
  const following = useRef(true);
  const composerHeight = useRef(0);
  const [atEnd, setAtEnd] = useState(true);
  const stacked = useMediaQuery(STACKED);

  /** Scrolls the conversation's scroller (never the app shell) by `dy` pixels. */
  const scrollBy = useCallback(
    (dy: number, smooth = false) => {
      const behavior: ScrollBehavior = smooth && !prefersReducedMotion() ? "smooth" : "auto";
      if (stacked) window.scrollBy({ top: dy, behavior });
      else scrollRef.current?.scrollBy({ top: dy, behavior });
    },
    [stacked],
  );

  /** Distance from the visible bottom to the end sentinel, and from the visible top to the newest question. */
  const distances = useCallback(() => {
    const last = contentRef.current?.querySelector<HTMLElement>("[data-turn]:last-child");
    const end = endRef.current;
    const own = scrollRef.current;
    if (!end || !own) return null;
    const box = own.getBoundingClientRect();
    const top = stacked ? 0 : box.top;
    const bottom = stacked ? window.innerHeight - composerHeight.current : box.bottom;
    const toEnd = end.getBoundingClientRect().bottom - bottom;
    const toQuestion = last ? last.getBoundingClientRect().top - parseFloat(getComputedStyle(last).scrollMarginTop) - top : toEnd;
    return { toEnd, toQuestion };
  }, [stacked]);

  /** Brings the end of the conversation into view, stopping at the newest question. */
  const follow = useCallback(() => {
    const d = distances();
    const dy = d ? Math.min(d.toEnd, d.toQuestion) : 0;
    if (dy > 1) scrollBy(dy);
  }, [distances, scrollBy]);

  const scrollToEnd = useCallback(() => {
    following.current = true;
    const d = distances();
    if (d && d.toEnd > 0) scrollBy(d.toEnd + 1, true);
  }, [distances, scrollBy]);

  // A new turn (the user just sent a message): follow it.
  useEffect(() => {
    if (turnCount === 0) return;
    following.current = true;
    follow();
  }, [turnCount, follow]);

  // Content growth (streamed steps, the answer, proposal cards loaded after the drafts fetch).
  useEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    const ro = new ResizeObserver(() => {
      if (following.current) follow();
    });
    ro.observe(content);
    return () => ro.disconnect();
  }, [follow]);

  // Scrolling up by hand stops the following.
  useEffect(() => {
    const own = scrollRef.current;
    const read = () => (stacked ? window.scrollY : (own?.scrollTop ?? 0));
    const target: HTMLElement | Window | null = stacked ? window : own;
    if (!target) return;
    let last = read();
    const onScroll = () => {
      const now = read();
      if (now < last - 2) following.current = false;
      last = now;
    };
    target.addEventListener("scroll", onScroll, { passive: true });
    return () => target.removeEventListener("scroll", onScroll);
  }, [stacked]);

  // "At the end" = the sentinel after the last turn is visible above the composer. On stacked layouts the
  // sticky composer covers the bottom of the viewport, so the observer's root shrinks by its height.
  useEffect(() => {
    const end = endRef.current;
    const composer = composerRef.current;
    if (!end || !composer) return;
    let io: IntersectionObserver | null = null;
    const observe = () => {
      io?.disconnect();
      io = new IntersectionObserver(
        ([entry]) => {
          setAtEnd(entry.isIntersecting);
          if (entry.isIntersecting) following.current = true;
        },
        stacked ? { root: null, rootMargin: `0px 0px -${composerHeight.current}px 0px` } : { root: scrollRef.current },
      );
      io.observe(end);
    };
    const ro = new ResizeObserver(() => {
      const h = Math.round(composer.getBoundingClientRect().height);
      if (h === composerHeight.current) return;
      composerHeight.current = h;
      if (stacked) observe();
    });
    composerHeight.current = Math.round(composer.getBoundingClientRect().height);
    ro.observe(composer);
    observe();
    return () => {
      ro.disconnect();
      io?.disconnect();
    };
  }, [stacked]);

  return { scrollRef, contentRef, endRef, composerRef, atEnd, scrollToEnd };
}
