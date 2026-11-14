// Storage for the stand-in API (docs/interfaces-m2.md, `/api/storage`): a report per node as a
// worker's sweep sends it, keep marks, and removals that answer after a moment. Every name is
// made up. MULEBOX_MOCK_SCENE=lowspace puts build-1 under its reserve with a list of what
// could go next, for the strip's warning and the review window.

const GB = 1e9, DAY = 86400;
const LOW = process.env.MULEBOX_MOCK_SCENE === "lowspace";
const OFF = process.env.MULEBOX_MOCK_SCENE === "cleanupoff";  // automatic cleanup off: folders that would go, a size limit passed
const now = () => Date.now() / 1000;
interface Folder { folder: string; size: number; last_used: number; fate: string; removed_in: number | null; why?: string | null }
interface Project { project: string; home: number; caches: number; folders: Folder[] }

const WORDS = ["checkout", "invoices", "login-redirect", "reports-export", "search-filters", "dark-mode", "rate-limits", "onboarding",
               "webhooks", "csv-import", "audit-log", "deps-november", "flaky-tests", "cache-headers", "empty-states", "pagination"];
const KINDS = ["feature", "fix", "chore", "agent"];
const branches: Record<string, Record<string, string>> = {};
const keeps: { project: string; branch: string | null; since: number }[] = [{ project: "example-app", branch: "main", since: now() - 9 * DAY }];

// A project's folders: `main` (kept by the viewer in example-app), the branch used last (the
// project's latest), then branches of the last week, each due once it is seven days unused.
function project(name: string, count: number, total: number, newest: number, caches: number): Project {
  const names = ["main", ...Array.from({ length: count - 1 }, (_, i) => `${KINDS[i % 4]}/${WORDS[(i * 5 + name.length) % 16]}${i >= 16 ? `-${Math.floor(i / 16) + 1}` : ""}`)];
  const weights = names.map((_, i) => 0.6 + ((i * 37 + name.length * 11) % 10) / 10);
  const scale = total / weights.reduce((a, b) => a + b, 0);
  branches[name] = {};
  const folders = names.map((branch, i) => {
    const folder = `${branch.replace(/[^A-Za-z0-9._-]+/g, "-")}-${(0x9e3779b1 * (i + 7 + name.length) >>> 0).toString(16).padStart(8, "0")}`;
    const age = count === 1 || i === 1 ? newest : i === 0 ? newest + 0.13 : Math.min(6.95, newest + 0.2 + (6.6 * (i - 1)) / (count - 2));
    branches[name][folder] = branch;
    const kept = keeps.some((k) => k.project === name && (k.branch === branch || k.branch === null));
    return { folder, size: Math.round(weights[i] * scale), last_used: now() - age * DAY, age,
             fate: age === newest ? (newest < 0.01 ? "running" : "latest") : kept ? "kept" : "stays", removed_in: null as number | null };
  });
  return { project: name, home: Math.round(0.02 * total), caches,
           folders: folders.map(({ age, ...f }) => ({ ...f, removed_in: f.fate === "stays" ? Math.max(0, 7 - age) : null })) };
}

const made = [project("example-app", 56, 37.2 * GB, 0.008, 2.3 * GB), project("example-shop", 69, 23.5 * GB, 0.08, 1.4 * GB),
                  project("mulebox", 19, 1.27 * GB, 0.03, 0.5 * GB), project("example-docs", 1, 0.7 * GB, 16.2, 0)];
// Two folders are due at the next cleanup: one whose branch was deleted, one unused for a week
// (with the cleanup off, three, one of them over the size limit).
function due(projectName: string, at: number, why: string) {
  const folder = made.find((p) => p.project === projectName)?.folders.filter((f) => f.fate === "stays").at(-at);
  if (folder) Object.assign(folder, { fate: "remove", removed_in: null, why });
}
due("example-app", 1, "unused"); due("example-shop", 3, "gone");
if (OFF) due("example-app", 2, "size");
const projects = made;
const where = (home: string) => ({ projects: `${home}/.mulebox/projects`, packages: `${home}/.mulebox/cache/packages`,
  toolchains: `${home}/.mulebox/cache/toolchains`, browsers: `${home}/.mulebox/cache/playwright`, caches_other: `${home}/.mulebox/cache`,
  runners: `${home}/.mulebox/runners`, staging: `${home}/.mulebox/staging`, jobs: `${home}/.mulebox/jobs` });
const policy = { keep_free: "10%", unused_days: 7, keep_latest: true, idle_days: 14, auto_clean: !OFF, docker_clean: true,
                 warn_size: "50GB", max_size: OFF ? "60GB" : "OFF" };

// A node's cleanups, newest first: hourly ones that found nothing, one after a branch was
// deleted, one by hand with Docker, one with an error, one when the disk ran low.
const removedOf = (list: [string, string, number, string][]) => list.map(([project, branch, gb, why]) =>
  {
    const folder = `${branch.replace(/\W+/g, "-")}-0f1e2d3c`;
    (branches[project] ??= {})[folder] = branch;
    return { project, folder, size: gb * GB, why };
  });
function sweep(hoursAgo: number, trigger: string, gone: [string, string, number, string][], docker: [number, number, string[]] | null,
               free: number, errors: string[] = []) {
  const removed = removedOf(gone), bytes = removed.reduce((a, f) => a + f.size, 0);
  const freed = bytes + (docker ? (docker[0] + docker[1]) * GB : 0);
  return { started: now() - hoursAgo * 3600, seconds: Math.round((3 + gone.length * 1.7) * 10) / 10, trigger, auto: !OFF, would_remove: OFF ? 3 : 0,
           removed: OFF ? [] : removed, count: OFF ? 0 : removed.length, bytes: OFF ? 0 : bytes,
           docker: OFF ? null : docker && { build_cache: docker[0] * GB, images: docker[1] * GB, removed: docker[2], error: null },
           free_before: free * GB - freed, free_after: free * GB, errors };
}
function history(node: string) {
  const quiet = (h: number) => sweep(h, "hourly", [], [0, 0, []], 80);
  return [
    sweep(0.2, "hourly", [["example-app", "feature/old-pricing", 0.8, "gone"], ["example-shop", "fix/typo", 0.4, "unused"]], [1.2, 0.4, ["node:20-bookworm"]], 80),
    quiet(1.2), quiet(2.2),
    sweep(3.2, "now", [["example-shop", "agent/spike-search", 0.9, "unused"]], [6.3, 2.1, ["postgres:16", "redis:7"]], 78.3),
    quiet(4.2),
    sweep(5.2, "hourly", [["example-app", "chore/bump-eslint", 0.5, "gone"]], [0, 0, []], 68.4,
          ["example-shop/fix-webhooks-1a2b3c4d: [Errno 13] Permission denied: 'node_modules/.cache'"]),
    sweep(6.1, "low", [["example-app", "feature/reports-v1", 1.1, "size"], ["example-app", "feature/reports-v2", 0.9, "size"],
                       ["example-shop", "fix/cart-rounding", 0.6, "unused"]], [3.8, 0, []], 67.9),
    sweep(7.2, "start", [], null, 61.5),
    ...Array.from({ length: 18 }, (_, i) => quiet(8.2 + i)),
  ].map((one) => ({ node, ...one }));
}

// What the node says could go next: the oldest folders, until they cover what is missing.
function short() {
  const need = 3 * GB, could: (Folder & { project: string })[] = [];
  const oldest = projects.flatMap((p) => p.folders.map((f) => ({ ...f, project: p.project })))
    .filter((f) => f.fate !== "running").sort((a, b) => a.last_used - b.last_used);
  for (const folder of oldest) {
    if (could.reduce((a, f) => a + f.size, 0) >= need) break;
    could.push(folder);
  }
  return { need, could_free: could.reduce((a, f) => a + f.size, 0), folders: could };
}

function reports() {
  const main = {
    at: now() - 12 * 60, disk: { total: 490 * GB, free: (LOW ? 46 : 80) * GB, reserve: 49 * GB }, policy, projects,
    shared: { toolchains: 2.1 * GB, browsers: 1.3 * GB, caches_other: 0.2 * GB, runners: 4.1 * GB, staging: 0.4 * GB, jobs: 0.1 * GB },
    paths: where("/home/alice"),
    docker: { images: { size: 9.8 * GB, reclaimable: 3.6 * GB, count: 23 }, containers: { size: 0.2 * GB, reclaimable: 0, count: 6 },
              volumes: { size: 1.1 * GB, reclaimable: 0.3 * GB, count: 9 }, build_cache: { size: 9.7 * GB, reclaimable: 9.4 * GB, count: 212 } },
    idle: [{ project: "example-docs", days: 16, size: 0.7 * GB, kept: keeps.some((k) => k.project === "example-docs" && !k.branch) }],
    short: LOW ? short() : null, removed: LOW || OFF ? { count: 0, bytes: 0 } : { count: 2, bytes: 1.2 * GB },
    held: 0, over: OFF ? 1.4 * GB : 0, sweep: history("build-1")[0] as Record<string, unknown>,
  };
  main.held = projects.reduce((a, p) => a + p.home + p.caches + p.folders.reduce((b, f) => b + f.size, 0), 0)
    + Object.values(main.shared).reduce((a, b) => a + b, 0);
  delete main.sweep.node;
  const ios = project("example-ios", 6, 3.3 * GB, 0.4, 1.2 * GB);
  const mac = { at: now() - 41 * 60, disk: { total: 994 * GB, free: 382 * GB, reserve: 99.4 * GB }, policy, projects: [ios],
                shared: { toolchains: 0.3 * GB, browsers: 0, caches_other: 0, runners: 1.3 * GB, staging: 0.1 * GB, jobs: 0 },
                paths: where("/Users/alice"), docker: null, idle: [], short: null, removed: { count: 0, bytes: 0 } };
  return [main, mac];
}

export function storageBody(machines: { name: string; state: string; version?: string | null }[], editable: boolean) {
  const made = reports();
  return { nodes: machines.map((m, index) => ({ node: m.name, online: m.state !== "offline", version: m.version, report: made[index] ?? null })),
           keeps, branches, history: history(machines[0]?.name ?? "build-1"), editable };
}

export function keepMark(body: Record<string, unknown>) {
  const project = String(body.project), branch = typeof body.branch === "string" ? body.branch : null;
  const at = keeps.findIndex((k) => k.project === project && k.branch === branch);
  if (body.keep === false) { if (at >= 0) keeps.splice(at, 1); } else if (at < 0) keeps.push({ project, branch, since: now() });
  return { keeps };
}

const groups = new Map<string, { project: string; branch: string | null; asked: number; nodes: string[]; sweep?: boolean }>();
// Run now: the node answers after a moment with its cleanup's own summary.
export function sweepStart(body: Record<string, unknown>) {
  const group = `grp-${groups.size + 1}`, nodes = [typeof body.node === "string" ? body.node : "build-1"];
  groups.set(group, { project: "", branch: null, asked: Date.now(), nodes, sweep: true });
  return { group, nodes, offline: [], done: false };
}
export function removeStart(body: Record<string, unknown>, nodes: string[]) {
  const group = `grp-${groups.size + 1}`;
  groups.set(group, { project: String(body.project), branch: typeof body.branch === "string" ? body.branch : null, asked: Date.now(), nodes });
  return { group, nodes, offline: [], done: false };
}
// A node answers after a second and a half; the folders are then gone from its report.
export function removeRead(group: string) {
  const found = groups.get(group);
  if (!found) return null;
  const done = Date.now() - found.asked > 1500;
  if (found.sweep) {
    return { group, done, action: "sweep", answers: found.nodes.map((node) => ({ node, exit_code: done ? 0 : null, answered: done, lost: false,
      output: done ? "removed 2 branch folder(s), 1.2 GB\ndocker: build cache 1.2 GB, images 400.0 MB freed (node:20-bookworm)\nfree space 78.4 GB to 80.0 GB" : null })) };
  }
  if (done) {
    const at = projects.findIndex((p) => p.project === found.project);
    if (at >= 0 && found.branch === null) projects.splice(at, 1);
    else if (at >= 0) projects[at].folders = projects[at].folders.filter((f) => branches[found.project][f.folder] !== found.branch);
  }
  return { group, done, action: "reset",
           answers: found.nodes.map((node) => ({ node, output: done ? "removed" : null, exit_code: done ? 0 : null, answered: done, lost: false })) };
}
