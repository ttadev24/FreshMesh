"use client";

import { useSyncExternalStore } from "react";
import type { User } from "./types";

// The API issues a bearer token. The Next app only proxies /api, so an httpOnly cookie is not
// available; the token lives in memory and is mirrored to sessionStorage (per tab, cleared when the
// tab closes) so a reload keeps the session, or to localStorage when the user ticks "Ghi nhớ đăng
// nhập" (survives closing the browser until the token expires). Storage can throw (private mode,
// blocked site data): every access is guarded and the in-memory copy stays authoritative.

export interface Session {
  token: string;
  user: User;
}

const STORAGE_KEY = "freshmesh.session.v1";
type Listener = () => void;

let current: Session | null = null;
let hydrated = false;
const listeners = new Set<Listener>();

const STORES = ["sessionStorage", "localStorage"] as const;

function readStorage(): Session | null {
  for (const store of STORES) {
    try {
      const raw = window[store].getItem(STORAGE_KEY);
      if (!raw) continue;
      const parsed = JSON.parse(raw) as Partial<Session>;
      if (typeof parsed.token === "string" && parsed.user && typeof parsed.user.user_id === "string") {
        return parsed as Session;
      }
    } catch {
      // Unreadable storage behaves like an empty one.
    }
  }
  return null;
}

function writeStorage(value: Session | null, remember: boolean) {
  for (const store of STORES) {
    try {
      // Keep the session in exactly one store; clearing removes it from both.
      if (value && (store === "localStorage") === remember) {
        window[store].setItem(STORAGE_KEY, JSON.stringify(value));
      } else {
        window[store].removeItem(STORAGE_KEY);
      }
    } catch {
      // In-memory session still works for this page lifetime.
    }
  }
}

function ensureHydrated() {
  if (!hydrated && typeof window !== "undefined") {
    hydrated = true;
    current = readStorage();
  }
}

export function getSession(): Session | null {
  ensureHydrated();
  return current;
}

export function setSession(value: Session | null, options: { remember?: boolean } = {}) {
  ensureHydrated();
  current = value;
  writeStorage(value, options.remember ?? false);
  listeners.forEach((l) => l());
}

export function clearSession() {
  setSession(null);
}

function subscribe(listener: Listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** `undefined` while rendering on the server (session unknown), `null` when logged out. */
export function useSession(): Session | null | undefined {
  return useSyncExternalStore(subscribe, getSession, () => undefined);
}
