// The storage reply, read once when the page opens and again every minute while it is in
// view: the Storage page, the Disk panel's line, the header's count and the low-space line all
// read this one copy. A report changes with a node's sweep, hourly, so a minute is often
// enough; a change made here reads it again at once.
//
// A removal shows before the node's next report says so: what the viewer removed is left out
// of the lists until a report newer than the removal comes.

import { problemText } from "../lib/api";
import { createStore, useStore } from "../lib/store";
import { readStorage, type Keep, type Report, type StorageBody } from "../lib/storage";

const EVERY_MS = 60_000;
interface State { body: StorageBody | null; problem: string | null }
export const storageStore = createStore<State>({ body: null, problem: null });
interface Gone { project: string; folder: string | null; at: number }
export const goneStore = createStore<Gone[]>([]);

export async function refreshStorage(): Promise<void> {
  try {
    const body = await readStorage();
    storageStore.set({ body, problem: null });
  } catch (failure) {
    storageStore.set((had) => ({ ...had, problem: problemText(failure) }));
  }
}

export function startStorage(): () => void {
  void refreshStorage();
  const timer = setInterval(() => { if (!document.hidden) void refreshStorage(); }, EVERY_MS);
  return () => clearInterval(timer);
}

export const setKeeps = (keeps: Keep[]) =>
  storageStore.set((had) => (had.body ? { ...had, body: { ...had.body, keeps } } : had));
export const markGone = (project: string, folder: string | null) =>
  goneStore.set((had) => [...had, { project, folder, at: Date.now() / 1000 }]);

// A report without what the viewer removed since it was measured.
export function without(report: Report, gone: Gone[]): Report {
  const fresh = gone.filter((g) => g.at > report.at);
  if (!fresh.length) return report;
  const went = (project: string, folder: string) =>
    fresh.some((g) => g.project === project && (g.folder === null || g.folder === folder));
  return {
    ...report,
    projects: report.projects.filter((p) => !fresh.some((g) => g.project === p.project && g.folder === null))
      .map((p) => ({ ...p, folders: p.folders.filter((f) => !went(p.project, f.folder)) })),
    idle: report.idle.filter((idle) => !fresh.some((g) => g.project === idle.project && g.folder === null)),
    short: report.short && { ...report.short, folders: report.short.folders.filter((f) => !went(f.project, f.folder)) },
  };
}

export function useStorage(): State & { body: StorageBody | null } {
  const state = useStore(storageStore), gone = useStore(goneStore);
  if (!state.body || !gone.length) return state;
  return { ...state, body: { ...state.body, nodes: state.body.nodes.map((node) =>
    (node.report ? { ...node, report: without(node.report, gone) } : node)) } };
}
