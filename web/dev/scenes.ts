// Other queues for `npm run dev`, picked with MULEBOX_MOCK_SCENE, to see the Jobs box's lanes
// in the shapes the default queue does not have:
//   split: build-1 runs 2 with 1 waiting for it; build-2 runs 1 with 8 waiting for it.
//   wide:  build-1 has 4 slots, all running, 2 waiting for it (long names, a paused job, a
//          GitHub run); build-2 runs 2 with 1 waiting; 2 jobs for the next free machine and
//          one no machine fits.
//   downloads: the Down meter in each state, on agent jobs and GitHub runs: a known total, no
//          total, no bytes for a while (each), the node's traffic only, a long name, a size alone,
//          and a GitHub run frozen and boosted (the narrowest card).

import { job, type MockJob } from "./fixtures.ts";

const now = () => Date.now() / 1000;
type More = Record<string, unknown>;

const run = (id: string, worker: string, age: number, cpu: number, more: More = {}) =>
  job(id, { state: "running", worker, started_at: now() - age, elapsed_s: age, usual_s: 240, section: "running",
            doing: { stage: "command", cpu_pct: cpu }, ...more });
const ci = (worker: string): More => ({ kind: "runner", project: "example-org__example-api", job: "CI (backend tests)",
  client: "github", client_os: null, pinned_worker: worker, can_run_on: undefined,
  run_url: "https://github.com/example-org/example-api/actions/runs/2" });
const only = (id: string, worker: string, more: More = {}) =>
  job(id, { section: "queued", can_run_on: [worker], needs: [], ...more });

const LONG = { project: "example-storefront-checkout", job: "check-and-integration", branch: "feature/checkout-address-validation-rework" };

function split() {
  const running = [
    run("A41F9C", "build-1", 134, 320, { branch: "feature/login", boost: true }),
    run("E93B21", "build-1", 62, 180, { project: "example-api", job: "test", branch: "fix/timeouts", client_os: "Linux" }),
    run("C07E55", "build-2", 41, 110, { ...ci("build-2"), doing: { step: "Build site", cpu_pct: 110 }, usual_s: 90 }),
  ];
  const queued = [
    only("W00001", "build-1", { branch: "feature/login", waiting_for: "Waits for the job running on this branch" }),
    only("W00002", "build-2", { project: "example-worker", branch: "chore/deps" }),
    only("W00003", "build-2", { ...LONG, paused: true, client_os: "Linux",
                                waiting_for: "The project example-storefront-checkout is paused. Resume it with `mulebox project resume example-storefront-checkout`" }),
    only("W00004", "build-2", ci("build-2")),
    ...["docs-site", "example-app", "example-api", "web-shop", "example-worker"].map((project, index) =>
      only(`W0001${index}`, "build-2", { project, branch: index % 2 ? "main" : `fix/issue-${40 + index}` })),
  ];
  return { running, queued, machines: { "build-1": { slots: 2, state: "busy" }, "build-2": { slots: 1, state: "busy" } } };
}

function wide() {
  const running = [
    run("A41F9C", "build-1", 134, 320, { branch: "feature/login", boost: true }),
    run("E93B21", "build-1", 362, 0, { project: "example-api", job: "test", branch: "fix/timeouts", client_os: "Linux", paused: true,
                                       question: { reason: "no output and no CPU for 20 min", left_s: 540 } }),
    run("C07E55", "build-1", 41, 110, { ...ci("build-1"), doing: { step: "Build site", cpu_pct: 110 }, usual_s: 90 }),
    run("B0E6F5", "build-1", 12, 640, { ...LONG }),
    run("D2A771", "build-2", 75, 210, { project: "docs-site", job: "build", branch: "draft/pricing" }),
    run("F5C310", "build-2", 20, 90, { project: "example-worker", branch: "chore/deps", client_os: "Linux" }),
  ];
  const queued = [
    only("W00001", "build-1", { ...LONG, paused: true, waiting_for: "Waits for the job running on this branch" }),
    job("W00002", { section: "queued", can_run_on: ["build-1", "build-2"], needs: [], project: "web-shop" }),
    only("W00003", "build-2", ci("build-2")),
    only("W00004", "build-1", ci("build-1")),
    job("W00005", { section: "queued", can_run_on: ["build-1", "build-2"], needs: [], project: "example-api", job: "lint", branch: "feature/rate-limit" }),
    job("W00006", { section: "queued", can_run_on: [], needs: ["gpu"], job: "e2e", waiting_for: "Needs gpu, which no machine offers" }),
  ];
  return { running, queued, machines: { "build-1": { slots: 4, state: "busy" }, "build-2": { slots: 2, state: "busy" } } };
}

const MB = 1024 ** 2;
function downloads() {
  const step = { step: "Run actions/setup-node@v4", cpu_pct: 0 };
  const cache = { what: "cache", name: "npm cache", done_bytes: 12 * MB, total_bytes: 41 * MB, rate_bytes_s: 0.5 * MB,
                  as_of_s: 30, net_bytes_s: 0.6 * MB, net_scope: "job", waiting_on_network: true, quiet_s: 0, stalled: false };
  const pnpm = { what: "package", name: "next@16.4.3", done_bytes: 18 * MB, total_bytes: null, rate_bytes_s: 0.4 * MB,
                 as_of_s: 1, net_bytes_s: 3.1 * MB, net_scope: "machine", waiting_on_network: true, quiet_s: 0, stalled: false };
  const still = { rate_bytes_s: 0, net_bytes_s: 0, quiet_s: 75, stalled: true };
  const running = [
    run("A41F9C", "build-1", 72, 30, { branch: "feat/checkout-form", doing: { stage: "install", cpu_pct: 30, download: pnpm } }),
    run("C07E55", "build-1", 48, 0, { ...ci("build-1"), usual_s: 180, paused: true, boost: true, doing: { ...step, download: cache } }),
    run("E93B21", "build-1", 117, 0, { branch: "feat/checkout-form", doing: { stage: "install", cpu_pct: 0, download: { ...pnpm, ...still } } }),
    run("B0E6F5", "build-1", 93, 0, { ...ci("build-1"), usual_s: 180, doing: { ...step, download: { ...cache, ...still } } }),
    run("D2A771", "build-2", 20, 5, { ...LONG, doing: { stage: "toolchain", cpu_pct: 5, download: {
      what: "tool", name: "chromium-headless-shell-linux-x64-with-a-long-file-name.tar.gz", done_bytes: null, total_bytes: null,
      rate_bytes_s: null, net_bytes_s: 3.1 * MB, net_scope: "machine", quiet_s: null, stalled: null } } }),
    run("F5C310", "build-2", 20, 90, { project: "example-worker", branch: "chore/deps", client_os: "Linux", doing: {
      stage: "install", cpu_pct: 90, download: { what: "package", name: "torch-2.5.1-cp312-cp312-manylinux1_x86_64.whl",
      done_bytes: null, total_bytes: 906 * MB, rate_bytes_s: null, net_bytes_s: 3.1 * MB, net_scope: "machine",
      quiet_s: null, stalled: null } } }),
  ];
  return { running, queued: [] as MockJob[], machines: { "build-1": { slots: 4, state: "busy" }, "build-2": { slots: 2, state: "busy" } } };
}

export function makeScene(name: string | undefined) {
  const made = name === "split" ? split() : name === "wide" ? wide() : name === "downloads" ? downloads() : null;
  if (!made) return null;
  made.queued.forEach((row: MockJob, index) => { row.position = index + 1; row.elapsed_s = 25 * (index + 1); });
  return { queue: { running: made.running as MockJob[], queued: made.queued as MockJob[], recent: [] as MockJob[] }, machines: made.machines };
}
