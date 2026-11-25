// The `resting` scene for `npm run dev` (MULEBOX_MOCK_SCENE=resting; docs/design.md, A node that
// rests): build-1 rests for a full disk with two jobs waiting for it, one put back in line once;
// build-2 holds back Docker; build-3 (with MULEBOX_MOCK_MACHINES=3 or more) is under 10% free.
// Check now answers after a moment, and the check still fails.

import { job, type MockJob } from "./fixtures.ts";

const now = () => Date.now() / 1000;
const GB = 1e9;
const RAN = ["disk", "roots", "git", "executor", "docker"];

const DISK = { check: "disk", message: "1.2 GB free on the disk of its cache folder, under its min_free of 5.0 GB",
               fix: "free space on build-1: `mulebox storage clean` removes what its rules allow, `mulebox project clean` lists more; `docker system df` shows Docker's",
               since: now() - 18 * 60 };
const DOCKER = { check: "docker", message: "Docker does not answer (Cannot connect to the Docker daemon at unix:///var/run/docker.sock)",
                 fix: "start Docker: `sudo systemctl start docker` on build-2; jobs without Docker still run there", since: now() - 120 };
const report = (more: Record<string, unknown>) =>
  ({ resting: false, until: null, problems: [], withheld: [], round: 12, answers: 0, ran: RAN,
     checked_at: now() - 20, next_at: now() + 40, min_free: 5 * GB, ...more });

export const RESTING_MACHINES = {
  "build-1": { slots: 2, state: "resting", more: { free_slots: 0, disk_free: 1.2 * GB, disk_total: 490 * GB,
                                                    health: report({ resting: true, problems: [DISK] }) } },
  "build-2": { slots: 2, state: "available", more: { disk_free: 120 * GB, disk_total: 490 * GB,
    capabilities: ["linux", "docker", "compose-v1", "isolated"],
    health: report({ problems: [DOCKER], withheld: ["compose-v1", "docker", "isolated"] }) } },
  "build-3": { state: "available", more: { disk_free: 21 * GB, disk_total: 250 * GB, health: report({ ran: ["disk", "roots", "git"] }) } },
};

// Check now: the next round counts one answer more, and the check has run again.
export function checked(row: Record<string, any>) {  // eslint-disable-line @typescript-eslint/no-explicit-any
  if (!row.health) return;
  row.health = { ...row.health, round: row.health.round + 1, answers: row.health.answers + 1,
                 checked_at: now(), next_at: now() + 60 };
}

export function restingScene() {
  const wait = (id: string, more: Record<string, unknown>) =>
    job(id, { section: "queued", can_run_on: ["build-1"], needs: ["linux"], held_by: ["build-1"],
              waiting_for: `build-1 is resting: ${DISK.message} (since 10:42); ${DISK.fix}. After a fix, \`mulebox machine check <node>\` (build-1) lets it take jobs at once`,
              ...more });
  const queued: MockJob[] = [
    wait("W00001", { project: "example-app", branch: "feature/login-form", client_os: "macOS" }),
    wait("W00002", { project: "example-shop", job: "integration", branch: "fix/cart-total", client_os: "Linux", retries: 1 }),
  ];
  return { running: [] as MockJob[], queued, machines: RESTING_MACHINES };
}
