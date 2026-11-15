// The `tests` scene for `npm run dev` (MULEBOX_MOCK_SCENE=tests): a finished job in each of
// the seven situations of "Proof that tests ran" (docs/design.md), as the coordinator stores
// them (coordinator/test_proof.py): fewer tests than the last pass and no tests (failures,
// exit 8), an ordinary failure with its count, a normal pass, a pass with more tests, a pass
// allowed with fewer and the agent's reason, and a lint with no summary at all. An eighth has
// `tests: required` and no summary. They fill the Failed, Passed and Recent tabs and the History
// page; each job's page has its own log, with the runners' summary lines in it.

import { job, type MockJob } from "./fixtures.ts";

const now = () => Date.now() / 1000;
type Runners = Record<string, { ran: number; skipped: number }>;
const sum = (runners: Runners, key: "ran" | "skipped") => Object.values(runners).reduce((n, item) => n + item[key], 0);
const last = (id: string, branch: string, ago: number, runners: Runners) =>
  ({ job_id: `job-01EXAMPLE${id}`, branch, ran: sum(runners, "ran"), runners, finished_at: now() - ago });
const tests = (runners: Runners, verdict: string | null, compared: unknown, more: Record<string, unknown> = {}) =>
  ({ mode: "auto", base: "main", fewer: null, runners, ran: sum(runners, "ran"), skipped: sum(runners, "skipped"), verdict, compared, ...more });
const done = (id: string, ago: number, took: number, state: "passed" | "failed", exit: number, more: Record<string, unknown>) =>
  job(id, { state: "finished", outcome: state, shown_state: state, exit_code: exit, worker: "build-1", section: "recent",
            started_at: now() - ago - took, finished_at: now() - ago, duration_s: took, ...more });

const PYTEST = (ran: number, skipped: number) => [`${".".repeat(40)} [100%]`, `${ran} passed${skipped ? `, ${skipped} skipped` : ""} in 212.40s`];
const VITEST = (ran: number, skipped: number) => ["", " RUN  v3.2.4 /job/example-app", " Test Files  24 passed (24)",
  `      Tests  ${ran ? `${ran} passed` : ""}${ran && skipped ? " | " : ""}${skipped ? `${skipped} skipped` : ""} (${ran + skipped})`];
// Each job's log, by job id: what `GET /api/jobs/{id}/log` streams in this scene.
export const TEST_LOGS: Record<string, string[]> = {};
// The summary lines the coordinator would keep (`tests.lines`): in this made-up log, the one
// each runner's helper above writes.
const SUMMARY: Record<string, (line: string) => boolean> = {
  pytest: (line) => line.endsWith(" in 212.40s"), vitest: (line) => line.startsWith("      Tests  "),
  jest: (line) => line.startsWith("Tests: "),
};
const withLog = (row: MockJob, lines: string[]) => {
  TEST_LOGS[row.job_id] = ["mulebox: job on build-1", ...lines];
  const kept = row.tests as { runners?: Record<string, unknown>; lines?: Record<string, string[]> } | undefined;
  if (kept?.runners) {
    kept.lines = Object.fromEntries(Object.keys(kept.runners)
      .map((name) => [name, lines.filter((line) => SUMMARY[name]?.(line))]));
  }
  return row;
};

export function testsScene() {
  const both = { pytest: { ran: 3462, skipped: 5 }, vitest: { ran: 213, skipped: 0 } };
  const recent = [
    withLog(done("X5K3A1", 120, 232, "passed", 0, { branch: "feature/login-form",
      tests: tests(both, "ok", last("X4M7B2", "main", 6200, both)) }),
      ["$ pytest -q && pnpm vitest run", ...PYTEST(3462, 5), ...VITEST(213, 0)]),
    withLog(done("X5H8C3", 440, 318, "passed", 0, { project: "example-api", branch: "feature/orders-table", client_os: "Linux",
      tests: tests({ pytest: { ran: 1904, skipped: 2 } }, "ok", last("X4R2D4", "main", 8300, { pytest: { ran: 1892, skipped: 2 } })) }),
      ["$ pytest -q", ...PYTEST(1904, 2)]),
    withLog(done("X5A1E5", 940, 229, "failed", 8, { branch: "fix/cart-total",
      tests: tests({ pytest: { ran: 3462, skipped: 5 }, vitest: { ran: 213, skipped: 0 } }, "fewer",
        last("X3B2F6", "fix/cart-total", 9100, { pytest: { ran: 3470, skipped: 5 }, vitest: { ran: 213, skipped: 0 } }), { command_exit: 0 }) }),
      ["$ pytest -q && pnpm vitest run", ...PYTEST(3462, 5), ...VITEST(213, 0)]),
    withLog(done("X59TG7", 1460, 41, "failed", 8, { project: "example-site", job: "unit", branch: "chore/vitest-config", client_os: "Linux",
      tests: tests({ vitest: { ran: 0, skipped: 213 } }, "zero", last("X2Z6H8", "main", 77_000, { vitest: { ran: 213, skipped: 0 } }), { command_exit: 0 }) }),
      ["$ pnpm vitest run", ...VITEST(0, 213)]),
    withLog(done("X57QJ9", 2500, 302, "passed", 0, { project: "example-api", branch: "chore/drop-v1-api",
      tests: tests({ pytest: { ran: 1820, skipped: 2 } }, "allowed", last("X4R2D4", "main", 8300, { pytest: { ran: 1892, skipped: 2 } }),
                   { fewer: "removed the old v1 API tests" }) }),
      ["$ pytest -q", ...PYTEST(1820, 2)]),
    withLog(done("X56DK0", 3200, 24, "passed", 0, { job: "lint", branch: "feature/login-form", tests: tests({}, null, null) }),
      ["$ pnpm run lint", "eslint: 412 files, no problems"]),
    withLog(done("X54BL1", 4300, 125, "failed", 1, { project: "example-shop", branch: "fix/checkout-rounding",
      tests: tests({ jest: { ran: 1204, skipped: 2 } }, null, null) }),
      ["$ pnpm jest", "FAIL src/cart/rounding.test.ts", "Tests:       3 failed, 2 skipped, 1201 passed, 1206 total"]),
    withLog(done("X53CM2", 5100, 12, "failed", 8, { project: "example-worker", job: "smoke", branch: "main", client_os: "Linux",
      tests: tests({}, "missing", null, { mode: "required", command_exit: 0 }) }),
      ["$ ./scripts/smoke.sh", "smoke: nothing to do"]),
  ];
  // The passes they were compared with, so "Open the last pass" leads somewhere.
  const earlier = [
    withLog(done("X4M7B2", 6200, 230, "passed", 0, { tests: tests(both, "ok", null) }), ["$ pytest -q && pnpm vitest run", ...PYTEST(3462, 5), ...VITEST(213, 0)]),
    withLog(done("X4R2D4", 8300, 310, "passed", 0, { project: "example-api", tests: tests({ pytest: { ran: 1892, skipped: 2 } }, "ok", null) }), ["$ pytest -q", ...PYTEST(1892, 2)]),
    withLog(done("X3B2F6", 9100, 228, "passed", 0, { branch: "fix/cart-total",
      tests: tests({ pytest: { ran: 3470, skipped: 5 }, vitest: { ran: 213, skipped: 0 } }, "ok", null) }), ["$ pytest -q && pnpm vitest run", ...PYTEST(3470, 5), ...VITEST(213, 0)]),
    withLog(done("X2Z6H8", 77_000, 40, "passed", 0, { project: "example-site", job: "unit", client_os: "Linux",
      tests: tests({ vitest: { ran: 213, skipped: 0 } }, "ok", null) }), ["$ pnpm vitest run", ...VITEST(213, 0)]),
  ];
  return { running: [] as MockJob[], queued: [] as MockJob[], recent: [...recent, ...earlier],
           machines: { "build-1": { slots: 2, state: "available" }, "build-2": { slots: 2, state: "available" } } };
}
