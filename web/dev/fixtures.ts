// Made-up data for `npm run dev` without a dashboard: a queue with every kind of row, two,
// five or twenty machines (MULEBOX_MOCK_MACHINES), other queues (dev/scenes.ts), a job with stages and a GitHub run. The
// shapes are the API's (docs/interfaces-m2.md); the names are examples.

const now = () => Date.now() / 1000;
const COUNT = Number(process.env.MULEBOX_MOCK_MACHINES ?? 2);
const OFFERS = [["docker", "node 22", "python 3.12"], ["docker", "playwright"], ["docker", "node 22"]];

export interface MockJob { [key: string]: unknown; job_id: string; state: string; kind: string; position?: number | null }

export const job = (id: string, more: Record<string, unknown>): MockJob => ({
  job_id: `job-01EXAMPLE${id}`, project: "example-app", job: "check", branch: "main", client: "laptop.local",
  client_os: "macOS", state: "queued", outcome: null, exit_code: null, worker: null, kind: "job", position: null,
  paused: false, boost: false, cancel_requested: false, pinned_worker: null, run_url: null,
  created_at: now() - 400, started_at: null, finished_at: null, ...more,
});

export function makeQueue() {
  const running: MockJob[] = [
    job("A41F9C", { state: "running", worker: "build-1", branch: "feature/login", boost: true, started_at: now() - 134,
                    elapsed_s: 134, usual_s: 240, doing: { stage: "command", cpu_pct: 320 }, section: "running" }),
    job("C07E55", { state: "running", worker: "build-1", kind: "runner", project: "example-org__docs-site", job: "build",
                    client: "github", client_os: null, pinned_worker: "build-1", started_at: now() - 41, elapsed_s: 41,
                    usual_s: 90, doing: { step: "Build site", cpu_pct: 110 }, section: "running",
                    run_url: "https://github.com/example-org/docs-site/actions/runs/1" }),
    job("E93B21", { state: "running", worker: "build-1", project: "example-api", job: "test", branch: "fix/timeouts",
                    client_os: "Linux", paused: true, started_at: now() - 362, elapsed_s: 362, usual_s: 300,
                    doing: { stage: "services", cpu_pct: 0 }, section: "running",
                    question: { reason: "no output and no CPU for 20 min", left_s: 540 } }),
  ];
  const wait = (id: string, position: number, more: Record<string, unknown>) =>
    job(id, { position, elapsed_s: 30 * position, section: "queued", can_run_on: ["build-1", "build-2"], needs: [], ...more });
  const queued: MockJob[] = [
    wait("W00001", 1, { branch: "feature/login", branch_busy: "job-01EXAMPLEA41F9C" }),
    wait("W00002", 2, { project: "example-worker", branch: "chore/deps" }),
    wait("W00003", 3, { project: "docs-site", job: "build", branch: "draft/pricing", client_os: "Linux", paused: true,
                        waiting_for: "The project docs-site is paused. Resume it with `mulebox project resume docs-site`" }),
    wait("W00004", 4, { kind: "runner", project: "example-org__example-api", job: "CI", client: "github", client_os: null,
                        pinned_worker: "build-2", can_run_on: undefined,
                        run_url: "https://github.com/example-org/example-api/actions/runs/2" }),
    wait("W00005", 5, { job: "e2e", branch: "feature/checkout", can_run_on: [], needs: ["gpu"],
                        waiting_for: "Needs gpu, which no machine offers" }),
  ];
  const done = (id: string, outcome: string, more: Record<string, unknown> = {}) =>
    job(id, { state: "finished", outcome, shown_state: outcome, worker: "build-1", started_at: now() - 900,
              finished_at: now() - 700, elapsed_s: 200, duration_s: 200, exit_code: outcome === "passed" ? 0 : 1,
              section: "recent", ...more });
  const recent: MockJob[] = [
    done("D00001", "passed"),
    done("D00002", "failed", { project: "example-api", job: "test", branch: "fix/timeouts" }),
    done("D00003", "failed", { kind: "runner", project: "example-org__docs-site", job: "build", client: "github",
                               client_os: null, exit_code: null,
                               ci_result: { outcome: "failed", step: "Build site", message: "Process completed with exit code 1." } }),
    done("D00004", "cancelled", { job: "e2e", branch: "feature/login", exit_code: null }),
    done("D00005", "passed", { kind: "upgrade", branch: "0.96.0", project: null, job: null }),
  ];
  return { running, queued, recent };
}

// `set` changes a machine by name (a scene's slots and state, dev/scenes.ts).
export function makeMachines(queue: ReturnType<typeof makeQueue>, set: Record<string, { slots?: number; state?: string }> = {}) {
  return Array.from({ length: COUNT }, (_, index) => {
    const n = index + 1, name = `build-${n}`;
    const jobs = queue.running.filter((row) => row.worker === name);
    const busy = n === 1 || n === 4 || n === 7;
    const slots = set[name]?.slots ?? (n === 1 ? 3 : 2 + (n % 3));
    const state = set[name]?.state ?? (n === 2 || n === 13 ? "offline" : n === 3 ? "draining" : n === 1 ? "busy" : "available");
    const offline = state === "offline";
    return {
      name, host: n === 1, version: n === 5 ? "0.95.4" : "0.95.5", slots, capabilities: OFFERS[index % OFFERS.length], state,
      free_slots: offline ? 0 : Math.max(0, slots - jobs.length), last_seen: offline ? now() - 840 : now(),
      cpu_pct: offline ? null : n === 1 ? 41 : busy ? 77 : 3 + (n * 7) % 9,
      mem_pct: offline ? null : n === 1 ? 62 : 15 + (n * 5) % 40, cores: n === 1 ? CORES : 8,
      net_in_kib_s: offline ? null : n === 1 ? 3400 : 12 + n, net_out_kib_s: offline ? null : n === 1 ? 212 : 3 + n, jobs,
    };
  });
}

// MULEBOX_MOCK_CORES=32 shows a machine with many cores (the CPU box's compact view).
const CORES = Number(process.env.MULEBOX_MOCK_CORES) || 8;

export function sample(t: number, seed = 0) {
  const wave = (k: number) => 40 + 30 * Math.sin(t / 17 + k + seed) + 12 * Math.sin(t / 3 + k * 2);
  const gib = 1024 ** 3;
  return {
    t, cpu: Array.from({ length: CORES }, (_, k) => Math.max(1, Math.min(99, k % 5 ? wave(k) / 6 : wave(k)))),
    memory: { total: 32 * gib, used: (18 + 2 * Math.sin(t / 40)) * gib, available: 12 * gib },
    swap: { total: 8 * gib, used: 0 }, jobs_memory: (11 + Math.sin(t / 40)) * gib, docker_disk: 65 * gib,
    self: { cpu: 0.5, rss: 44 * 1024 ** 2 }, docker: 6, viewers: 1,
    disk: [{ roots: ["cache", "jobs", "projects"], total: 256 * gib, used: 215 * gib, free: 41 * gib }],
  };
}

export function detail(row: MockJob) {
  const start = (row.started_at as number | null) ?? now();
  const lengths: [string, number][] = [["prepare", 2], ["toolchain", 1], ["images", 16], ["services", 9], ["setup", 12], ["command", 94]];
  let at = start;
  const finished = row.state === "finished";
  const steps = row.kind !== "job" || row.state === "queued" ? [] : lengths.map(([stage, length], index) => {
    const from = at;
    at += length;
    const open = !finished && index === lengths.length - 1;
    return { seq: index, stage, started_at: from, finished_at: open ? null : at, bytes_downloaded: stage === "images" ? 396e6 : null,
             failing_line: row.outcome === "failed" && index === lengths.length - 1 ? "FAIL src/cart/totals.test.ts" : null };
  });
  return {
    ...row, base_commit: "9f2c41d07a3e5b6c", timeout_min: 20, toolchain: {}, command: "pnpm run check",
    duration_s: finished ? 200 : null, steps, failed_stage: row.outcome === "failed" && row.kind === "job" ? "command" : null,
    usual: row.kind === "job" ? { runs: 9, job_s: 240, stages: { prepare: 3, toolchain: 1, images: 18, services: 10, setup: 14, command: 190 } } : null,
    activity: finished ? null : { output_idle_s: 45, job_cpu_pct: 320 }, log_size: 1200,
  };
}

export const AGENT_LOG = ["mulebox: job on build-1, branch feature/login", "prepare: 3 files changed, sent 1.4 KiB",
  "images: example-app-web built, 2 pulled from cache", "services: db healthy, cache healthy", "$ pnpm run check",
  "tsc --noEmit: no errors", "eslint: 412 files, no problems", "vitest run", " PASS  src/login/session.test.ts (41 tests)"];
// A run's steps as the worker writes them (runners/live_log.py), with times from 41 s ago to now.
const at = (ago: number) => new Date(Date.now() - ago * 1000).toISOString().replace(/\.\d+Z$/, "Z");
export const CI_LOG = [
  `mulebox: step at ${at(41)}: Set up job`, `mulebox: step passed at ${at(39)}: Set up job`,
  `mulebox: step at ${at(39)}: Check out`, `mulebox: step passed at ${at(36)}: Check out`,
  `mulebox: step at ${at(36)}: Use Node 22`, `mulebox: step skipped at ${at(36)}: Use Node 22`,
  `mulebox: step at ${at(36)}: Install dependencies`, `mulebox: step passed at ${at(22)}: Install dependencies`,
  `mulebox: step at ${at(22)}: Build site`, "--- output of Install dependencies", "added 412 packages in 14s",
  "--- output of Build site", "$ pnpm run build", "vite building for production", "transforming (318) src/pages/pricing.mdx"];

export function stats(days: number[]) {
  const row = (key: string, seconds: number, runs: number) => ({ key, seconds, runs, running: 0, running_seconds: 0, unknown: 0 });
  return {
    from: days.at(-1) ?? now() - 3600, first_started_at: now() - 86400 * 40,
    total: { ...row("total", 138600, 1104), running: 2, running_seconds: 300, unknown: 3 },
    by: {
      kind: [row("job", 107400, 921), row("runner", 31200, 183)],
      project: ["example-app", "example-api", "docs-site", "example-worker", "example-org__docs-site", "a", "b", "c", "d", "e"]
        .map((key, index) => row(key, 60000 / (index + 1), 300 - index * 25)),
      client: [row("laptop.local", 107400, 921), row("github", 31200, 183)],
      worker: [row("build-1", 120000, 1000), row("build-2", 18600, 104)],
      job: [row("check", 90000, 700), row("test", 30000, 300), row("build", 18600, 104)],
    },
    days: days.map((from, index) => ({ from, runs: 20 + index * 3, kinds: { job: 3000 + index * 900, runner: index % 3 ? 1500 + index * 200 : 0 } })),
    choices: { kind: ["job", "runner"], project: ["example-app", "example-api", "docs-site"], client: ["laptop.local", "github"],
               worker: ["build-1", "build-2"] },
  };
}
