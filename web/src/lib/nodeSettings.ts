// A node's settings window, without React: what the server says (docs/interfaces-m2.md, Node
// settings), what the viewer has changed and not saved yet, and what Save sends.
//
// Three values per setting: what the node runs with now (`current`), a change the coordinator
// holds until the node takes it (`pending`), and the viewer's own edit (`Draft`). An edit is
// "unsaved" until Save; only a saved one is ever "pending".

import { getJson, post } from "./api";
import { unsent as unsentOf } from "./edits";
import { REREAD_MS } from "./turns";

export const STORAGE_KEYS = ["keep_free", "unused_days", "keep_latest", "idle_days",
                             "auto_clean", "docker_clean", "max_size", "warn_size"] as const;
export const KEYS = ["slots", "priority", "dev", ...STORAGE_KEYS] as const;
export type SettingKey = typeof KEYS[number];
// `dev` is missing from a node older than 1.23, which has no dev mode; the four disk settings
// (docs/design.md, Disk use and cleanup on its own) from one older than 1.24, and the last four
// (common/storage_policy.py) from one older than 1.26.
export interface Values {
  slots: number; priority: string; dev?: boolean;
  keep_free?: string; unused_days?: number; keep_latest?: boolean; idle_days?: number;
  auto_clean?: boolean; docker_clean?: boolean; max_size?: string; warn_size?: string;
}
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
  choices?: { slots?: { min: number; max: number }; priority?: string[]; dev?: boolean[];
              keep_free?: { max_share: number }; unused_days?: { min: number; max: number };
              idle_days?: { min: number; max: number }; auto_clean?: boolean[]; docker_clean?: boolean[];
              max_size?: Record<string, string>; warn_size?: Record<string, string> };
  defaults?: Pick<Values, typeof STORAGE_KEYS[number]>;  // what mulebox suggests for the disk settings
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
// Dev mode (common/node_settings.py): off by default; on, the node takes only jobs sent to it.
export const DEV_MODES: { value: string; label: string; says: string }[] = [
  { value: "off", label: "Off", says: "Takes any job it can run." },
  { value: "on", label: "On", says: "Takes only jobs sent to it with --on, and its own runners." },
];
export const devLabel = (value: boolean | null | undefined) =>
  value === null || value === undefined ? "-" : value ? "On" : "Off";
export const priorityLabel = (value: string | null | undefined) =>
  PRIORITIES.find((choice) => choice.value === value)?.label ?? (value || "-");

// node.toml's own defaults for the disk settings, when the server names none.
export const STORAGE_DEFAULTS = { keep_free: "10%", unused_days: 7, keep_latest: true, idle_days: 14,
                                  auto_clean: true, docker_clean: true, max_size: "OFF", warn_size: "50GB" };
// A size setting with no limit, as the node writes it back (common/storage_policy.py).
export const OFF = "OFF";
export const ON_OFF: { value: string; label: string }[] = [{ value: "on", label: "On" }, { value: "off", label: "Off" }];
export const DAYS_RANGE = { min: 1, max: 365 };
export const LATEST: { value: string; label: string; says: string }[] = [
  { value: "keep", label: "Keep", says: "Each project's most recent folder stays however old, so its next job starts warm." },
  { value: "remove", label: "Remove", says: "A project's latest folder goes like the rest once it is unused long enough." },
];

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
  const body: Record<string, unknown> = {};
  for (const key of KEYS) if (rowOf(view, draft, key).mark === "unsaved") body[key] = draft[key];
  return body as Draft;
}

// The edits left once `sent` was saved (lib/edits.ts).
export const unsent = (draft: Draft, sent: Draft): Draft => unsentOf<Values>(draft, sent);

// "All as suggested": the suggestion as fixed values of the viewer's own, still to be saved; of
// the disk settings only those the node reports, as an older node takes no others.
export function asSuggested(view: NodeSettings): Draft {
  const defaults: Draft = { ...STORAGE_DEFAULTS, ...view.defaults };
  const disk = Object.fromEntries(STORAGE_KEYS.filter((key) => view.current?.[key] !== undefined)
    .map((key) => [key, defaults[key]]));
  return { priority: SUGGESTED_PRIORITY, ...(typeof view.current?.dev === "boolean" ? { dev: false } : {}),
           ...(view.suggested ? { slots: view.suggested.slots } : {}), ...disk };
}

const url = (name: string) => `/api/machines/${encodeURIComponent(name)}/settings`;
export const readSettings = (name: string) => getJson<NodeSettings>(url(name));
export const saveSettings = (name: string, body: Draft) => post<NodeSettings>(url(name), body);
export const dropPending = (name: string) => post<NodeSettings>(url(name), { cancel: true });
