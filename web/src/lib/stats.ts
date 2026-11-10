// The Statistics page's sums and words. The numbers are `/api/stats`, the same module as
// `mulebox stats` (coordinator/stats.py); the page only asks and draws. "Today" is this
// browser's own day: it sends its local midnight, and the last 14 midnights for the chart.

import { getJson } from "./api";
import { duration } from "./format";
import type { StatDay, StatRow, Stats } from "./types";

export const DAYS = 14, LIMIT = 8;
export type Dim = "project" | "kind" | "client" | "worker" | "job";
export const DIMS: [Dim, string][] = [["project", "Project"], ["kind", "Type"], ["client", "Source"],
                                      ["worker", "Machine"], ["job", "Job name"]];
export const FILTERS: [Dim, string, string][] = [["kind", "Type", "All types"], ["project", "Project", "All projects"],
                                                 ["client", "Source", "All sources"], ["worker", "Machine", "All machines"]];
// Series: mulebox's own jobs and GitHub runs keep one colour each everywhere on the page.
export const SERIES: { kind: string; name: string; tone: string }[] = [
  { kind: "job", name: "mulebox jobs", tone: "bg-chart-1" },
  { kind: "runner", name: "GitHub Actions", tone: "bg-chart-2" },
];

export const isGithub = (key: string) => key === "runner" || key === "github";
export const int = (n: number) => Math.round(n).toLocaleString("en-US");
export const runsText = (n: number) => `${int(n)} ${n === 1 ? "run" : "runs"}`;
export const share = (part: number, whole: number) => (whole > 0
  ? `${part / whole >= 0.1 ? Math.round((100 * part) / whole) : Math.round((1000 * part) / whole) / 10}%` : "0%");
export function average(row: StatRow): string {
  const finished = row.runs - row.running;
  return finished > 0 ? duration((row.seconds - row.running_seconds) / finished) : "-";
}

export function label(dim: Dim, key: string | null): string {
  if (dim === "kind") return SERIES.find((series) => series.kind === key)?.name ?? String(key);
  if (dim === "client") return key === "github" ? "GitHub" : String(key ?? "-").replace(/\.local$/, "");
  return String(key ?? "-").replace("__", "/");
}
// The series colour of a row, when its dimension says which series it is.
export const toneOf = (dim: Dim, key: string) =>
  (dim === "kind" || dim === "client" ? SERIES[isGithub(key) ? 1 : 0].tone : "bg-meter-fill");

export function midnights(count: number, now = new Date()): number[] {
  return Array.from({ length: count }, (_, i) =>
    new Date(now.getFullYear(), now.getMonth(), now.getDate() - (count - 1 - i)).getTime() / 1000);
}

export async function askStats(filters: Partial<Record<Dim, string>>): Promise<{ today: Stats; all: Stats }> {
  const days = midnights(DAYS);
  const chosen = Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
  const query = (extra: Record<string, string>) => new URLSearchParams({ ...chosen, ...extra });
  const [today, all] = await Promise.all([
    getJson<Stats>(`/api/stats?${query({ from: String(days.at(-1)) })}`),
    getJson<Stats>(`/api/stats?${query({ day_starts: days.join(",") })}`),
  ]);
  return { today, all };
}

export const dayName = (from: number, options: Intl.DateTimeFormatOptions) =>
  new Date(from * 1000).toLocaleDateString("en-GB", options);

// The day chart's scale: two grid steps that hold the tallest day.
export function dayScale(days: StatDay[], shown: string[]): { step: number; max: number; value: (d: StatDay) => number } {
  const value = (d: StatDay) => shown.reduce((sum, kind) => sum + (d.kinds?.[kind] ?? 0), 0);
  const top = Math.max(...days.map(value), 1) / 3600;
  const step = [0.25, 0.5, 1, 2, 3, 4, 6, 8, 12, 24, 48].find((s) => s * 2 >= top) ?? Math.ceil(top / 2);
  return { step, max: step * 2 * 3600, value };
}
export const hourTick = (hours: number) => (hours > 0 && hours < 1 ? `${hours * 60}m` : `${hours}h`);
