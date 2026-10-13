"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";

// Canvas / SVG libraries (ECharts, Leaflet) cannot read CSS variables themselves: they get resolved
// token values, and re-read them when the system colour scheme flips.

export function cssVar(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Live result of a media query (false during server rendering). */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const mq = window.matchMedia(query);
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    },
    [query],
  );
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches, () => false);
}

/** "dark" | "light", following the system preference live (tokens in globals.css switch on it). */
export function useColorScheme(): "dark" | "light" {
  return useMediaQuery("(prefers-color-scheme: dark)") ? "dark" : "light";
}

/**
 * Resolves `{ key: [cssVar, fallback] }` to colours, re-resolved when the colour scheme flips.
 * Pass a module-level constant so the memo holds between renders.
 */
export function useThemeTokens<K extends string>(tokens: Readonly<Record<K, readonly [string, string]>>): Record<K, string> {
  const scheme = useColorScheme();
  return useMemo(
    () => {
      const out = {} as Record<K, string>;
      for (const key of Object.keys(tokens) as K[]) out[key] = cssVar(tokens[key][0], tokens[key][1]);
      return out;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `scheme` is an implicit input: the computed CSS tokens read here change with it.
    [tokens, scheme],
  );
}
