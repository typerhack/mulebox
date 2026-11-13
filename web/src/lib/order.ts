// The order rules of the line, without React: what a level is called, what changed between the
// stored rules and the ones being edited, and the short line a waiting row shows for its place
// (docs/design.md, Order of the line; coordinator/line_rules.py, line_why.py).

import { ArrowDown, Clock, Flag, GitBranch, Hand, Hourglass, Repeat, Timer, Workflow, type LucideIcon } from "lucide-react";

import type { Choice } from "../ui/Segmented";
import { ago, day, roughly, shortId } from "./format";
import type { Job, OrderPart, Rules, RulesBody } from "./types";

export type LevelMap = "projects" | "branches" | "workflows";
export const LEVEL_MAPS: LevelMap[] = ["projects", "branches", "workflows"];
export const WORDS: Record<string, number> = { low: -1, normal: 0, high: 1 };
export const MAX_AGING_MIN = 24 * 60;
export const MAX_NAME = 100;

// A level by its name, 0 when the name has none. Never the plain `map[name]`: a project may be
// called "constructor" or "toString", and an object answers those with a function of its own.
export const levelOf = (map: Record<string, number>, name: string): number => (Object.hasOwn(map, name) ? map[name] : 0);

export const signed = (level: number) => (level > 0 ? `+${level}` : String(level));

// low, normal or high; any other stored level as its number.
export function levelName(level: number, words: Record<string, number> = WORDS): string {
  return Object.keys(words).find((word) => words[word] === level) ?? signed(level);
}

// The choices a level offers: High, Normal, Low, and the stored number when it is none of them.
export function levelChoices(saved: number, words: Record<string, number> = WORDS): Choice<number>[] {
  const named = [["high", "High"], ["normal", "Normal"], ["low", "Low"]]
    .filter(([word]) => Object.hasOwn(words, word)).map(([word, label]) => ({ value: words[word], label }));
  return named.some(({ value }) => value === saved) ? named : [...named, { value: saved, label: signed(saved) }];
}

// What to send so the stored rules become the edited ones: only what differs. Maps merge entry
// by entry on the server, and a level of 0 removes one.
export function changeOf(saved: Rules, draft: Rules): Partial<Rules> {
  const change: Partial<Rules> = {};
  for (const map of LEVEL_MAPS) {
    const entries = new Map<string, number>();
    for (const name of new Set([...Object.keys(saved[map]), ...Object.keys(draft[map])])) {
      const was = levelOf(saved[map], name), now = levelOf(draft[map], name);
      if (was !== now) entries.set(name, now);
    }
    if (entries.size) change[map] = Object.fromEntries(entries);
  }
  if (saved.github !== draft.github) change.github = draft.github;
  if (saved.aging_min !== draft.aging_min) change.aging_min = draft.aging_min;
  if (saved.shortest_first !== draft.shortest_first) change.shortest_first = draft.shortest_first;
  if (saved.fair_turns !== draft.fair_turns) change.fair_turns = draft.fair_turns;
  return change;
}

// The rules with `change` (changeOf's shape) laid over them: maps entry by entry, a level of 0
// kept as an entry so its row stays in the list while it is being edited.
export function applyChange(rules: Rules, change: Partial<Rules>): Rules {
  const out: Rules = { ...rules, ...change };
  for (const map of LEVEL_MAPS) out[map] = { ...rules[map], ...change[map] };
  return out;
}

export const isDirty = (saved: Rules, draft: Rules) => Object.keys(changeOf(saved, draft)).length > 0;
export const isDefault = (body: RulesBody) => !isDirty(body.defaults, body.rules);

// The projects to set a level for: every one the node has seen, every one with a level and
// every one with a job waiting now (`waiting`, from the live queue, so a project new since the
// rules were read has its row at once). In two groups: those with a job or a GitHub run in the
// last seven days (or one waiting now), by name, then the rest, the latest run first and one
// that never ran last. `flat` when the answer does not say how the projects were used: then
// there is one group, as before. Names are looked up in Maps, so any name is only a name.
export interface ProjectRow { name: string; last_run: number | null; runs_7d: number; waiting: number }

export function projectGroups(body: RulesBody, draft: Rules, waiting: ReadonlyMap<string, number> = new Map()) {
  const used = new Map((body.project_activity ?? []).map((entry) => [entry.name, entry]));
  const names = [...new Set([...body.projects, ...used.keys(), ...Object.keys(body.rules.projects), ...Object.keys(draft.projects), ...waiting.keys()])];
  const rows: ProjectRow[] = names.map((name) =>
    ({ name, last_run: used.get(name)?.last_run ?? null, runs_7d: used.get(name)?.runs_7d ?? 0, waiting: waiting.get(name) ?? 0 }));
  if (!body.project_activity) return { flat: true, active: rows, other: [] };
  const isActive = (row: ProjectRow) => row.runs_7d > 0 || row.waiting > 0;
  const byName = (a: ProjectRow, b: ProjectRow) => a.name.localeCompare(b.name);
  return { flat: false, active: rows.filter(isActive).sort(byName),
           other: rows.filter((row) => !isActive(row)).sort((a, b) => (b.last_run ?? 0) - (a.last_run ?? 0) || byName(a, b)) };
}

// The one fact beside a project's name: what waits now, else how much it ran this week and when
// last; for a project not used this week, the day of its last run.
export function projectNote(row: ProjectRow, now: number, flat = false): string | undefined {
  const waits = row.waiting ? `${row.waiting} waiting` : undefined;
  if (flat) return waits;
  const runs = `${row.runs_7d} ${row.runs_7d === 1 ? "run" : "runs"}`;
  if (waits) return row.runs_7d ? `${waits}, ${runs}` : waits;
  if (row.runs_7d) return `${runs}, last ${ago(row.last_run, now).replace(/^now$/, "just now")}`;
  return row.last_run ? `last run ${day(row.last_run, now)}` : "no run yet";
}

// How many levels are set: the entries that are not normal, and GitHub runs when not normal.
export function levelsSet(rules: Rules): number {
  return LEVEL_MAPS.reduce((sum, map) => sum + Object.values(rules[map]).filter(Boolean).length, 0)
    + (rules.github ? 1 : 0);
}

// Whether a rule can change the order of arrival. Aging alone cannot: an older job has waited
// at least as long as a younger one.
export const ordering = (rules: Rules) => levelsSet(rules) > 0 || rules.shortest_first || rules.fair_turns;

// A new branch pattern or workflow name, or why it cannot be added.
export function nameProblem(name: string, taken: Record<string, number>): string | null {
  if (!name) return "Type a name first.";
  if (name.length > MAX_NAME) return `At most ${MAX_NAME} characters.`;
  if (Object.hasOwn(taken, name)) return "It is already in the list.";
  return null;
}

const waited = (minutes: number) =>
  (minutes >= 60 ? `${Math.floor(minutes / 60)}h${minutes % 60 ? ` ${minutes % 60}m` : ""}` : `${minutes}m`);

function partText(part: OrderPart, words: Record<string, number>): string {
  const word = levelName(part.level, words);
  if (part.rule === "project") return `project ${word}`;
  if (part.rule === "github") return `GitHub runs ${word}`;
  if (part.rule === "waited") return `waited ${waited(part.over ?? part.minutes ?? 0)} or more`;
  return `${part.rule} ${part.name ?? ""} ${word}`.replace(/\s+/g, " ");
}

function partIcon(part: OrderPart): LucideIcon {
  if (part.rule === "project") return part.level < 0 ? ArrowDown : Flag;
  if (part.rule === "branch") return GitBranch;
  if (part.rule === "waited") return Hourglass;
  return Workflow;
}

export interface Place { Icon: LucideIcon; text: string }

function movedPlace(job: Job): Place {
  const moved = job.order?.moved, side = moved?.side ?? job.moved;
  if (side === "front") return { Icon: Hand, text: job.kind === "upgrade" ? "an upgrade, sent to go first" : "moved to the front by hand" };
  const other = moved?.job_id ? shortId({ job_id: moved.job_id }) : null;
  if (!other || (side !== "before" && side !== "after")) return { Icon: Hand, text: "placed by hand" };
  const where = side === "before" ? "ahead of" : "behind";
  return { Icon: Hand, text: moved?.in_line === false ? `moved by hand, in the place ${where} ${other}, which has left the line`
                                                       : `moved by hand, just ${where} ${other}` };
}

// The short reason on a waiting row: the rule that put it there first, with that rule's icon.
// Nothing with the defaults and nothing moved, when the server sends no reason.
export function placeOf(job: Job, words: Record<string, number> = WORDS): Place | null {
  const order = job.order;
  if (!order) return job.place_reason ? { Icon: Clock, text: job.place_reason } : null;
  if (order.moved || order.by_hand || job.moved) return movedPlace(job);
  const bits: Place[] = [];
  const parts = (order.levels ?? []).filter((part) => part.level);
  if (parts.length) {
    const level = order.level ?? parts.reduce((sum, part) => sum + part.level, 0);
    const lead = [...parts].sort((a, b) => Math.abs(b.level) - Math.abs(a.level))
      .find((part) => !level || Math.sign(part.level) === Math.sign(level)) ?? parts[0];
    const side = level > 0 ? "ahead" : level < 0 ? "behind" : "level 0";
    bits.push({ Icon: partIcon(lead), text: `${side}: ${parts.map((part) => partText(part, words)).join(", ")}` });
  }
  if (typeof order.turn === "number") bits.push({ Icon: Repeat, text: `fair turn ${order.turn}` });
  if ("usual_s" in order) {
    bits.push({ Icon: Timer, text: typeof order.usual_s === "number" ? `usually ${roughly(order.usual_s)}`
      : typeof order.counted_as_s === "number" ? `no usual length yet, counted as ${roughly(order.counted_as_s)}`
        : "no usual length yet" });
  }
  if (!bits.length) return { Icon: Clock, text: "in order of arrival" };
  return { Icon: bits[0].Icon, text: bits.map((bit) => bit.text).join("; ") };
}
