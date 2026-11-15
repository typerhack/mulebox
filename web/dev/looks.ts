// The `looks` scene for `npm run dev` (MULEBOX_MOCK_SCENE=looks): a running job in each
// verdict of "A job that looks stuck" (docs/design.md), with the coordinator's sentences:
// working (nothing shown), slow, waiting on purpose, asking for input and stuck, and a job
// with no verdict at all. One waits behind them.

import { job, type MockJob } from "./fixtures.ts";

const now = () => Date.now() / 1000;
type More = Record<string, unknown>;
const MB = 1000 ** 2;

const run = (id: string, worker: string, age: number, more: More) =>
  job(id, { state: "running", worker, started_at: now() - age, elapsed_s: age, usual_s: 240, section: "running",
            doing: { stage: "command", cpu_pct: 0 }, ...more });
// `since` moves with the clock, so the quiet time reads the same on every load and counts on.
const quiet = (verdict: string, seconds: number, stage: string, last_line: string, text: string) =>
  ({ verdict, text, stage, last_line, limit_s: 120, since: now() - seconds, quiet_s: seconds });

export function looksScene() {
  const running = [
    run("A41F9C", "build-1", 134, { branch: "feature/login-form", doing: { stage: "command", cpu_pct: 320 },
      looks: { verdict: "working", text: "", stage: "command", last_line: "vitest run", limit_s: 120 } }),
    run("B0E6F5", "build-1", 362, { project: "example-shop", branch: "fix/cart-total", client_os: "Linux", usual_s: 180,
      doing: { stage: "toolchain", cpu_pct: 0, download: { what: "tool", name: "node-v22.tar.xz", done_bytes: 41 * MB,
        total_bytes: 300 * MB, rate_bytes_s: 12_000, as_of_s: 2, net_bytes_s: 12_000, net_scope: "job", quiet_s: 0, stalled: false } },
      looks: { verdict: "slow", stage: "toolchain", last_line: "Downloading node-v22.tar.xz", limit_s: 120,
               text: "Downloading slowly: 12 KB/s, 41 MB of 300 MB of node-v22.tar.xz. Nothing else has moved for 3m." } }),
    run("C07E55", "build-1", 581, { project: "example-api", job: "integration", branch: "main", usual_s: 720,
      looks: quiet("waiting", 240, "command", "Retrying in 60 s (attempt 3 of 5)",
                   "Quiet for 4m, but its last line says it is waiting: \"Retrying in 60 s (attempt 3 of 5)\".") }),
    run("D2A771", "build-2", 172, { project: "example-site", job: "build", branch: "chore/scaffold", client_os: "Linux", usual_s: 60,
      doing: { stage: "setup", cpu_pct: 0 },
      looks: quiet("asking", 150, "setup", "Overwrite existing files? [y/N]",
                   "Waiting for an answer it will never get, for 2m 30s: \"Overwrite existing files? [y/N]\". Cancel it and make the command non-interactive.") }),
    run("E93B21", "build-2", 331, { job: "migrate", branch: "feature/orders-table", usual_s: 40,
      looks: quiet("stuck", 310, "command", "Running migrations...",
                   "Looks stuck: no output, no CPU, no I/O for 5m 10s in stage command. Last line: \"Running migrations...\". Look at its log or cancel it.") }),
    run("F5C310", "build-2", 20, { project: "example-worker", branch: "chore/deps", doing: { stage: "images", cpu_pct: 90 } }),
  ];
  const queued: MockJob[] = [job("W00001", { section: "queued", can_run_on: ["build-1", "build-2"], needs: [], project: "docs-site", job: "build" })];
  return { running, queued, machines: { "build-1": { slots: 3, state: "busy" }, "build-2": { slots: 3, state: "busy" } } };
}
