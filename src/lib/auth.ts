import { useSyncExternalStore } from "react";
import { api } from "./api";

/**
 * Authentication boundary.
 *
 * Calls backend API for signUp/signIn and stores session with merchant_id in localStorage.
 * The rest of the app only ever talks to this module.
 */

export interface Session {
  email: string;
  businessName: string;
  merchantId: string;
  token?: string;
}

const STORAGE_KEY = "recoverai.session";

let listeners: Array<() => void> = [];

// Cached snapshot: useSyncExternalStore requires a stable reference between
// notifications, otherwise every render produces a new object and loops.
let cachedRaw: string | null = null;
let cachedSession: Session | null = null;

function readSession(): Session | null {
  if (typeof window === "undefined") return null;
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
  if (raw === cachedRaw) return cachedSession;
  cachedRaw = raw;
  try {
    cachedSession = raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    cachedSession = null;
  }
  return cachedSession;
}

function notify() {
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.push(listener);
  return () => {
    listeners = listeners.filter((l) => l !== listener);
  };
}

export function getSession(): Session | null {
  return readSession();
}

export async function signIn(email: string, password: string): Promise<Session> {
  const response = await api.signIn(email, password);
  const session: Session = {
    email: response.email,
    businessName: response.businessName,
    merchantId: response.merchantId,
    ...(response.token ? { token: response.token } : {}),
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  notify();
  return session;
}

export async function signUp(businessName: string, email: string, password: string): Promise<Session> {
  const response = await api.signUp(businessName, email, password);
  const session: Session = {
    email: response.email,
    businessName: response.businessName,
    merchantId: response.merchantId,
    ...(response.token ? { token: response.token } : {}),
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  notify();
  return session;
}

export function signOut() {
  window.localStorage.removeItem(STORAGE_KEY);
  notify();
}

/**
 * Clear session from localStorage and notify subscribers.
 * Used by the API layer on 401 responses to force a re-login
 * without importing signOut (which would create a circular dependency).
 */
export function clearSession() {
  window.localStorage.removeItem(STORAGE_KEY);
  notify();
}

export function useAuth(): Session | null {
  return useSyncExternalStore(subscribe, readSession, () => null);
}