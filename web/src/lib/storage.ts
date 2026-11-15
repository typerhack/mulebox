// What mulebox holds on each node (docs/interfaces-m2.md, `/api/storage`; docs/design.md, Disk
// use and cleanup on its own), without React: the reply's shape, what the page works out from
// a node's report, and the two changes the page can ask for. A report is what the node's last
// sweep measured, an hour old at most; nothing here measures anything.

import { getJson, post } from "./api";
import { bytes, plural } from "./format";

export type Fate = "running" | "kept" | "latest" | "remove" | "stays";
export type Why = "gone" | "unused" | "size";   // why a folder goes: its branch is gone, no job for long, over the size limit
export interface Folder { folder: string; size: number; last_used: number | null; fate: Fate; removed_in: number | null; why?: Why | null }
export interface Project { project: string; home: number; caches: number; folders: Folder[] }
// The last four are a 1.26 node's: an older one sends none, and cleans folders on its own.
export interface Policy {
  keep_free: string; unused_days: number; keep_latest: boolean; idle_days: number;
  auto_clean?: boolean; docker_clean?: boolean; max_size?: string; warn_size?: string;
}
// One cleanup of a node: when and why it ran, what it removed and what that freed.
export type Trigger = "start" | "hourly" | "low" | "now";
export interface Removed { project: string; folder: string; size: number; why: Why | null }
export interface DockerFreed { build_cache: number; images: number; removed: string[]; error: string | null }
export interface Sweep {
  started: number; seconds: number; trigger: Trigger; auto: boolean; would_remove: number;
  removed: Removed[]; count: number; bytes: number; docker: DockerFreed | null;
  free_before: number; free_after: number; errors: string[];
}
export interface DockerPart { size: number | null; reclaimable: number | null; count: number | null }
export interface Idle { project: string; days: number | null; size: number; kept: boolean }
export type CouldGo = Folder & { project: string };
export interface Short { need: number; could_free: number; folders: CouldGo[] }
export interface Report {
  at: number;
  disk: { total: number; free: number; reserve: number };
  policy: Policy;
  projects: Project[];
  shared: Record<string, number>;
  paths?: Record<string, string>;        // where each part is on the node; a worker before 1.25 sends none
  docker: Record<string, DockerPart> | null;
  idle: Idle[];
  short: Short | null;
  removed: { count: number; bytes: number };
  held?: number;                         // all mulebox holds on the node, in bytes (1.26)
  over?: number;                         // bytes still over `max_size` after the cleanup (1.26)
  sweep?: Sweep | null;                  // the node's last cleanup (1.26)
  measured_at?: number;                  // when the sizes were measured; `at` is when the plan was made (1.28)
  next_sweep?: number;                   // when the node's next cleanup runs on its own (1.28)
}
// When the sizes in a report were measured: a node from 1.28 plans again between cleanups.
export const measuredAt = (report: Report) => report.measured_at ?? report.at;
export interface NodeStorage { node: string; online: boolean; version?: string | null; report: Report | null }
export interface Keep { project: string; branch: string | null }
export interface StorageBody {
  nodes: NodeStorage[];
  keeps: Keep[];
  branches: Record<string, Record<string, string>>;
  history?: (Sweep & { node: string })[];  // the newest cleanups of every node, newest first (1.26)
  editable: boolean;
}

const sum = (numbers: number[]) => numbers.reduce((a, b) => a + b, 0);
export const foldersSize = (project: Project) => sum(project.folders.map((f) => f.size));
export const projectSize = (project: Project) => foldersSize(project) + project.home + project.caches;

// The parts of the ruler, in its order: what mulebox holds, by kind.
export type PartKey = "folders" | "caches" | "tools" | "runners" | "other";
export interface Part { key: PartKey; label: string; size: number }
export function parts(report: Report): Part[] {
  const shared = (name: string) => report.shared[name] ?? 0;
  return [
    { key: "folders", label: "Branch folders", size: sum(report.projects.map((p) => foldersSize(p) + p.home)) },
    { key: "caches", label: "Package caches", size: sum(report.projects.map((p) => p.caches)) + shared("caches_other") },
    { key: "tools", label: "Toolchains and browsers", size: shared("toolchains") + shared("browsers") },
    { key: "runners", label: "GitHub runners", size: shared("runners") },
    { key: "other", label: "Uploads and job folders", size: shared("staging") + shared("jobs") },
  ];
}
export const held = (report: Report) => report.held ?? sum(parts(report).map((part) => part.size));
// Free space above the reserve; under zero the node is short.
export const headroom = (report: Report) => report.disk.free - report.disk.reserve;

// The branch a folder name stands for, when the job history knows it.
export const branchOf = (body: StorageBody, project: string, folder: string): string | null =>
  body.branches[project]?.[folder] ?? null;
export const keptProject = (body: StorageBody, project: string) =>
  body.keeps.some((keep) => keep.project === project && keep.branch === null);
export const keptBranch = (body: StorageBody, project: string, branch: string | null) =>
  branch !== null && body.keeps.some((keep) => keep.project === project && keep.branch === branch);

// What Clean on a project's row removes: its branch folders that would go by themselves anyway.
// The latest, the kept and one a job runs in stay; one whose branch is not known cannot be
// removed alone (the request takes a branch) and stays too.
export function cleanable(body: StorageBody, project: Project): { goes: Folder[]; stays: Folder[]; unknown: Folder[] } {
  const free = project.folders.filter((f) => f.fate === "stays" || f.fate === "remove");
  return { goes: free.filter((f) => branchOf(body, project.project, f.folder) !== null),
           unknown: free.filter((f) => branchOf(body, project.project, f.folder) === null),
           stays: project.folders.filter((f) => f.fate !== "stays" && f.fate !== "remove") };
}

const inDays = (days: number) => (days < 1 ? "within a day" : `in ${plural(Math.ceil(days), "day")}`);
// Why a folder goes, or went, in words.
export function whyText(why: Why | null | undefined, days: number): string {
  if (why === "gone") return "its branch is gone from your dev machines";
  if (why === "size") return "over the size limit";
  return `no job for ${plural(days, "day")}`;
}
export function fateText(folder: Pick<Folder, "fate" | "removed_in" | "why">, policy?: Policy): string {
  if (folder.fate === "running") return "A job runs in it now";
  if (folder.fate === "kept") return "Kept by you";
  if (folder.fate === "latest") return "Kept: the project's latest";
  if (folder.fate === "remove") {
    const why = policy ? `: ${whyText(folder.why, policy.unused_days)}` : "";
    return policy?.auto_clean === false ? `Would go (automatic cleanup is off)${why}` : `Goes at the next cleanup${why}`;
  }
  return folder.removed_in === null ? "Stays" : `Removed ${inDays(folder.removed_in)}`;
}

// A size setting ("50GB", "500MB", "1TB") in bytes; null for "OFF" or none.
export function sizeBytes(text: string | null | undefined): number | null {
  const found = /^\s*(\d+(?:\.\d+)?)\s*(MB|GB|TB)\s*$/i.exec(text ?? "");
  return found ? Number(found[1]) * { MB: 1e6, GB: 1e9, TB: 1e12 }[found[2].toUpperCase() as "MB" | "GB" | "TB"] : null;
}

// What the automatic cleanup of a node does, as its settings stand: one sentence per rule, and
// what is off said as off.
export function policyLines(policy: Policy): { on: boolean; rules: string[] } {
  const on = policy.auto_clean !== false, limit = sizeBytes(policy.max_size);
  const verb = on ? "Removes" : "Would remove";
  return { on, rules: [
    policy.auto_clean === undefined
      ? `${verb} a branch folder after ${plural(policy.unused_days, "day")} with no job`
      : `${verb} a branch folder when its branch is gone from your dev machines, or after ${plural(policy.unused_days, "day")} with no job`,
    policy.keep_latest ? "keeps each project's latest folder" : "a project's latest folder goes like the rest",
    `keeps ${policy.keep_free} of the disk free`,
    ...(limit === null ? [] : [`holds at most ${bytes(limit)}`]),
    policy.docker_clean === undefined ? "leaves Docker alone"
      : !policy.docker_clean ? "Docker cleanup is off"
        : on ? "cleans Docker's unused build cache and images" : "would clean Docker's unused build cache and images",
  ] };
}

// What mulebox holds against its limits: past `warn_size` agents are warned, past `max_size`
// the cleanup removes older folders; `over` is what it could not reach.
export interface SizeState { held: number; warn: number | null; max: number | null; warned: boolean; over: number; blocks: string[] }
export function sizeState(report: Report): SizeState {
  const total = held(report), warn = sizeBytes(report.policy.warn_size), max = sizeBytes(report.policy.max_size);
  const fates = new Set(report.projects.flatMap((p) => p.folders.map((f) => f.fate)));
  const blocks = [fates.has("latest") && "latest", fates.has("kept") && "kept", fates.has("running") && "running"].filter(Boolean) as string[];
  return { held: total, warn, max, warned: warn !== null && total > warn, over: report.over ?? 0, blocks };
}

export const TRIGGERS: Record<Trigger, string> = {
  start: "The node started", hourly: "Hourly", low: "Free space fell under the reserve", now: "Run now, by hand",
};

// What goes next on its own, soonest first: the list behind "Show".
export function goingNext(report: Report): CouldGo[] {
  const all = report.projects.flatMap((p) => p.folders.map((f) => ({ ...f, project: p.project })));
  const due = (f: Folder) => (f.fate === "remove" ? -1 : f.removed_in ?? Infinity);
  return all.filter((f) => f.fate === "remove" || f.fate === "stays").sort((a, b) => due(a) - due(b));
}
// What a cleanup removes now, and when the node does it by itself: Run now removes the same.
export function nextLine(report: Report, now: number): string {
  const next = goingNext(report);
  const soon = next.filter((f) => f.fate === "remove" || (f.removed_in ?? Infinity) < 1);
  const due = next.filter((f) => f.fate === "remove");
  if (due.length) {
    const what = `${plural(due.length, "branch folder")}, ${bytes(sum(due.map((f) => f.size)))}`;
    if (report.policy.auto_clean === false) return `Run now removes ${what}; with the cleanup off nothing goes by itself.`;
    const minutes = report.next_sweep === undefined ? null : Math.max(1, Math.round((report.next_sweep - now) / 60));
    return `Run now removes ${what}; ${minutes === null ? "the next cleanup does too" : `the next cleanup does in ${plural(minutes, "minute")}`}.`;
  }
  if (!next.length) return "Nothing is due to go on its own.";
  if (!soon.length) return `Nothing goes within a day. The next folder goes ${inDays(next[0].removed_in ?? 0)}.`;
  return `${plural(soon.length, "branch folder")} ${soon.length === 1 ? "goes" : "go"} within a day, ${bytes(sum(soon.map((f) => f.size)))}.`;
}

// Idle projects that wait for the owner's word (a kept one asks nothing), per project once.
export const suggestions = (report: Report | null) => (report?.idle ?? []).filter((idle) => !idle.kept);
export const suggestionCount = (body: StorageBody | null) =>
  new Set((body?.nodes ?? []).flatMap((node) => suggestions(node.report).map((idle) => idle.project))).size;
// Nodes under their reserve with nothing left for the rules to remove: the owner decides.
export const lowNodes = (body: StorageBody | null) =>
  (body?.nodes ?? []).filter((node) => node.online && node.report?.short);

// `keep_free` as the node holds it, "10%" or "50GB" ("500MB", "1TB"), in the two units the
// page offers. A size is shown in whole GB; it changes only when the viewer edits it.
export interface KeepFree { amount: number; unit: "%" | "GB" }
export function parseKeepFree(text: string | null | undefined): KeepFree | null {
  const found = /^\s*(\d+(?:\.\d+)?)\s*(%|MB|GB|TB)\s*$/i.exec(text ?? "");
  if (!found) return null;
  const amount = Number(found[1]), unit = found[2].toUpperCase();
  if (unit === "%") return { amount: Math.round(amount), unit: "%" };
  return { amount: Math.max(1, Math.round(unit === "TB" ? amount * 1000 : unit === "MB" ? amount / 1000 : amount)), unit: "GB" };
}
export const formatKeepFree = (value: KeepFree) => `${value.amount}${value.unit}`;
export function reserveOf(keepFree: string, total: number): number | null {
  const found = parseKeepFree(keepFree);
  return found ? (found.unit === "%" ? (total * found.amount) / 100 : found.amount * 1e9) : null;
}

// The same, as the page writes it: "100 GB", or "Off".
export const sizeLabel = (text: string | null | undefined) => {
  const found = /^\s*(\d+(?:\.\d+)?)\s*(MB|GB|TB)\s*$/i.exec(text ?? "");
  return found ? `${found[1]} ${found[2].toUpperCase()}` : text === null || text === undefined ? "-" : "Off";
};

// What a node's next cleanup would do with other values than it has, from its last report: the
// rules of worker/storage_rules.py, on the folders as they were measured. `goes` and `frees`
// count what the rules pick, also with cleanup on its own off, when nothing is removed;
// `bySize` of them are past the size limit, and `over` is what stays over it.
export interface Preview {
  reserve: number; goes: number; frees: number; shortBy: number;
  auto: boolean; limit: number | null; held: number; bySize: number; over: number;
}
export function preview(report: Report, policy: Policy, now: number): Preview | null {
  const reserve = reserveOf(policy.keep_free, report.disk.total);
  if (reserve === null) return null;
  let goes = 0, frees = 0;
  const stays: Folder[] = [];
  for (const project of report.projects) {
    const newest = Math.max(...project.folders.map((f) => f.last_used ?? 0));
    for (const folder of project.folders) {
      if (folder.fate === "running" || folder.fate === "kept") continue;
      if (policy.keep_latest && (folder.last_used ?? 0) === newest) continue;
      const age = folder.last_used ? (now - folder.last_used) / 86400 : Infinity;
      if (age >= policy.unused_days) { goes += 1; frees += folder.size; } else stays.push(folder);
    }
  }
  const limit = sizeBytes(policy.max_size), had = held(report);
  let over = limit === null ? 0 : had - frees - limit, bySize = 0;
  for (const folder of stays.sort((a, b) => (a.last_used ?? 0) - (b.last_used ?? 0))) {
    if (over <= 0) break;
    goes += 1; bySize += 1; frees += folder.size; over -= folder.size;
  }
  const auto = policy.auto_clean !== false, freed = auto ? frees : 0;
  if (!auto && limit !== null) over = had - limit;
  return { reserve, goes, frees, auto, limit, bySize, over: Math.max(0, over), held: had - freed,
           shortBy: Math.max(0, reserve - (report.disk.free + freed)) };
}
export function previewText(found: Preview, report: Report): string {
  const picked = plural(found.goes, "folder");
  const sizeNote = found.bySize ? `, ${found.bySize} of them to stay under the size limit` : "";
  const sweep = !found.goes ? "the next cleanup removes nothing"
    : found.auto ? `the next cleanup removes ${picked} and frees ${bytes(found.frees)}${sizeNote}`
    : `cleanup on its own is off, so the next cleanup removes nothing; it would remove ${picked}, ${bytes(found.frees)}`;
  const free = report.disk.free + (found.auto ? found.frees : 0);
  const after = found.shortBy > 0
    ? `That leaves the disk ${bytes(found.shortBy)} under the reserve, so mulebox would ask you what else may go.`
    : `The disk stays ${bytes(free - found.reserve)} above the reserve.`;
  const hold = found.auto ? "would hold" : "holds";
  const limit = found.limit === null ? ""
    : found.over > 0 ? ` mulebox ${hold} ${bytes(found.held)}, over its ${bytes(found.limit)} limit${found.auto ? ": the rest is running, kept or latest" : ""}.`
    : ` mulebox ${hold} ${bytes(found.held)} of its ${bytes(found.limit)} limit.`;
  return `With these values the reserve is ${bytes(found.reserve)} and ${sweep}. ${after}${limit}`;
}

export const readStorage = () => getJson<StorageBody>("/api/storage");
export const sendKeep = (project: string, branch: string | null, keep: boolean) =>
  post<{ keeps: Keep[] }>("/api/storage/keep", { project, ...(branch ? { branch } : {}), keep });

export interface Answer { node: string; output: string | null; exit_code: number | null; answered: boolean; lost: boolean }
interface Order { group: string; done: boolean; answers?: Answer[]; nodes?: string[]; offline?: string[] }
const POLL_MS = 1000, POLLS = 320;  // a node answers within seconds; the coordinator gives up after 5 minutes
type Wait = (ms: number) => Promise<void>;
const pause: Wait = (ms) => new Promise<void>((done) => setTimeout(done, ms));

// An order to the nodes, read until every node answered.
async function follow(first: Order, wait: Wait): Promise<Order> {
  let reply = first;
  for (let turn = 0; !reply.done && turn < POLLS; turn += 1) {
    await wait(POLL_MS);
    reply = { ...reply, ...await getJson<Order>(`/api/storage/remove/${encodeURIComponent(reply.group)}`) };
  }
  return reply;
}

// Remove a project's folders, or one branch's, on every node, as `mulebox project reset --yes`.
// Resolves with what went wrong on a node, in words, or nothing when every node did it.
export async function sendRemove(project: string, branch: string | null, wait: Wait = pause): Promise<string[]> {
  const reply = await follow(await post<Order>("/api/storage/remove", { project, ...(branch ? { branch } : {}) }), wait);
  const answers = reply.answers ?? [];
  return [
    ...answers.filter((a) => a.lost).map((a) => `${a.node} did not answer.`),
    ...answers.filter((a) => a.answered && a.exit_code).map((a) => `${a.node}: ${(a.output ?? "").trim().split("\n").pop() || "it failed"}`),
    ...(reply.done ? [] : ["The nodes have not all answered yet."]),
  ];
}

// The cleanup now on one node, Docker too, as `mulebox storage clean`: each node's own answer.
export interface SweepAnswer { node: string; ok: boolean; text: string }
export async function sendSweep(node: string, wait: Wait = pause): Promise<SweepAnswer[]> {
  const reply = await follow(await post<Order>("/api/storage/sweep", { node, docker: true }), wait);
  const answers: SweepAnswer[] = (reply.answers ?? []).map((a) => ({
    node: a.node, ok: a.answered && !a.exit_code,
    text: a.lost ? "did not answer" : !a.answered ? "has not answered yet" : (a.output ?? "").trim() || (a.exit_code ? "it failed" : "done"),
  }));
  return [...answers, ...(reply.offline ?? []).map((name) => ({ node: name, ok: false, text: "is offline" }))];
}
