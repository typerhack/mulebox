// A node's own checks on the page, without React (docs/design.md, A node that rests). The
// user's pick of 2026-11-25: the strip says a problem once, with its fix and Check now; the
// Machines box and a waiting job carry the state's icon and a few words; the Machines page a
// second row under the node; the settings window a Health tab with every check and min_free.

import { ago } from "./format";
import type { Job, Machine } from "./types";

// A node's own checks as it reports them (mulebox/common/node_health.py): absent from a node
// older than 1.41, and `ran`, `checked_at`, `next_at` and `min_free` from one older than 1.42.
export interface HealthProblem { check: string; message: string; fix: string; since: number }
export interface Health {
  resting: boolean;
  until?: number | null;
  problems: HealthProblem[];
  withheld: string[];
  round?: number;
  answers?: number;
  ran?: string[];
  checked_at?: number;
  next_at?: number;
  min_free?: number;
}

interface Check { name: string; short: string; passes: string }
// Every check a node runs, in its own order (mulebox/common/node_health.py, CHECKS).
export const CHECKS: Record<string, Check> = {
  disk: { name: "Disk space", short: "Low disk", passes: "more free than its least free space" },
  roots: { name: "Folders", short: "Folders not writable", passes: "its folders can be written" },
  git: { name: "git", short: "No git", passes: "runs" },
  executor: { name: "Job runner", short: "No job runner", passes: "systemd's user manager answers" },
  docker: { name: "Docker", short: "No Docker", passes: "answers" },
  xcode: { name: "Xcode", short: "No Xcode", passes: "xcodebuild runs" },
  streak: { name: "Starts", short: "Failed starts", passes: "no jobs in a row that could not start" },
};
const ORDER = Object.keys(CHECKS);
const WITHHOLDS: Record<string, string> = { docker: "Docker", xcode: "Xcode" };

// mulebox/common/disk.py: low under 10 GB free or a tenth of the disk, whichever is more.
export const LOW_FREE = 10_000_000_000;
export const LOW_SHARE = 0.1;

export const healthOf = (m: Machine): Health | null => (m.state === "offline" ? null : m.health ?? null);
export const problemsOf = (m: Machine): HealthProblem[] => healthOf(m)?.problems ?? [];
export const isSick = (m: Machine) => problemsOf(m).length > 0;
export const isResting = (m: Machine) => m.state === "resting";
export const shortOf = (p: HealthProblem) => CHECKS[p.check]?.short ?? p.check;

// The node's own sentence, as the API gives it lower-case, as a sentence of the page.
export function sentence(text: string): string {
  const trimmed = text.trim().replace(/[.;]$/, "");
  return trimmed ? `${trimmed[0].toUpperCase()}${trimmed.slice(1)}.` : "";
}

// "build-1 is resting and takes no job", "build-2 takes no Docker jobs".
export function headline(m: Machine): string {
  if (isResting(m)) return `${m.name} is resting and takes no job`;
  const parts = [...new Set(problemsOf(m).map((p) => WITHHOLDS[p.check]).filter(Boolean))];
  return `${m.name} takes no ${parts.length ? parts.join(" or ") : "new"} jobs`;
}

// Four words on a waiting job held by a node's checks; the strip has the rest.
export function heldWords(job: Job, machines: Machine[]): string | null {
  const held = machines.filter((m) => job.held_by?.includes(m.name) && isSick(m));
  if (!held.length) return null;
  if (held.length > 1) return `${held.map((m) => m.name).join(", ")} hold it back`;
  const [node] = held, first = problemsOf(node)[0];
  return isResting(node) ? `${node.name} is resting: ${shortOf(first).toLowerCase()}` : headline(node);
}

function inWords(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return s < 90 ? `${s} s` : `${Math.round(s / 60)} min`;
}

// "checked 20 s ago, again in 40 s"; empty for a node older than 1.42.
export function checkedText(health: Health | null, now: number): string {
  if (!health?.checked_at) return "";
  const when = ago(health.checked_at, now);
  const next = health.next_at && health.next_at > now ? `, again in ${inWords(health.next_at - now)}` : "";
  return `checked ${when === "now" ? "just now" : when}${next}`;
}

// A node under 10% free (or 10 GB), long before it rests: its cleanup runs first.
export function lowDisk(m: Machine): { free: number; total: number | null } | null {
  const free = m.disk_free;
  if (m.state === "offline" || typeof free !== "number") return null;
  if (problemsOf(m).some((p) => p.check === "disk")) return null;  // the strip says the rest
  const line = Math.max(LOW_FREE, LOW_SHARE * (m.disk_total ?? 0));
  return free < line ? { free, total: m.disk_total ?? null } : null;
}

// The Health tab's list: every check the node runs, failing ones with their problem.
export interface CheckRow { check: string; name: string; passes: string; problem?: HealthProblem }
export function checkRows(health: Health | null): CheckRow[] {
  if (!health) return [];
  const failing = new Map(health.problems.map((p) => [p.check, p]));
  const ran = new Set([...(health.ran ?? []), ...failing.keys(), "streak"]);
  return ORDER.filter((check) => ran.has(check))
    .map((check) => ({ check, ...CHECKS[check], problem: failing.get(check) }));
}
