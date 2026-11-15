// Agents' requests on this page: what waits comes with the live stream (the machines panel's
// `asks` and `allowed`); the settings history and the Agents option are read from `/api/asks`
// while a view needs them. An answer given here stays in the strip as a decided line, with
// Undo, until the node has taken the value (its history row has `in_force_at`); a decline
// until Got it. "Got it" on a grey tell is remembered in this browser.

import { useEffect } from "react";

import { problemText } from "../lib/api";
import { groupAsks, readAsks, sendAgents, sendAnswer, sendUndo, type AgentsOption, type Ask, type AskGroup, type AsksBody, type Change } from "../lib/asks";
import { decidedLine, type Line } from "../lib/asksText";
import { createStore, useStore } from "../lib/store";
import { useMachines } from "./live";

export interface Decided { change: string; node: string; approve: boolean; line: Line; asks: string[] }
interface State { body: AsksBody | null; problem: string | null }

export const asksStore = createStore<State>({ body: null, problem: null });
export const decidedStore = createStore<Decided[]>([]);
export const undoneStore = createStore<Set<string>>(new Set());
// The review window, open on the groups the owner chose, wherever it was opened from, so it
// stays open when the strip's last request is answered in it.
export const reviewStore = createStore<{ groups: AskGroup[]; opener: HTMLElement | null } | null>(null);

const GOT_IT = "mulebox.asks.got-it";
function readGotIt(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(GOT_IT) ?? "[]") as string[]); } catch { return new Set(); }
}
export const gotItStore = createStore<Set<string>>(readGotIt());
export function gotIt(id: string) {
  gotItStore.set((had) => new Set([...had, id]));
  try { localStorage.setItem(GOT_IT, JSON.stringify([...gotItStore.get()].slice(-200))); } catch { /* private mode: until the page closes */ }
}

// A history row the node has taken, or that is gone from the history: its decided line goes.
function settle(body: AsksBody) {
  decidedStore.set((had) => {
    const left = had.filter((d) => {
      const row = body.changes.find((c) => c.id === d.change);
      const undone = body.changes.some((c) => c.undo_of === d.change);
      return !d.approve || (!undone && (!row || row.in_force_at === null));
    });
    return left.length === had.length ? had : left;
  });
}
function took(body: AsksBody) {
  asksStore.set({ body, problem: null });
  settle(body);
}

export async function refreshAsks(): Promise<void> {
  try { took(await readAsks()); } catch (failure) { asksStore.set((had) => ({ ...had, problem: problemText(failure) })); }
}

// Read now and every few seconds while a view shows the history, or a decided line waits.
const EVERY_MS = 5000;
let watchers = 0, timer: ReturnType<typeof setInterval> | undefined;
function tick() {
  if (document.hidden) return;
  if (watchers > 0 || decidedStore.get().some((d) => d.approve)) void refreshAsks();
}
function watch(): () => void {
  watchers += 1;
  void refreshAsks();
  timer ??= setInterval(tick, EVERY_MS);
  return () => { watchers -= 1; };
}
export function startAsks(): () => void {
  timer ??= setInterval(tick, EVERY_MS);
  return () => { clearInterval(timer); timer = undefined; };
}
export function useAsksBody(): State {
  useEffect(() => watch(), []);
  return useStore(asksStore);
}

// Requests still waiting: the stream's, less those answered here since it was sent.
export function useWaiting(): AskGroup[] {
  const asks = useMachines()?.asks ?? [];
  const decided = useStore(decidedStore);
  const answered = new Set(decided.flatMap((d) => d.asks));
  return groupAsks(asks.filter((ask: Ask) => !answered.has(ask.id)));
}
export function useAllowed(): Change[] {
  const allowed = useMachines()?.allowed ?? [];
  const seen = useStore(gotItStore);
  return allowed.filter((change) => !seen.has(change.id));
}

// Answer a node's requests; null when taken, else what went wrong in words.
export async function answer(group: AskGroup, approve: boolean, limit: string | null,
                             more: { value?: string; note?: string } = {}): Promise<string | null> {
  try {
    const body = await sendAnswer(group.node, approve, more);
    const chosen = approve ? more.value ?? group.largest : null;
    decidedStore.set((had) => [...had, { change: body.change_id ?? "", node: group.node, approve, asks: group.asks.map((a) => a.id),
                                          line: decidedLine(group, approve, chosen, limit) }]);
    took(body);
    return null;
  } catch (failure) {
    return problemText(failure);
  }
}

export async function undo(change: string): Promise<string | null> {
  try {
    const body = await sendUndo(change);
    decidedStore.set((had) => had.filter((d) => d.change !== change));
    undoneStore.set((had) => new Set([...had, change]));
    took(body);
    return null;
  } catch (failure) {
    return problemText(failure);
  }
}
export const dropDecided = (change: string) => decidedStore.set((had) => had.filter((d) => d.change !== change));

export async function saveAgents(option: AgentsOption): Promise<string | null> {
  try { took(await sendAgents(option)); return null; } catch (failure) { return problemText(failure); }
}
