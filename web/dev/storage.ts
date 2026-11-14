// Storage for the stand-in API (docs/interfaces-m2.md, `/api/storage`): a report per node as a
// worker's sweep sends it, keep marks, and removals that answer after a moment. Every name is
// made up. MULEBOX_MOCK_SCENE=lowspace puts build-1 under its reserve with a list of what
// could go next, for the strip's warning and the review window.

const GB = 1e9, DAY = 86400;
const LOW = process.env.MULEBOX_MOCK_SCENE === "lowspace";
const now = () => Date.now() / 1000;
interface Folder { folder: string; size: number; last_used: number; fate: string; removed_in: number | null }
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

const projects = [project("example-app", 56, 37.2 * GB, 0.008, 2.3 * GB), project("example-shop", 69, 23.5 * GB, 0.08, 1.4 * GB),
                  project("mulebox", 19, 1.27 * GB, 0.03, 0.5 * GB), project("example-docs", 1, 0.7 * GB, 16.2, 0)];
const where = (home: string) => ({ projects: `${home}/.mulebox/projects`, packages: `${home}/.mulebox/cache/packages`,
  toolchains: `${home}/.mulebox/cache/toolchains`, browsers: `${home}/.mulebox/cache/playwright`, caches_other: `${home}/.mulebox/cache`,
  runners: `${home}/.mulebox/runners`, staging: `${home}/.mulebox/staging`, jobs: `${home}/.mulebox/jobs` });
const policy = { keep_free: "10%", unused_days: 7, keep_latest: true, idle_days: 14 };

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
    short: LOW ? short() : null, removed: LOW ? { count: 0, bytes: 0 } : { count: 13, bytes: 4.3 * GB },
  };
  const ios = project("example-ios", 6, 3.3 * GB, 0.4, 1.2 * GB);
  const mac = { at: now() - 41 * 60, disk: { total: 994 * GB, free: 382 * GB, reserve: 99.4 * GB }, policy, projects: [ios],
                shared: { toolchains: 0.3 * GB, browsers: 0, caches_other: 0, runners: 1.3 * GB, staging: 0.1 * GB, jobs: 0 },
                paths: where("/Users/alice"), docker: null, idle: [], short: null, removed: { count: 0, bytes: 0 } };
  return [main, mac];
}

export function storageBody(machines: { name: string; state: string; version?: string | null }[], editable: boolean) {
  const made = reports();
  return { nodes: machines.map((m, index) => ({ node: m.name, online: m.state !== "offline", version: m.version, report: made[index] ?? null })),
           keeps, branches, editable };
}

export function keepMark(body: Record<string, unknown>) {
  const project = String(body.project), branch = typeof body.branch === "string" ? body.branch : null;
  const at = keeps.findIndex((k) => k.project === project && k.branch === branch);
  if (body.keep === false) { if (at >= 0) keeps.splice(at, 1); } else if (at < 0) keeps.push({ project, branch, since: now() });
  return { keeps };
}

const groups = new Map<string, { project: string; branch: string | null; asked: number; nodes: string[] }>();
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
  if (done) {
    const at = projects.findIndex((p) => p.project === found.project);
    if (at >= 0 && found.branch === null) projects.splice(at, 1);
    else if (at >= 0) projects[at].folders = projects[at].folders.filter((f) => branches[found.project][f.folder] !== found.branch);
  }
  return { group, done, action: "reset",
           answers: found.nodes.map((node) => ({ node, output: done ? "removed" : null, exit_code: done ? 0 : null, answered: done, lost: false })) };
}
