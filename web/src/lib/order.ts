// The order rules of the line, without React: what a level is called, what changed between the
// stored rules and the ones being edited, and the short line a waiting row shows for its place
// (docs/design.md, Order of the line; coordinator/line_rules.py, line_why.py).

import { ArrowDown, Clock, Flag, GitBranch, Hand, Hourglass, Repeat, Timer, Workflow, type LucideIcon } from "lucide-react";

import { roughly, shortId } from "./format";
import type { Job, OrderPart, Rules, RulesBody } from "./types";

export type LevelMap = "projects" | "branches" | "workflows";
export const LEVEL_MAPS: LevelMap[] = ["projects", "branches", "workflows"];
export const WORDS: Record<string, number> = { low: -1, normal: 0, high: 1 };
export const MAX_AGING_MIN = 24 * 60;
export const MAX_NAME = 100;

export const signed = (level: number) => (level > 0 ? `+${level}` : String(level));

// low, normal or high; any other stored level as its number.
export function levelName(level: number, words: Record<string, number> = WORDS): string {
  return Object.keys(words).find((word) => words[word] === level) ?? signed(level);
}

// The choices a level offers: High, Normal, Low, and the stored number when it is none of them.
export function levelChoices(saved: number, words: Record<string, number> = WORDS): [number, string][] {
  const named: [number, string][] = [["high", "High"], ["normal", "Normal"], ["low", "Low"]]
    .filter(([word]) => word in words).map(([word, text]) => [words[word], text]);
  return named.some(([level]) => level === saved) ? named : [...named, [saved, signed(saved)]];
}

// What to send so the stored rules become the edited ones: only what differs. Maps merge entry
// by entry on the server, and a level of 0 removes one.
export function changeOf(saved: Rules, draft: Rules): Partial<Rules> {
  const change: Partial<Rules> = {};
  for (const map of LEVEL_MAPS) {
    const entries: Record<string, number> = {};
    for (const name of new Set([...Object.keys(saved[map]), ...Object.keys(draft[map])])) {
      const was = saved[map][name] ?? 0, now = draft[map][name] ?? 0;
      if (was !== now) entries[name] = now;
    }
    if (Object.keys(entries).length) change[map] = entries;
  }
  if (saved.github !== draft.github) change.github = draft.github;
  if (saved.aging_min !== draft.aging_min) change.aging_min = draft.aging_min;
  if (saved.shortest_first !== draft.shortest_first) change.shortest_first = draft.shortest_first;
  if (saved.fair_turns !== draft.fair_turns) change.fair_turns = draft.fair_turns;
  return change;
}

export const isDirty = (saved: Rules, draft: Rules) => Object.keys(changeOf(saved, draft)).length > 0;
export const isDefault = (body: RulesBody) => !isDirty(body.defaults, body.rules);

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
  if (name in taken) return "It is already in the list.";
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
