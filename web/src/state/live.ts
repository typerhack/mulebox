// The page's live data: one event stream (`/api/events`) into small stores. Views read the
// stores; nothing else asks for the queue, the machines or the host's samples.

import { actionToken, getJson } from "../lib/api";
import { liveStream } from "../lib/live";
import { createStore, useStore } from "../lib/store";
import type { MachinesPanel, QueueSnapshot, Sample } from "../lib/types";

export const MAX_SAMPLES = 150;  // the server keeps 5 minutes of samples
export const WINDOW_S = 300;

export interface QueueState {
  snapshot: QueueSnapshot | null;
  at: number;  // performance.now() when it came, so times tick from it
}
export type Conn = { state: "connecting" | "live" | "lost"; text: string };

export const queueStore = createStore<QueueState>({ snapshot: null, at: 0 });
export const machinesStore = createStore<MachinesPanel | null>(null);
export const samplesStore = createStore<Sample[]>([]);
export const connStore = createStore<Conn>({ state: "connecting", text: "Connecting" });
export const healthStore = createStore<{ version?: string; sign_in?: boolean }>({});
// Whole seconds since the page opened; the one clock every ticking time reads.
export const tickStore = createStore(0);

const parse = <T,>(event: MessageEvent<string>) => JSON.parse(event.data) as T;

async function sessionEnded() {
  const reply = await fetch("/healthz").catch(() => null);
  if (reply?.status === 401) window.location.assign("/login");
  else connStore.set({ state: "lost", text: "Closed; reload the page" });
}

export function startLive(): () => void {
  const stop = liveStream(() => "/api/events", {
    queue: (event) => queueStore.set({ snapshot: parse<QueueSnapshot>(event), at: performance.now() }),
    machines: (event) => machinesStore.set(parse<MachinesPanel>(event)),
    metrics: (event) => samplesStore.set((samples) => [...samples, parse<Sample>(event)].slice(-MAX_SAMPLES)),
    metrics_history: (event) => samplesStore.set(parse<{ history: Sample[] }>(event).history.slice(-MAX_SAMPLES)),
  }, {
    opened: () => connStore.set({ state: "live", text: "Live" }),
    lost: (closed) => {
      connStore.set({ state: "lost", text: "Reconnecting" });
      // The browser retries a dropped connection by itself, but gives up on a refused one.
      if (closed) void sessionEnded();
    },
  });
  const clock = setInterval(() => { if (!document.hidden) tickStore.set((n) => n + 1); }, 1000);
  void actionToken();
  getJson<{ version?: string; sign_in?: boolean }>("/healthz").then((health) => healthStore.set(health))
    .catch(() => undefined);
  return () => { stop(); clearInterval(clock); };
}

export const useQueue = () => useStore(queueStore, (state) => state.snapshot);
export const useMachines = () => useStore(machinesStore);

// Seconds since the queue snapshot came, moving once a second: what a ticking time adds.
export function useAge(): number {
  useStore(tickStore);
  const at = useStore(queueStore, (state) => state.at);
  return at ? (performance.now() - at) / 1000 : 0;
}

export async function signOut() {
  await fetch("/logout", { method: "POST" }).catch(() => undefined);
  window.location.assign("/login");
}
