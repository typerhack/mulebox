// The order rules of the stand-in API (dev/mock.ts): `GET|POST /api/queue/rules` as the
// dashboard answers them (docs/interfaces-m2.md), and the `order` scene's line, whose rows say
// why they stand where they do. The stand-in keeps the rules; it does not reorder the line.

import { job, type MockJob } from "./fixtures.ts";

interface Rules { projects: Record<string, number>; branches: Record<string, number>; workflows: Record<string, number>;
                  github: number; aging_min: number; shortest_first: boolean; fair_turns: boolean }
const MAPS = ["projects", "branches", "workflows"] as const;
const defaults = (): Rules => ({ projects: {}, branches: {}, workflows: {}, github: 0, aging_min: 30, shortest_first: false, fair_turns: false });
const PROJECTS = ["docs-site", "example-api", "example-app", "example-org__example-api", "example-worker"];

// What the node remembers of each project: [runs in the last seven days, hours since the last
// one]. Five in use, then the long tail a node gathers: drills and projects set aside.
const DAY = 24;
const USED: Record<string, [number, number]> = {
  "docs-site": [4, 0.2], "example-api": [1, 5 * DAY], "example-app": [12, 2], "example-org__example-api": [31, 0.01],
  "example-worker": [3, 26], "example-storefront-checkout": [6, 0.01], "example-reports": [0, 9 * DAY], "example-billing": [0, 16 * DAY],
  "example-org__example-billing": [0, 23 * DAY], "example-mobile-api": [0, 41 * DAY], "example-search": [0, 44 * DAY],
  ...Object.fromEntries(Array.from({ length: 12 }, (_, i) => [`drill-compose-${String(i + 1).padStart(2, "0")}`, [0, (60 + 9 * i) * DAY]])),
  "example-legacy-importer": [0, 420 * DAY],
};

let rules = defaults();

export function rulesBody() {
  const now = Date.now() / 1000;
  const names = [...new Set([...PROJECTS, ...Object.keys(USED)])].sort();
  return { rules, defaults: defaults(), levels: { min: -3, max: 3, words: { low: -1, normal: 0, high: 1 } }, projects: names, now,
           project_activity: names.map((name) => ({ name, last_run: now - USED[name][1] * 3600, runs_7d: USED[name][0] })) };
}

// The new rules, or the coordinator's refusal as text.
export function changeRules(body: Record<string, unknown>): string | null {
  if (body.reset === true) { rules = defaults(); return null; }
  const change = body.rules as Partial<Rules> | undefined;
  if (!change || typeof change !== "object") return "send {\"rules\": {...}} or {\"reset\": true}";
  const next: Rules = { ...rules };
  for (const map of MAPS) {
    if (!change[map]) continue;
    next[map] = { ...rules[map] };
    for (const [name, level] of Object.entries(change[map])) {
      if (!Number.isInteger(level) || level < -3 || level > 3) return `level must be low, normal, high or a whole number from -3 to 3, got ${level}`;
      if (level) next[map][name] = level; else delete next[map][name];
    }
  }
  for (const name of ["github", "aging_min", "shortest_first", "fair_turns"] as const) {
    if (name in change) Object.assign(next, { [name]: change[name] });
  }
  rules = next;
  return null;
}

// The `order` scene: two machines busy, seven jobs for the next free one, as in the mockup the
// user picked (docs/design-system/queue-order-mockup.html, option A).
export function orderScene() {
  rules = { ...defaults(), projects: { "example-app": 1, "docs-site": -1 }, branches: { main: 1 },
            workflows: { "Nightly build": -2 }, aging_min: 10, shortest_first: true, fair_turns: true };
  const now = Date.now() / 1000;
  const run = (id: string, worker: string, age: number, more: Record<string, unknown>) =>
    job(id, { state: "running", worker, started_at: now - age, elapsed_s: age, usual_s: 240, section: "running",
              doing: { stage: "command", cpu_pct: 260 }, ...more });
  const wait = (id: string, waited: number, reason: string, order: Record<string, unknown>, more: Record<string, unknown>) =>
    job(id, { section: "queued", can_run_on: ["build-1", "build-2"], needs: [], elapsed_s: waited, place_reason: reason,
              order: { by_hand: false, level: 0, levels: [], ...order }, ...more });
  const queued: MockJob[] = [
    wait("W00001", 130, "moved to the front by hand", { by_hand: true, moved: { side: "front", job_id: null, in_line: true } },
         { project: "example-worker", job: "test", branch: "fix/retry", client_os: "Linux", moved: "front" }),
    wait("W00002", 20, "branch main +1; turn 1 of example-org__example-api; usually 3m; then by arrival",
         { level: 1, levels: [{ rule: "branch", name: "main", level: 1 }], turn: 1, usual_s: 180 },
         { kind: "runner", project: "example-org__example-api", job: "CI", branch: "main", client: "github", client_os: null,
           workflow: "CI", run_url: "https://github.com/example-org/example-api/actions/runs/2" }),
    wait("W00003", 65, "project example-app +1; turn 1 of example-app; usually 4m; then by arrival",
         { level: 1, levels: [{ rule: "project", name: "example-app", level: 1 }], turn: 1, usual_s: 240 },
         { branch: "fix/cart-total" }),
    wait("W00004", 850, "project docs-site -1; waited 10m or more +1; turn 1 of docs-site; no usual length yet, counted as the line's median 3m; then by arrival",
         { level: 0, levels: [{ rule: "project", name: "docs-site", level: -1 }, { rule: "waited", minutes: 14, over: 10, level: 1 }],
           turn: 1, usual_s: null, counted_as_s: 180 },
         { project: "docs-site", job: "build", branch: "feat/search" }),
    wait("W00005", 50, "turn 1 of example-worker; usually 40s; then by arrival", { turn: 1, usual_s: 40 },
         { project: "example-worker", job: "lint", branch: "chore/deps", client_os: "Linux" }),
    wait("W00006", 58, "turn 2 of example-storefront-checkout; usually 12m; then by arrival", { turn: 2, usual_s: 720 },
         { project: "example-storefront-checkout", job: "check-and-integration", branch: "feature/checkout-address-validation-rework",
           branch_busy: "job-01EXAMPLEB0E6F5" }),
    wait("W00007", 30, "project docs-site -1; turn 2 of docs-site; usually 2m; then by arrival",
         { level: -1, levels: [{ rule: "project", name: "docs-site", level: -1 }], turn: 2, usual_s: 120 },
         { project: "docs-site", job: "preview", branch: "feat/search" }),
  ];
  const running = [
    run("A41F9C", "build-1", 134, { branch: "feature/login" }),
    run("B0E6F5", "build-2", 41, { project: "example-storefront-checkout", job: "check-and-integration",
                                   branch: "feature/checkout-address-validation-rework" }),
  ];
  return { running, queued, machines: { "build-1": { slots: 1, state: "busy" }, "build-2": { slots: 1, state: "busy" } } };
}
