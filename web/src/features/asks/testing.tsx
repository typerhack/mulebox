// What the request tests share: requests and history rows as the coordinator sends them, a
// node's storage report around them, a stand-in server that keeps every POST, and the strips
// with their window on a page. Every name is an example.

import { render } from "@testing-library/react";
import { vi } from "vitest";

import { tokenStore } from "../../lib/api";
import type { Ask, AsksBody, Change } from "../../lib/asks";
import { reply } from "../../lib/heldServer.testing";
import { GB, NOW, body, report } from "../../lib/storage.testing";
import { asksStore, decidedStore, gotItStore, reviewStore, undoneStore } from "../../state/asks";
import { machinesStore } from "../../state/live";
import { storageStore } from "../../state/storage";
import { TipProvider } from "../../ui/Tip";
import { OutOfStepMark, OutOfStepStrip } from "../header/OutOfStep";
import { AskWindowHost } from "./AskWindow";
import { CalmStrip } from "./CalmStrip";

export const request = (more: Partial<Ask> = {}): Ask => ({
  id: "ask-1", node: "build-1", setting: "max_size", value: "30GB", project: "example-app", client: "alice-laptop",
  job_id: "job-01JCX4M7Q2", asked_at: NOW - 12 * 60, state: "waiting", answer: null, change_id: null,
  reason: "The release branch builds three images and four branches are open this week.", ...more,
});
export const change = (more: Partial<Change> = {}): Change => ({
  id: "chg-1", node: "build-1", setting: "max_size", old: "20GB", new: "30GB", how: "allowed",
  asked: { value: "30GB", note: null, asks: [{ value: "30GB", reason: "The release branch builds three images.", project: "example-app",
                                              job_id: "job-01JCX4M7Q2", client: "alice-laptop", asked_at: NOW - 2 * 60 }] },
  by: null, at: NOW - 100, in_force_at: NOW - 94, undo_of: null, undoable: true, ...more,
});
export const asksBody = (more: Partial<AsksBody> = {}): AsksBody => ({ asks: [], changes: [], agents: "ask", editable: true, ...more });

// build-1 holds 16.4 GB of 20 GB, its disk 61 GB free of 490 GB with a floor of 49 GB.
export function lay(asks: Ask[], allowed: Change[] = []) {
  machinesStore.set({ machines: [], total: 0, online: 0, free_slots: 0, notices: [], asks, allowed });
  const made = report({ disk: { total: 490 * GB, free: 61 * GB, reserve: 49 * GB }, held: 16.4 * GB,
                        policy: { ...report().policy, max_size: "20GB" } });
  storageStore.set({ body: body({}, made), problem: null });
}

// The server: every POST to /api/asks is kept and answered with `after`.
export function serve(after: AsksBody = asksBody({ change_id: "chg-9" }), first: AsksBody = asksBody()) {
  const posts: unknown[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (url === "/api/session") return reply({ action_token: "token" });
    if (!url.startsWith("/api/asks")) return reply("not here", 404);
    if (init?.method !== "POST") return reply(first);
    posts.push(JSON.parse(String(init.body)));
    return reply(after);
  }));
  return posts;
}

export const page = () => render(
  <TipProvider><OutOfStepMark /><OutOfStepStrip /><CalmStrip /><AskWindowHost /></TipProvider>,
);

export function reset() {
  vi.unstubAllGlobals();
  localStorage.clear();
  tokenStore.set(undefined);
  machinesStore.set(null);
  storageStore.set({ body: null, problem: null });
  asksStore.set({ body: null, problem: null });
  decidedStore.set([]);
  undoneStore.set(new Set());
  gotItStore.set(new Set());
  reviewStore.set(null);
}
