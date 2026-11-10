// The one way this page asks the server, and the one way it asks for a change
// (docs/interfaces-m2.md, Controls).
//
// The server gives a token to send back with every change, or null when its controls are off.
// The token is the service's own, or the sign-in's with a password, so after the service
// restarts the old one is refused once: the page then asks for the new one and tries again.

import { createStore } from "./store";

export class ApiError extends Error {
  status: number | null;
  constructor(message: string, status: number | null = null) {
    super(message);
    this.status = status;
  }
}

export async function getJson<T>(url: string): Promise<T> {
  const reply = await fetch(url, { headers: { Accept: "application/json" } });
  if (!reply.ok) throw new ApiError(`${reply.status} ${(await reply.text()).trim()}`, reply.status);
  return reply.json() as Promise<T>;
}

// What the page may change: `undefined` until the server answered, null with the controls off.
export const tokenStore = createStore<string | null | undefined>(undefined);
let pending: Promise<string | null> | null = null;

export function actionToken(fresh = false): Promise<string | null> {
  if (fresh || !pending) {
    pending = getJson<{ action_token?: string | null; cancel_token?: string | null }>("/api/session")
      .then((access) => access?.action_token ?? access?.cancel_token ?? null)
      .catch(() => null)  // no answer: no buttons, the rest of the page still works
      .then((token) => { tokenStore.set(token); return token; });
  }
  return pending;
}

function once(url: string, body: unknown, token: string | null): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: { "X-Mulebox-Token": token ?? "", Accept: "application/json",
               ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
}

// The reply's JSON; an ApiError with `status` and the server's own words when it is refused.
export async function post<T = Record<string, unknown>>(url: string, body: unknown = null): Promise<T> {
  let reply = await once(url, body, await actionToken());
  if (reply.status === 403) reply = await once(url, body, await actionToken(true));
  if (!reply.ok) throw new ApiError((await reply.text()).trim(), reply.status);
  return reply.json() as Promise<T>;
}

// What to tell the viewer when a change failed: the server's words, or that it said nothing.
export const problemText = (failure: unknown) =>
  (failure instanceof ApiError && failure.status ? failure.message : "The dashboard did not answer.");

const jobUrl = (id: string, what: string) => `/api/jobs/${encodeURIComponent(id)}/${what}`;
export type JobAction = "pause" | "resume" | "first" | "up" | "down" | "last" | "boost" | "normal";
export const controlJob = (id: string, action: JobAction) => post(jobUrl(id, "control"), { action });
export const cancelJob = (id: string) => post<{ state?: string }>(jobUrl(id, "cancel"));
export const controlMachine = (name: string, action: "pause" | "resume") =>
  post(`/api/machines/${encodeURIComponent(name)}/control`, { action });
