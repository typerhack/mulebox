// The stand-in for `GET /api/history` (docs/interfaces-m2.md): the made-up finished jobs,
// repeated into enough rows to page through, with the same filters, search and 400s as the
// real route (mulebox/dashboard/history_query.py). It answers after a short random wait, so a
// superseded request can come back late, as it can on a real network.

import type { MockJob } from "./fixtures.ts";

const GROUPS = ["project", "job", "client", "worker", "kind"];
const KINDS = ["job", "runner"];
const RESULTS: Record<string, string[]> = {
  passed: ["passed"], failed: ["failed", "timed_out", "interrupted"], cancelled: ["cancelled", "stuck"],
};
const BRANCHES = ["main", "fix/timeouts", "feature/login", "feature/50%-off", "release/1.2"];
const PROJECTS = ["example-app", "example-api", "example-web"];

// 120 rows a minute apart, newest first, varied from the fixtures' finished jobs.
export function historyRows(recent: MockJob[], now: number): MockJob[] {
  return Array.from({ length: 120 }, (_, i) => {
    const base = recent[i % recent.length];
    const finished = now - 700 - 60 * i;
    const own = base.kind === "job" && i >= recent.length;
    return {
      ...base, job_id: `${base.job_id}${String(i).padStart(3, "0")}`, finished_at: finished, started_at: finished - 200,
      ...(own ? { project: PROJECTS[i % PROJECTS.length], branch: BRANCHES[i % BRANCHES.length] } : {}),
    };
  });
}

export function answerHistory(rows: MockJob[], query: URLSearchParams): { status: number; body: unknown } {
  const kind = query.get("kind"), result = query.get("result"), q = (query.get("q") ?? "").trim().toLowerCase();
  if (kind && !KINDS.includes(kind)) return { status: 400, body: `kind must be one of ${KINDS.join(", ")}` };
  if (result && !RESULTS[result]) return { status: 400, body: `result must be one of ${Object.keys(RESULTS).join(", ")}` };
  const before = query.get("before") ? Number(query.get("before")) : null;
  const limit = Math.max(1, Math.min(200, Number(query.get("limit") ?? 50)));
  const kept = rows.filter((row) => KINDS.includes(row.kind)
    && GROUPS.every((name) => !query.get(name) || row[name] === query.get(name))
    && (!result || RESULTS[result].includes(String(row.shown_state)))
    && (!q || ["project", "job", "branch"].some((name) => String(row[name] ?? "").toLowerCase().includes(q))));
  const page = kept.filter((row) => before === null || Number(row.finished_at) < before).slice(0, limit);
  const more = page.length === limit;
  const choices = Object.fromEntries(GROUPS.map((name) => [name,
    [...new Set(rows.filter((row) => KINDS.includes(row.kind)).map((row) => row[name]).filter(Boolean))].sort()]));
  return { status: 200, body: { jobs: page, next_before: more ? page.at(-1)?.finished_at : null,
                                ...(before === null ? { choices } : {}) } };
}
