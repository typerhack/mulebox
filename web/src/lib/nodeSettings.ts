// A node's settings window, without React: what the server says (docs/interfaces-m2.md, Node
// settings), what the viewer has changed and not saved yet, and what Save sends.
//
// Three values per setting: what the node runs with now (`current`), a change the coordinator
// holds until the node takes it (`pending`), and the viewer's own edit (`Draft`). An edit is
// "unsaved" until Save; only a saved one is ever "pending".

import { getJson, post } from "./api";
import { unsent as unsentOf } from "./edits";
import { REREAD_MS } from "./turns";

export type SettingKey = "slots" | "priority";
export interface Values { slots: number; priority: string }
export type Draft = Partial<Values>;

export interface NodeSettings {
  worker: string;
  online: boolean;
  draining?: boolean;
  version?: string | null;
  running?: number;
  applies: boolean;
  current: Values | null;
  pending: Draft | null;
  pending_since?: number | null;
  error?: string | null;
  suggested: { slots: number; reason: string } | null;
  choices?: { slots?: { min: number; max: number }; priority?: string[] };
  editable: boolean;
}

export const POLL_MS = REREAD_MS;  // how often an open window asks the node's settings again
export const SLOTS_RANGE = { min: 1, max: 64 };
// node.toml's own default when it names no priority (docs/design.md, Node settings).
export const SUGGESTED_PRIORITY = "normal";
export const PRIORITIES: { value: string; label: string; says: string }[] = [
  { value: "preferred", label: "Preferred", says: "Jobs come here first, while it has a free slot." },
  { value: "normal", label: "Normal", says: "Takes a job when no preferred node can within 30 s." },
  { value: "fallback", label: "Fallback", says: "Takes a job only when better nodes cannot within 30 s." },
];
export const priorityLabel = (value: string | null | undefined) =>
  PRIORITIES.find((choice) => choice.value === value)?.label ?? (value || "-");

export type Mark = "unsaved" | "pending" | null;
export interface Row<K extends SettingKey> {
  now: Values[K] | null;     // what the node runs with
  yours: Values[K] | null;   // what the control shows
  mark: Mark;
}

export function rowOf<K extends SettingKey>(view: NodeSettings, draft: Draft, key: K): Row<K> {
  const now = view.current?.[key] ?? null;
  const waits = view.pending?.[key];
  const sent = (waits ?? now) as Values[K] | null;
  const edit = draft[key] as Values[K] | undefined;
  if (edit !== undefined && edit !== sent) return { now, yours: edit, mark: "unsaved" };
  return { now, yours: sent, mark: waits !== undefined && waits !== now ? "pending" : null };
}

// What Save sends: only the settings whose edit differs from what was last sent.
export function changes(view: NodeSettings, draft: Draft): Draft {
  const body: Draft = {};
  if (rowOf(view, draft, "slots").mark === "unsaved") body.slots = draft.slots;
  if (rowOf(view, draft, "priority").mark === "unsaved") body.priority = draft.priority;
  return body;
}

// The edits left once `sent` was saved (lib/edits.ts).
export const unsent = (draft: Draft, sent: Draft): Draft => unsentOf<Values>(draft, sent);

// "All as suggested": the suggestion as fixed values of the viewer's own, still to be saved.
export const asSuggested = (view: NodeSettings): Draft =>
  ({ priority: SUGGESTED_PRIORITY, ...(view.suggested ? { slots: view.suggested.slots } : {}) });

const url = (name: string) => `/api/machines/${encodeURIComponent(name)}/settings`;
export const readSettings = (name: string) => getJson<NodeSettings>(url(name));
export const saveSettings = (name: string, body: Draft) => post<NodeSettings>(url(name), body);
export const dropPending = (name: string) => post<NodeSettings>(url(name), { cancel: true });
