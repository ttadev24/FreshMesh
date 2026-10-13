"use client";

import { useSyncExternalStore } from "react";
import type { User } from "./types";

// The API issues a bearer token. The Next app only proxies /api, so an httpOnly cookie is not
// available; the token lives in memory and is mirrored to sessionStorage (per tab, cleared when the
// tab closes) so a reload keeps the session. Storage can throw (private mode, blocked site data):
// every access is guarded and the in-memory copy stays authoritative.

export interface Session {
  token: string;
  user: User;
}

const STORAGE_KEY = "freshmesh.session.v1";
type Listener = () => void;

let current: Session | null = null;
let hydrated = false;
const listeners = new Set<Listener>();

function readStorage(): Session | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Session>;
    if (typeof parsed.token === "string" && parsed.user && typeof parsed.user.user_id === "string") {
      return parsed as Session;
    }
  } catch {
    // Unreadable storage behaves like an empty one.
  }
  return null;
}

function writeStorage(value: Session | null) {
  try {
    if (value) window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // In-memory session still works for this page lifetime.
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

export function setSession(value: Session | null) {
  ensureHydrated();
  current = value;
  writeStorage(value);
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
