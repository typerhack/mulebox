// Which machine CPU, Memory and Disk show (docs/design-system.md, More than one machine).
// The host is the default and keeps the live stream; any other machine is asked for every
// 2 s while it is picked (`/api/metrics?machine=`). A server from before that route answers
// with the host's samples or a 404: then the panels say there is no per-core data.

import { useEffect, useState } from "react";

import { getJson } from "../lib/api";
import { createStore, useStore } from "../lib/store";
import type { Machine, MachineMetrics, MachinesPanel, Sample } from "../lib/types";
import { samplesStore, useMachines } from "./live";

const ASK_EVERY_MS = 2000;
export const pickStore = createStore<string | null>(null);
export const pick = (name: string | null) => pickStore.set(name);

// The dashboard's own machine: the row the server marks. A server that marks rows and marks
// none has no worker on the dashboard's machine: then there is no host row, only its samples.
// An older server marks nothing: the first online machine stands in, else the first.
export function hostOf(panel: MachinesPanel | null): Machine | null {
  const rows = panel?.machines ?? [];
  if (rows.some((m) => typeof m.host === "boolean")) return rows.find((m) => m.host) ?? null;
  return rows.find((m) => m.state !== "offline") ?? rows[0] ?? null;
}

export interface Shown {
  machine: Machine | null;
  isHost: boolean;
  samples: Sample[];
  // False when the server has no samples for this machine: the panels then fall back to the
  // machine row's own readings.
  detailed: boolean;
  lastSeen: number | null;
}

export function useShown(): Shown {
  const panel = useMachines();
  const name = useStore(pickStore);
  const hostSamples = useStore(samplesStore);
  const host = hostOf(panel);
  const picked = panel?.machines.find((m) => m.name === name) ?? null;
  const remote = picked && picked.name !== host?.name ? picked : null;
  const [reply, setReply] = useState<{ name: string; body: MachineMetrics | null } | null>(null);

  useEffect(() => {
    if (!remote) return undefined;
    const machine = remote.name;
    let gone = false;
    const ask = () => getJson<MachineMetrics>(`/api/metrics?machine=${encodeURIComponent(machine)}`)
      .then((body) => { if (!gone) setReply({ name: machine, body: body.machine === machine ? body : null }); })
      .catch(() => { if (!gone) setReply({ name: machine, body: null }); });
    void ask();
    const timer = setInterval(() => { if (!document.hidden) void ask(); }, ASK_EVERY_MS);
    return () => { gone = true; clearInterval(timer); };
  }, [remote?.name]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (!remote) return { machine: host, isHost: true, samples: hostSamples, detailed: true, lastSeen: host?.last_seen ?? null };
  const body = reply?.name === remote.name ? reply.body : null;
  return { machine: remote, isHost: false, samples: body?.history ?? [], detailed: Boolean(body?.history.length),
           lastSeen: body?.last_seen ?? remote.last_seen ?? null };
}
