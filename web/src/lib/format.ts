// Small display helpers shared by the views. Same duration format as the terminal view.

import type { Job } from "./types";

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "-";
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  if (h) return `${h}h ${pad(m)}m`;
  if (m) return `${m}m ${pad(s)}s`;
  return `${s}s`;
}

// A length from past runs, to the minute past one: it is a rough figure.
export function roughly(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  const minutes = Math.round(total / 60), h = Math.floor(minutes / 60), m = minutes % 60;
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
}

export function bytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = n, unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export const rate = (kibS: number) => `${bytes(kibS * 1024)}/s`;
export const percent = (value: number) => `${value.toFixed(0)}%`;

export function clock(seconds: number | null | undefined): string {
  if (!seconds) return "-";
  return new Date(seconds * 1000).toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

// How long ago, in words short enough for a table: "now", "14 min ago", "2 h ago".
export function ago(seconds: number | null | undefined, now: number): string {
  if (!seconds) return "never";
  const gone = Math.max(0, now - seconds);
  if (gone < 20) return "now";
  if (gone < 90) return `${Math.round(gone)} s ago`;
  if (gone < 5400) return `${Math.round(gone / 60)} min ago`;
  if (gone < 129600) return `${Math.round(gone / 3600)} h ago`;
  return `${Math.round(gone / 86400)} days ago`;
}

// A day short enough for a row: "3 Oct", with its year once that is not this one.
export function day(seconds: number, now: number): string {
  const date = new Date(seconds * 1000), sameYear = date.getFullYear() === new Date(now * 1000).getFullYear();
  return date.toLocaleDateString([], { day: "numeric", month: "short", ...(sameYear ? {} : { year: "numeric" }) });
}

// A link target only when it is really http(s): stored values never become script URLs.
export function safeUrl(text: string | null | undefined): string | null {
  if (!text) return null;
  try {
    const url = new URL(text);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

// A runner reservation only holds a slot for GitHub Actions, so it is named by its repository,
// without the owner: the project of one is `owner__repo` (coordinator/reservations.py).
export const isCI = (job: Pick<Job, "kind">) => job.kind === "runner";
export const repository = (job: Pick<Job, "project">) => (job.project ?? "-").replace("__", "/");

// [project, job name]: the two halves of a job's display name; an upgrade has one.
export function nameParts(job: Job): [string, string | null] {
  if (job.kind === "upgrade") return [`mulebox upgrade to ${job.branch ?? "?"}`, null];
  if (isCI(job)) return [(job.project ?? "-").split("__").pop() ?? "-", job.job ?? "CI"];
  return [job.project ?? "-", job.job ?? "-"];
}
export const jobName = (job: Job) => nameParts(job).filter(Boolean).join(" / ");

// The end of a job's id: ids made close in time start alike, their ends never do.
export const shortId = (job: Pick<Job, "job_id">) => job.job_id.slice(-6);
export const jobHref = (job: Pick<Job, "job_id">) => `#/job/${encodeURIComponent(job.job_id)}`;

export const stateOf = (job: Job) => job.shown_state ?? job.outcome ?? job.state;
export const words = (state: string | null | undefined) => String(state ?? "unknown").replaceAll("_", " ");
export const stateText = (state: string | null | undefined) =>
  words(state).replace(/^./, (first) => first.toUpperCase());

export const WAITING = new Set(["uploading", "queued"]);
export const RUNNING = new Set(["starting", "running"]);
export const FAILED = new Set(["failed", "timed_out", "interrupted"]);

export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
export const timeLeft = (seconds: number) => `${duration(seconds)} left`;

// The job among `jobs` that stops first, and how many wait for an answer.
export function soonest(jobs: Job[]): { job: Job | null; count: number } {
  const alone = jobs.filter((job) => job.question);
  alone.sort((a, b) => (a.question?.left_s ?? 0) - (b.question?.left_s ?? 0));
  return { job: alone[0] ?? null, count: alone.length };
}

// `a `b` c` -> text and code parts, so a command reads as one.
export function codeParts(text: string): { text: string; code: boolean }[] {
  return text.split("`").map((part, index) => ({ text: part, code: index % 2 === 1 }))
    .filter((part) => part.text !== "");
}
