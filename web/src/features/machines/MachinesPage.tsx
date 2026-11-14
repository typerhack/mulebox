// The Machines page: every machine with its state, readings, slots, offers, version and when
// it was last seen, sortable, with its Pause and settings buttons and a way to show it in the top row. On a
// narrow screen each machine is a card and the sort is a select.

import { ChevronDown, ChevronUp, Eye } from "lucide-react";
import { useState } from "react";

import { ago, percent } from "../../lib/format";
import { useStore } from "../../lib/store";
import type { Machine } from "../../lib/types";
import { tickStore, useMachines } from "../../state/live";
import { hostOf, pick, pickStore } from "../../state/picked";
import { IconButton } from "../../ui/Button";
import { MeterBar } from "../../ui/Meter";
import { Empty, Panel } from "../../ui/Panel";
import { NodeSettingsButton } from "./NodeSettings";
import { HostMark, MachinePause, MachineState, Net, Offers, Slots, StepMark, isLive, shownState } from "./parts";

const ORDER = ["busy", "draining", "paused", "dev", "idle", "offline"];
type Sorter = (m: Machine, index: number) => number | string;
const COLUMNS: [string, string, Sorter][] = [
  ["name", "Name", (_, index) => index],
  ["state", "State", (m) => ORDER.indexOf(shownState(m).state)],
  ["cpu", "CPU", (m) => m.cpu_pct ?? -1],
  ["mem", "Memory", (m) => m.mem_pct ?? -1],
  ["net", "Network", (m) => m.net_in_kib_s ?? -1],
  ["slots", "Slots", (m) => (isLive(m) ? m.free_slots : -1)],
  ["offers", "Offers", (m) => m.capabilities.join()],
  ["version", "Version", (m) => m.version ?? ""],
  ["seen", "Last seen", (m) => -(m.last_seen ?? 0)],
];

const Reading = ({ value, label }: { value: number | null | undefined; label: string }) => (typeof value === "number" ? (
  <span className="flex min-w-col-s items-center gap-3">
    <MeterBar className="flex-1" value={value} label={`${label}: ${percent(value)}`} />
    <span className="num min-w-7 text-right text-sm font-medium">{percent(value)}</span>
  </span>
) : <span className="text-ink-2">n/a</span>);

export function MachinesPage() {
  const panel = useMachines();
  const picked = useStore(pickStore);
  useStore(tickStore);
  const [sort, setSort] = useState({ key: "name", dir: 1 });
  const rows = panel?.machines ?? [];
  const now = Date.now() / 1000;
  const shownName = picked ?? hostOf(panel)?.name;
  const sorter = (COLUMNS.find(([key]) => key === sort.key) ?? COLUMNS[0])[2];
  const sorted = rows.map((m, index) => ({ m, by: sorter(m, index) }))
    .sort((a, b) => (a.by > b.by ? 1 : a.by < b.by ? -1 : 0) * sort.dir).map(({ m }) => m);
  const sortBy = (key: string) => setSort((had) => ({ key, dir: had.key === key ? -had.dir : 1 }));
  const show = (m: Machine) => { pick(m.name); window.scrollTo({ top: 0 }); };

  return (
    <Panel title="All machines" label="All machines" strong
      note={(
        <label className="hidden items-center gap-2 font-normal text-ink-2 max-lg:inline-flex">
          Sort by
          <select value={sort.key} onChange={(event) => setSort({ key: event.target.value, dir: 1 })}
            className="h-ctl-touch rounded-m border border-line-strong bg-surface-1 px-2 text-ink-1">
            {COLUMNS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
      )}>
      {!rows.length ? <Empty title={panel ? "No machine has checked in yet." : "Waiting for data"} /> : (
        <div className="overflow-x-auto">
          <table className="data-table stacks">
            <thead>
              <tr>
                {COLUMNS.map(([key, label]) => (
                  <th key={key} scope="col" aria-sort={sort.key === key ? (sort.dir > 0 ? "ascending" : "descending") : "none"}>
                    <button type="button" onClick={() => sortBy(key)}
                      className="inline-flex min-h-ctl-s items-center gap-1 font-semibold hover:text-ink-1">
                      {label}
                      {sort.key === key && (sort.dir > 0 ? <ChevronUp aria-hidden className="size-icon-s" />
                                                         : <ChevronDown aria-hidden className="size-icon-s" />)}
                    </button>
                  </th>
                ))}
                <th scope="col" className="end"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((m) => (
                <tr key={m.name} className={m.name === shownName ? "lg:bg-surface-2" : undefined}>
                  <td className="wide max-lg:text-lg">
                    <span className="inline-flex items-center gap-2 whitespace-nowrap">
                      <strong className="font-semibold">{m.name}</strong><HostMark machine={m} />
                      {m.host && <span className="text-sm font-normal text-ink-2">Dashboard host</span>}
                    </span>
                  </td>
                  <td data-label="State"><MachineState machine={m} /></td>
                  <td data-label="CPU"><Reading value={m.cpu_pct} label={`${m.name} CPU`} /></td>
                  <td data-label="Memory"><Reading value={m.mem_pct} label={`${m.name} memory`} /></td>
                  <td data-label="Network" className="text-sm text-ink-2">
                    {isLive(m) && typeof m.net_in_kib_s === "number" ? <Net machine={m} /> : "n/a"}
                  </td>
                  <td data-label="Slots" className="whitespace-nowrap"><Slots machine={m} /></td>
                  <td data-label="Offers" className="wide"><Offers machine={m} /></td>
                  <td data-label="Version">
                    <span className="inline-flex items-center gap-2">
                      <span className="num">{m.version ?? "-"}</span><StepMark machine={m} notices={panel?.notices} />
                    </span>
                  </td>
                  <td data-label="Last seen" className="num">{ago(m.last_seen, now)}</td>
                  <td className="wide end">
                    <span className="inline-flex items-center gap-2">
                      <IconButton small aria-pressed={m.name === shownName} onClick={() => show(m)}
                        label={`Show ${m.name} in CPU, Memory and Disk`}>
                        <Eye aria-hidden className="size-icon-s" />
                      </IconButton>
                      <MachinePause machine={m} /><NodeSettingsButton machine={m} />
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
