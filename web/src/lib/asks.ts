// Agents' requests for a setting change, such as more space for mulebox on a node, and the
// settings history (docs/interfaces-m2.md, Requests for more space; docs/design.md, Agents
// asking for more space), without React: the shapes, the calls, and how requests are grouped
// for one answer. The wording is in asksText.ts.

import { getJson, post } from "./api";
import { held, sizeBytes, type StorageBody } from "./storage";

export interface AskAnswer { value: string | null; note: string | null; by: string | null; at: number }
export interface Ask {
  id: string; node: string; setting: string; value: string; reason: string | null;
  project: string | null; job_id: string | null; client: string | null; asked_at: number;
  state: "waiting" | "approved" | "declined" | "applied"; answer: AskAnswer | null; change_id: string | null;
}
export type How = "owner" | "approved" | "approved_other" | "declined" | "allowed" | "undo" | "agents";
export interface AskedFor { value: string; reason: string | null; project: string | null; job_id: string | null; client: string | null; asked_at: number }
export interface Change {
  id: string; node: string | null; setting: string; old: string | null; new: string | null; how: How;
  asked: { value: string | null; note: string | null; asks: AskedFor[] } | null;
  by: string | null; at: number; in_force_at: number | null; undo_of: string | null; undoable: boolean;
}
export type AgentsOption = "ask" | "allow";
export interface AsksBody { asks: Ask[]; changes: Change[]; agents: AgentsOption; editable: boolean; change_id?: string }

export const readAsks = (history = 50) => getJson<AsksBody>(`/api/asks?history=${history}`);
export const sendAnswer = (node: string, approve: boolean, more: { value?: string; note?: string } = {}) =>
  post<AsksBody>("/api/asks", { action: "answer", approve, node, ...more });
export const sendUndo = (change: string) => post<AsksBody>("/api/asks", { action: "undo", change });
export const sendAgents = (option: AgentsOption) => post<AsksBody>("/api/asks", { action: "agents", option });

// The requests for one setting of one node: they get one answer, offered at the largest value.
export interface AskGroup { node: string; setting: string; asks: Ask[]; largest: string; oldest: number }
const size = (value: string) => sizeBytes(value) ?? (Number(value) || 0);
export function groupAsks(asks: Ask[]): AskGroup[] {
  const groups = new Map<string, Ask[]>();
  for (const ask of [...asks].sort((a, b) => a.asked_at - b.asked_at)) {
    const key = `${ask.node}\u0000${ask.setting}`;
    groups.set(key, [...(groups.get(key) ?? []), ask]);
  }
  return [...groups.values()].map((list) => ({
    node: list[0].node, setting: list[0].setting, asks: list, oldest: list[0].asked_at,
    largest: list.reduce((best, ask) => (size(ask.value) > size(best) ? ask.value : best), list[0].value),
  })).sort((a, b) => a.oldest - b.oldest);
}

// A size setting in whole GB for the stepper, and back ("25GB").
export const wholeGb = (value: string | null | undefined) => Math.round((sizeBytes(value) ?? 0) / 1e9);
export const gbValue = (gb: number) => `${gb}GB`;

// What the node's last storage report says around a request: the space it has and holds, and
// its disk. Null with no report from that node.
export interface NodeRoom { limit: string | null; held: number; free: number; total: number; floor: number; keepFree: string; clean: number }
export function roomOf(body: StorageBody | null, node: string): NodeRoom | null {
  const report = body?.nodes.find((n) => n.node === node)?.report;
  if (!report) return null;
  const folders = report.projects.flatMap((p) => p.folders);
  const clean = folders.reduce((sum, f) => sum + (f.fate === "remove" ? f.size : f.slim === "due" ? f.frees ?? 0 : 0), 0);
  return { limit: report.policy.max_size ?? null, held: held(report), free: report.disk.free, total: report.disk.total,
           floor: report.disk.reserve, keepFree: report.policy.keep_free, clean };
}
