// Minimal fetch client for the PROPOSED demo API (docs/api-contract/frontend-v1.md).
// Errors are mapped to fixed user-facing text; response bodies are never logged or surfaced.

import type { ApiErrorBody } from "./types";

export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1"; // same origin: Vite proxies /api to the local demo API

export type SafeErrorCode = "unreachable" | "timeout" | "not_found" | "busy" | "bad_contract" | "server_error";

export class SafeError extends Error {
  readonly code: SafeErrorCode;
  constructor(code: SafeErrorCode) {
    super(SAFE_MESSAGES[code]);
    this.code = code;
    this.name = "SafeError";
  }
}

export const SAFE_MESSAGES: Record<SafeErrorCode, string> = {
  unreachable: "The local CLINVEIL backend is not reachable.",
  timeout: "The local CLINVEIL backend did not answer in time.",
  not_found: "The requested result does not exist.",
  busy: "Another run is in progress. Wait for it to finish, then start a new one.",
  bad_contract: "The backend answered in a format this interface does not understand.",
  server_error: "The backend reported an error. Details are in the backend's local log.",
};

export async function getJson<T extends { contract: string }>(path: string, timeoutMs = 4000): Promise<T> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      signal: ctl.signal,
      headers: { Accept: "application/json" },
      credentials: "omit",
      referrerPolicy: "no-referrer",
    });
  } catch {
    throw new SafeError(ctl.signal.aborted ? "timeout" : "unreachable");
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 404) throw new SafeError("not_found");
  if (res.status === 409) throw new SafeError("busy");
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new SafeError("bad_contract");
  }
  if (!res.ok || (body as ApiErrorBody).error) throw new SafeError("server_error");
  if (typeof body !== "object" || body === null || (body as { contract?: string }).contract !== "clinveil-frontend/1") {
    throw new SafeError("bad_contract");
  }
  return body as T;
}

export async function postJson<T extends { contract: string }>(path: string, body: unknown, timeoutMs = 8000): Promise<T> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      signal: ctl.signal,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "omit",
      referrerPolicy: "no-referrer",
    });
  } catch {
    throw new SafeError(ctl.signal.aborted ? "timeout" : "unreachable");
  } finally {
    clearTimeout(timer);
  }
  let data: unknown;
  try {
    data = await res.json();
  } catch {
    throw new SafeError("bad_contract");
  }
  if (res.status === 409) throw new SafeError("busy");
  if (!res.ok || (data as ApiErrorBody).error) throw new SafeError("server_error");
  if ((data as { contract?: string }).contract !== "clinveil-frontend/1") throw new SafeError("bad_contract");
  return data as T;
}
