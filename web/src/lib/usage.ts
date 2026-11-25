// What jobs really used (docs/design.md, Job usage): the shapes of `/api/usage`, how the page
// asks, and the sums and words both views share. The figures are the coordinator's, the same
// as `mulebox usage` prints; the page only sets them beside the node they ran on.
// A dashboard on an older coordinator answers 404: that reads as "nothing to show", never an error.

import { ApiError, getJson } from "./api";
import { bytes } from "./format";

export interface Spread { median: number; max: number }
export interface NodeSize { cores?: number | null; memory?: number | null }
export type Sizes = Record<string, NodeSize>;

export interface UsageJob {
  project: string | null;
  job: string | null;
  kind: "job" | "runner";
  runs: number;
  measured: number;
  not_measured: number;
  no_cores: number;                 // measured, but too short for cores
  cores: Spread | null;
  memory: Spread | null;
  fits: { cores: number | null; memory: number | null } | null;
  machines: string[];
  last_finished_at?: number | null;
}
export interface UsageBody { machines: Sizes; jobs: UsageJob[]; runs: number; all: boolean }

// One run's peaks; empty or null when its node sent none.
export interface Peaks {
  peak_cores?: number | null;
  peak_cores_stage?: string | null;   // a mulebox stage, or a GitHub run's step
  peak_memory?: number | null;
  peak_memory_stage?: string | null;
  cpu_s?: number | null;
  samples?: number | null;
}
export interface RunUsage {
  job_id: string;
  kind: string;
  worker?: string | null;
  state: string;
  run_s?: number | null;
  usage?: Peaks | null;
  average_cores?: number | null;
}
export interface RunBody { machines: Sizes; run: RunUsage }

export interface UsageFilters { project?: string; worker?: string; kind?: string }
export interface NodeGroup { name: string; size: NodeSize; jobs: UsageJob[] }
export interface UsageView { nodes: NodeGroup[]; machines: string[]; projects: string[] | null; runs: number; all: boolean }

export const READ_EVERY_S = 10;   // how often a worker reads a job's cores and memory
export const one = (n: number) => n.toFixed(1);
export const coresWord = (n: number) => `${n} ${n === 1 ? "core" : "cores"}`;
export const readings = (n: number) => `${n} ${n === 1 ? "reading" : "readings"}`;
// A share of a node as a width, never past its end.
export const part = (value: number, whole: number) => `${Math.max(0, Math.min(100, (100 * value) / whole)).toFixed(2)}%`;

// What one ruled unit of a track stands for: a core, or a few GB, so that a node is 8 units or
// fewer (16 for cores, which are counted one by one up to there).
const GB = 1e9;
export const coreUnit = (cores: number) => [1, 2, 4, 8, 16, 32].find((step) => cores / step <= 16) ?? 64;
export const memoryUnit = (memory: number) =>
  (memory < 4 * GB ? 0.5 : [2, 4, 8, 16, 32, 64, 128].find((step) => memory / (step * GB) <= 8.5) ?? 256) * GB;

// How heavy a job is on a node: the larger share its highest peaks take of it. Unmeasured last.
export function weight(job: UsageJob, size: NodeSize): number {
  const cores = job.cores && size.cores ? job.cores.max / size.cores : job.cores ? job.cores.max / 1e3 : -1;
  const memory = job.memory && size.memory ? job.memory.max / size.memory : job.memory ? job.memory.max / 1e15 : -1;
  return Math.max(cores, memory);
}

// A mulebox from before usage was sent (1.36.0): its runs read "not measured".
export function sendsNoUsage(version: string | null | undefined): boolean {
  const [major, minor] = (version ?? "").split(".").map(Number);
  return Number.isFinite(major) && Number.isFinite(minor) && (major < 1 || (major === 1 && minor < 36));
}

// Why nothing was measured on a node, as far as the page can tell.
export const whyNot = (node: string | null | undefined, version: string | null | undefined, what: string) => (node && sendsNoUsage(version)
  ? `${node} runs mulebox ${version}, which sends no usage` : `${node ?? "its node"} sent no usage for ${what}`);

const quiet = <T>(failure: unknown): T | null => {
  if (failure instanceof ApiError && failure.status === 404) return null;
  throw failure;
};

// The summary, a group per node. A job that ran on several nodes is asked for once per node, so
// every bar of a node is that node's own runs on that node's scale. Null: no usage on this server.
export async function askUsage(filters: UsageFilters, all: boolean): Promise<UsageView | null> {
  const chosen = Object.fromEntries(Object.entries(filters).filter(([, value]) => value)) as Record<string, string>;
  const ask = (more: Record<string, string> = {}) =>
    getJson<UsageBody>(`/api/usage?${new URLSearchParams({ ...chosen, ...(all ? { all: "1" } : {}), ...more })}`);
  const whole = await ask().catch(quiet<UsageBody>);
  if (!whole) return null;
  const ran = whole.jobs.filter((job) => job.machines.length > 0);
  const names = [...new Set(ran.flatMap((job) => job.machines))].sort();
  const parts: [string, UsageJob[]][] = names.length <= 1 ? names.map((name) => [name, ran])
    : await Promise.all(names.map(async (name): Promise<[string, UsageJob[]]> => [name, (await ask({ worker: name })).jobs]));
  const nodes = parts.map(([name, jobs]) => {
    const size = whole.machines[name] ?? {};
    return { name, size, jobs: [...jobs].sort((a, b) => weight(b, size) - weight(a, size)) };
  });
  // Nodes with measured jobs first, most first; a node that never reported (removed) last.
  const counted = (group: NodeGroup) => group.jobs.filter((job) => job.measured > 0).length;
  const known = (group: NodeGroup) => (group.size.cores || group.size.memory ? 1 : 0);
  nodes.sort((a, b) => known(b) - known(a) || counted(b) - counted(a) || a.name.localeCompare(b.name));
  const projects = filters.project ? null : [...new Set(whole.jobs.map((job) => job.project ?? ""))].filter(Boolean).sort();
  return { nodes, machines: Object.keys(whole.machines).sort(), projects, runs: whole.runs, all: whole.all };
}

// One run. Null when the server has no usage, or does not know the job.
export const askRun = (jobId: string): Promise<RunBody | null> =>
  getJson<RunBody>(`/api/usage/${encodeURIComponent(jobId)}`).catch(quiet<RunBody>);

// A peak against its node, in words: "6.1 of 8 cores", "3.5 GB of 16.0 GB"; alone when the
// node's size is not known.
export const coresOf = (peak: number, size: NodeSize) => (size.cores ? `${one(peak)} of ${coresWord(size.cores)}` : `${one(peak)} cores`);
export const memoryOf = (peak: number, size: NodeSize) => (size.memory ? `${bytes(peak)} of ${bytes(size.memory)}` : bytes(peak));
