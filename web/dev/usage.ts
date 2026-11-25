// Stand-in answers for `/api/usage` and `/api/usage/<job_id>` (docs/interfaces-m2.md): what
// jobs used, in every shape the Usage page and a job's page show. build-1 has nine jobs, one
// too short for cores; build-2 one job that also ran on build-1 and one never measured; a third
// machine (MULEBOX_MOCK_MACHINES=3 or more) stands for a Mac. The names are examples.

import type { MockJob } from "./fixtures.ts";

const GB = 1e9;
const now = () => Date.now() / 1000;
interface Size { cores: number; memory: number }
const SIZES: Size[] = [{ cores: 8, memory: 16 * GB }, { cores: 4, memory: 8 * GB }, { cores: 10, memory: 32 * GB }];
const sizeOf = (index: number) => SIZES[index] ?? SIZES[0];

type Pair = [number, number] | null;   // the median and the highest peak: cores; GB
interface Row { project: string; job: string; kind: "job" | "runner"; on: number; runs: number; c: Pair; m: Pair; failed?: boolean }
const ROWS: Row[] = [
  { project: "example-org__example-app", job: "test", kind: "runner", on: 1, runs: 20, c: [7.2, 7.8], m: [5.6, 6.3] },
  { project: "example-org__example-shop", job: "build", kind: "runner", on: 1, runs: 20, c: [3.6, 7.4], m: [2.4, 4.8] },
  { project: "example-app", job: "check", kind: "job", on: 1, runs: 20, c: [5.4, 6.1], m: [3.1, 3.5] },
  { project: "example-org__example-api", job: "e2e", kind: "runner", on: 1, runs: 12, c: [4.8, 6.6], m: [7.9, 9.4] },
  { project: "example-api", job: "check", kind: "job", on: 1, runs: 18, c: [3.2, 4.4], m: [2.2, 2.9] },
  { project: "example-shop", job: "check", kind: "job", on: 1, runs: 20, c: [2.1, 2.6], m: [1.6, 1.9] },
  { project: "example-site", job: "unit", kind: "job", on: 1, runs: 20, c: [1.4, 1.8], m: [0.7, 0.9] },
  { project: "example-app", job: "lint", kind: "job", on: 1, runs: 20, c: [0.9, 1.2], m: [0.412, 0.538] },
  { project: "example-site", job: "format", kind: "job", on: 1, runs: 20, c: null, m: [0.148, 0.212] },
  { project: "example-storefront-checkout", job: "check-and-integration", kind: "job", on: 1, runs: 3, c: [2.0, 2.2], m: [1.1, 1.3], failed: true },
  { project: "example-app", job: "check", kind: "job", on: 2, runs: 4, c: [3.4, 3.9], m: [3.0, 3.4] },
  { project: "example-legacy", job: "check", kind: "job", on: 2, runs: 6, c: null, m: null },
  { project: "example-org__example-ios", job: "build", kind: "runner", on: 3, runs: 9, c: [7.1, 9.3], m: [6.0, 7.7] },
  { project: "example-ios", job: "test", kind: "job", on: 3, runs: 14, c: [6.3, 8.2], m: [5.2, 6.8] },
];

const spread = (pair: Pair, scale = 1) => (pair ? { median: pair[0] * scale, max: pair[1] * scale } : null);
const HALF = 0.5 * GB;

// One entry per project, job and kind: its runs on every node it ran on, taken together.
function group(rows: Row[]) {
  const first = rows[0], measured = rows.filter((row) => row.m);
  const cores = rows.filter((row) => row.c).map((row) => row.c as [number, number]);
  const memory = measured.map((row) => row.m as [number, number]);
  const top = (pairs: [number, number][]): Pair => (pairs.length ? [Math.max(...pairs.map((p) => p[0])), Math.max(...pairs.map((p) => p[1]))] : null);
  const c = spread(top(cores)), m = spread(top(memory), GB);
  const counted = (list: Row[]) => list.reduce((sum, row) => sum + row.runs, 0);
  return {
    project: first.project, job: first.job, kind: first.kind, runs: counted(rows), measured: counted(measured),
    not_measured: counted(rows) - counted(measured), no_cores: counted(measured.filter((row) => !row.c)), cores: c, memory: m,
    fits: c || m ? { cores: c ? Math.ceil(c.max) : null, memory: m ? Math.ceil(m.max / HALF) * HALF : null } : null,
    machines: [...new Set(rows.map((row) => `build-${row.on}`))].sort(), last_finished_at: now() - 600,
  };
}

export function usageBody(names: string[], query: URLSearchParams) {
  const all = query.get("all") === "1", has = (key: string, value: string) => !query.get(key) || query.get(key) === value;
  const rows = ROWS.filter((row) => names.includes(`build-${row.on}`) && (all || !row.failed)
    && has("project", row.project) && has("job", row.job) && has("kind", row.kind) && has("worker", `build-${row.on}`));
  const groups = new Map<string, Row[]>();
  rows.forEach((row) => groups.set(`${row.kind}/${row.project}/${row.job}`, [...(groups.get(`${row.kind}/${row.project}/${row.job}`) ?? []), row]));
  return { machines: sizes(names), jobs: [...groups.values()].map(group), runs: Number(query.get("runs") ?? 20), all };
}

const sizes = (names: string[]) => Object.fromEntries(names.map((name, index) => [name, sizeOf(index)]));

// One run, from its row in the stand-in's queue: a running job's peaks grow with its age; the
// finished ones are a full measurement, one too short for cores, and one never measured.
export function runBody(names: string[], row: MockJob) {
  const started = row.started_at as number | null, finished = row.state === "finished", ci = row.kind === "runner";
  const ran = !started ? null : finished ? (row.duration_s as number | undefined) ?? 200 : now() - started;
  const samples = ran === null ? 0 : Math.floor(ran / 10);
  const step = (row.doing as { step?: string } | undefined)?.step ?? "Build site";
  const full = { peak_cores: ci ? 5.9 : 6.1, peak_cores_stage: ci ? step : "command", peak_memory: (ci ? 7.4 : 3.5) * GB,
                 peak_memory_stage: ci ? "Install dependencies" : "setup", cpu_s: (ci ? 3.1 : 3.5) * (ran ?? 0), samples };
  const usage = ran === null || (finished && ci) ? {}
    : finished && row.outcome === "failed" ? { peak_cores: null, peak_cores_stage: null, peak_memory: 0.212 * GB, peak_memory_stage: "command", cpu_s: 4, samples: 1 }
      : full;
  const cpu = (usage as { cpu_s?: number }).cpu_s, cores = (usage as { peak_cores?: number | null }).peak_cores;
  return {
    machines: sizes(names),
    run: { job_id: row.job_id, project: row.project, job: row.job, kind: row.kind, worker: row.worker, state: row.state,
           outcome: row.outcome, run_s: ran, usage, average_cores: cpu && cores && ran ? cpu / ran : null },
  };
}
