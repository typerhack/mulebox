// What mulebox holds on each node (docs/interfaces-m2.md, `/api/storage`; docs/design.md, Disk
// use and cleanup on its own), without React: the reply's shape, what the page works out from
// a node's report, and the two changes the page can ask for. A report is what the node's last
// sweep measured, an hour old at most; nothing here measures anything.

import { getJson, post } from "./api";
import { bytes, plural } from "./format";

export type Fate = "running" | "kept" | "latest" | "remove" | "stays";
export interface Folder { folder: string; size: number; last_used: number | null; fate: Fate; removed_in: number | null }
export interface Project { project: string; home: number; caches: number; folders: Folder[] }
export interface Policy { keep_free: string; unused_days: number; keep_latest: boolean; idle_days: number }
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
}
export interface NodeStorage { node: string; online: boolean; version?: string | null; report: Report | null }
export interface Keep { project: string; branch: string | null }
export interface StorageBody {
  nodes: NodeStorage[];
  keeps: Keep[];
  branches: Record<string, Record<string, string>>;
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
export const held = (report: Report) => sum(parts(report).map((part) => part.size));
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
export function fateText(folder: Pick<Folder, "fate" | "removed_in">): string {
  if (folder.fate === "running") return "A job runs in it now";
  if (folder.fate === "kept") return "Kept by you";
  if (folder.fate === "latest") return "Kept: the project's latest";
  if (folder.fate === "remove") return "Goes at the next sweep";
  return folder.removed_in === null ? "Stays" : `Removed ${inDays(folder.removed_in)}`;
}

// What goes next on its own, soonest first: the list behind "Show".
export function goingNext(report: Report): CouldGo[] {
  const all = report.projects.flatMap((p) => p.folders.map((f) => ({ ...f, project: p.project })));
  const due = (f: Folder) => (f.fate === "remove" ? -1 : f.removed_in ?? Infinity);
  return all.filter((f) => f.fate === "remove" || f.fate === "stays").sort((a, b) => due(a) - due(b));
}
export function nextLine(report: Report): string {
  const next = goingNext(report);
  const soon = next.filter((f) => f.fate === "remove" || (f.removed_in ?? Infinity) < 1);
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

// What a node's next sweep would do with other values than it has, from its last report: the
// rules of worker/storage_rules.py, on the folders as they were measured.
export interface Preview { reserve: number; goes: number; frees: number; shortBy: number }
export function preview(report: Report, policy: Policy, now: number): Preview | null {
  const reserve = reserveOf(policy.keep_free, report.disk.total);
  if (reserve === null) return null;
  let goes = 0, frees = 0;
  for (const project of report.projects) {
    const newest = Math.max(...project.folders.map((f) => f.last_used ?? 0));
    for (const folder of project.folders) {
      if (folder.fate === "running" || folder.fate === "kept") continue;
      if (policy.keep_latest && (folder.last_used ?? 0) === newest) continue;
      const age = folder.last_used ? (now - folder.last_used) / 86400 : Infinity;
      if (age >= policy.unused_days) { goes += 1; frees += folder.size; }
    }
  }
  return { reserve, goes, frees, shortBy: Math.max(0, reserve - (report.disk.free + frees)) };
}
export function previewText(found: Preview, report: Report): string {
  const sweep = found.goes ? `the next sweep removes ${plural(found.goes, "folder")} and frees ${bytes(found.frees)}`
    : "the next sweep removes nothing";
  const after = found.shortBy > 0
    ? `That leaves the disk ${bytes(found.shortBy)} under the reserve, so mulebox would ask you what else may go.`
    : `The disk stays ${bytes(report.disk.free + found.frees - found.reserve)} above the reserve.`;
  return `With these values the reserve is ${bytes(found.reserve)} and ${sweep}. ${after}`;
}

export const readStorage = () => getJson<StorageBody>("/api/storage");
export const sendKeep = (project: string, branch: string | null, keep: boolean) =>
  post<{ keeps: Keep[] }>("/api/storage/keep", { project, ...(branch ? { branch } : {}), keep });

interface Answer { node: string; output: string | null; exit_code: number | null; answered: boolean; lost: boolean }
interface Removal { group: string; done: boolean; answers?: Answer[]; offline?: string[] }
const POLL_MS = 1000, POLLS = 320;  // a node answers within seconds; the coordinator gives up after 5 minutes

// Remove a project's folders, or one branch's, on every node, as `mulebox project reset --yes`.
// Resolves with what went wrong on a node, in words, or nothing when every node did it.
export async function sendRemove(project: string, branch: string | null,
                                 wait = (ms: number) => new Promise<void>((done) => setTimeout(done, ms))): Promise<string[]> {
  let reply = await post<Removal>("/api/storage/remove", { project, ...(branch ? { branch } : {}) });
  for (let turn = 0; !reply.done && turn < POLLS; turn += 1) {
    await wait(POLL_MS);
    reply = await getJson<Removal>(`/api/storage/remove/${encodeURIComponent(reply.group)}`);
  }
  const answers = reply.answers ?? [];
  return [
    ...answers.filter((a) => a.lost).map((a) => `${a.node} did not answer.`),
    ...answers.filter((a) => a.answered && a.exit_code).map((a) => `${a.node}: ${(a.output ?? "").trim().split("\n").pop() || "it failed"}`),
    ...(reply.done ? [] : ["The nodes have not all answered yet."]),
  ];
}
