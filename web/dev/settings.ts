// Node settings for the stand-in API (docs/interfaces-m2.md, Node settings): what each node
// has, a change that waits, and the suggestion. A saved change is pending for a few seconds,
// as a node on another machine takes it with its next check-in, then it is what the node has.

import { SETTINGS_SCENE } from "./scenes.ts";

interface Row { name: string; slots: number; state: string; cores?: number | null; version?: string | null; jobs: unknown[] }
interface Kept { priority: string; pending: Record<string, unknown> | null; since: number | null; error: string | null; old: boolean }

const TAKES_MS = 6000;
const PRIORITIES = ["preferred", "normal", "fallback"];
const scene = process.env.MULEBOX_MOCK_SCENE === "settings" ? SETTINGS_SCENE : {};
const kept = new Map<string, Kept>();

function of(row: Row): Kept {
  let found = kept.get(row.name);
  if (!found) {
    const start = scene[row.name] ?? {};
    found = { priority: "normal", pending: (start.pending as Kept["pending"]) ?? null, since: start.pending ? Date.now() / 1000 - 40 : null,
              error: (start.error as string) ?? null, old: Boolean(start.old) };
    kept.set(row.name, found);
  }
  return found;
}

// A machine's row with the two fields the settings add to it.
export const withSettings = <T extends Row>(row: T) =>
  ({ ...row, priority: of(row).old ? null : of(row).priority, settings_pending: Boolean(of(row).pending) });

function view(row: Row, editable: boolean) {
  const has = of(row), cores = row.cores ?? 8, memory = cores * 2;
  return {
    worker: row.name, online: row.state !== "offline", draining: row.state === "draining", version: has.old ? "1.14.5" : row.version,
    running: row.jobs.length, applies: !has.old, current: has.old ? null : { slots: row.slots, priority: has.priority },
    pending: has.pending, pending_since: has.since, error: has.pending ? has.error : null,
    suggested: { slots: Math.max(1, Math.min(Math.floor(cores / 4), Math.floor(memory / 6))),
                 reason: `${cores} cores and ${memory} GB of memory, at about 4 cores and 6 GB a job` },
    choices: { slots: { min: 1, max: 64 }, priority: PRIORITIES }, editable,
  };
}

// GET with `change` null, else a POST's body. `changed` is called when the node took a change.
export function answerSettings(row: Row, change: Record<string, unknown> | null, editable: boolean, changed: () => void) {
  const has = of(row);
  if (!change) return { status: 200, body: view(row, editable) };
  if (has.old) return { status: 409, body: `${row.name} has not reported its settings: it runs a mulebox older than this one; upgrade it first` };
  const slots = change.slots, priority = change.priority;
  if (slots !== undefined && !(Number.isInteger(slots) && (slots as number) >= 1 && (slots as number) <= 64)) return { status: 400, body: "slots must be a whole number from 1 to 64" };
  if (priority !== undefined && !PRIORITIES.includes(String(priority))) return { status: 400, body: "priority must be preferred, normal or fallback" };
  const wanted: Record<string, unknown> = change.cancel ? {} : { ...has.pending };
  if (slots !== undefined) wanted.slots = slots;
  if (priority !== undefined) wanted.priority = priority;
  if (wanted.slots === row.slots) delete wanted.slots;
  if (wanted.priority === has.priority) delete wanted.priority;
  const waits = Object.keys(wanted).length > 0;
  Object.assign(has, { pending: waits ? wanted : null, since: waits ? Date.now() / 1000 : null, error: null });
  if (waits && row.state !== "offline") {
    setTimeout(() => {
      if (has.pending !== wanted) return;  // changed or dropped meanwhile
      if (typeof wanted.slots === "number") row.slots = wanted.slots;
      if (typeof wanted.priority === "string") has.priority = wanted.priority;
      Object.assign(has, { pending: null, since: null });
      changed();
    }, TAKES_MS);
  }
  return { status: 200, body: view(row, editable) };
}
