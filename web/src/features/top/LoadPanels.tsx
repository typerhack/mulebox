// CPU, Memory and Disk for one machine: the dashboard's host by default, or the machine picked
// in the Machines box (state/picked.ts). Current values are always text too. An offline
// machine keeps the panels' shape and says when it was last seen.

import { ArrowLeft, Cpu, HardDrive, MemoryStick } from "lucide-react";

import { ago, bytes, percent } from "../../lib/format";
import type { Sample } from "../../lib/types";
import { WINDOW_S } from "../../state/live";
import { pick, type Shown } from "../../state/picked";
import { Graph } from "../../ui/Graph";
import { Meter } from "../../ui/Meter";
import { Fact, Panel } from "../../ui/Panel";
import { HostMark } from "../machines/parts";
import { CpuCores, ViewSwitch, compactable, useCpuView, useWide } from "./CpuCores";

const average = (cpu: number[] | null | undefined) =>
  (cpu?.length ? cpu.reduce((a, b) => a + b, 0) / cpu.length : null);
const lastWith = <K extends keyof Sample>(samples: Sample[], key: K) =>
  samples.findLast((s) => s[key] !== null && s[key] !== undefined)?.[key] ?? null;

function Scope({ shown, back }: { shown: Shown; back?: boolean }) {
  const name = shown.machine?.name;
  return (
    <>
      <span className="inline-flex items-center gap-1 text-sm whitespace-nowrap">
        {name && <strong className="font-semibold">{name}</strong>}<HostMark machine={shown.machine} />
      </span>
      {back && (shown.isHost
        ? <span className="text-sm whitespace-nowrap text-ink-2">Dashboard host</span>
        : (
          <button type="button" onClick={() => pick(null)} title="Show the dashboard host again"
            className="-my-1 inline-flex h-ctl-s touch:h-ctl-touch items-center gap-2 rounded-m border border-line-strong bg-surface-1 px-2 text-sm font-medium whitespace-nowrap hover:border-ink-1 hover:bg-surface-3">
            <ArrowLeft aria-hidden className="size-icon-s" />Back to host
          </button>
        ))}
    </>
  );
}

const Quiet = ({ children }: { children: string }) => (
  <p className="grid min-h-graph flex-1 place-items-center rounded-m border border-dashed border-line-strong p-3 text-center text-sm text-ink-2">
    {children}
  </p>
);

function offlineText(shown: Shown, now: number): string | null {
  const m = shown.machine;
  if (!m || m.state !== "offline") return null;
  return `No live data. ${m.name} was last seen ${ago(shown.lastSeen, now)}.`;
}

export function CpuPanel({ shown, now }: { shown: Shown; now: number }) {
  const { samples, machine } = shown;
  const cores = lastWith(samples, "cpu") ?? [];
  const offline = offlineText(shown, now);
  const overall = average(cores) ?? (shown.isHost ? null : machine?.cpu_pct ?? null);
  const count = cores.length || machine?.cores || 0;
  const [view, setView] = useCpuView();
  const wide = useWide();
  const text = offline ? "No live data" : overall === null ? "Waiting for the first sample"
    : `${count ? `${count} cores, ` : ""}${percent(overall)} now`;
  const note = !offline && compactable(cores.length, wide)
    ? <span className="inline-flex items-center gap-2">{text}<ViewSwitch view={view} set={setView} /></span> : text;
  return (
    <Panel title="CPU" label="CPU" icon={<Cpu aria-hidden className="size-icon" />} note={note}
      head={<Scope shown={shown} back />} bodyClassName="flex flex-col gap-3">
      {offline ? <Quiet>{offline}</Quiet> : cores.length ? (
        <>
          <Graph className="flex-1" points={samples.map((s) => ({ t: s.t, v: average(s.cpu) }))} max={100}
            windowS={WINDOW_S} format={percent} scale="Last 5 min, 0 to 100%"
            label={`Average CPU${machine ? ` of ${machine.name}` : ""}, last 5 minutes: ${overall === null ? "-" : percent(overall)}`} />
          <CpuCores cores={cores} view={view} machine={machine?.name ?? ""} />
        </>
      ) : (
        <>
          <Quiet>{shown.isHost ? "Waiting for the first sample." : "No per-core data from this machine."}</Quiet>
          {typeof overall === "number" && (
            <Meter name="All" value={overall} text={percent(overall)} label={`CPU, all cores: ${percent(overall)}`} />
          )}
        </>
      )}
    </Panel>
  );
}

const orNa = <T,>(value: T | null, show: (v: T) => string) => (value === null ? "n/a" : show(value));

// Host only: what mulebox runs for jobs (job units, busy runners and their containers) and swap.
const swapText = (swap: Sample["swap"]) =>
  !swap ? "n/a" : swap.total ? `${bytes(swap.used)} of ${bytes(swap.total)}` : "Off";

export function MemoryPanel({ shown, now }: { shown: Shown; now: number }) {
  const { samples, machine } = shown;
  const memory = lastWith(samples, "memory");
  const offline = offlineText(shown, now);
  const pct = memory ? (100 * memory.used) / memory.total : shown.isHost ? null : machine?.mem_pct ?? null;
  const note = offline ? "No live data" : memory ? `${bytes(memory.used)} of ${bytes(memory.total)}`
    : pct === null ? "Not available" : `${percent(pct)} used`;
  return (
    <Panel title="Memory" label="Memory" icon={<MemoryStick aria-hidden className="size-icon" />} note={note}
      head={<Scope shown={shown} />} bodyClassName="flex flex-col gap-2">
      <Meter name="Used" value={offline ? null : pct} text={offline || pct === null ? "n/a" : percent(pct)}
        label={`Memory used: ${note}`} />
      {shown.isHost ? (
        <>
          <Fact name={<span title="Memory of running jobs, their containers and GitHub runners busy with a job">Jobs</span>}>{orNa(lastWith(samples, "jobs_memory"), bytes)}</Fact>
          <Fact name="Swap">{swapText(lastWith(samples, "swap"))}</Fact>
        </>
      ) : <Fact name="Available">{memory && !offline ? bytes(memory.available) : "n/a"}</Fact>}
      {memory && !offline && (
        <Graph small className="flex-1" points={samples.map((s) => ({ t: s.t, v: s.memory?.used ?? null }))}
          max={memory.total} windowS={WINDOW_S} format={bytes} scale="Last 5 min, 0 to total"
          label="Memory used, last 5 minutes" />
      )}
    </Panel>
  );
}

export function DiskPanel({ shown, now }: { shown: Shown; now: number }) {
  const { samples } = shown;
  const disks = lastWith(samples, "disk") ?? [];
  const last = samples.at(-1);
  const offline = offlineText(shown, now);
  const tightest = [...disks].sort((a, b) => a.free - b.free)[0];
  const note = offline ? "No live data" : tightest ? `${bytes(tightest.free)} free` : "Not measured yet";
  return (
    <Panel title="Disk" label="Disk" icon={<HardDrive aria-hidden className="size-icon" />} note={note}
      head={<Scope shown={shown} />} bodyClassName="flex flex-col gap-2">
      {!offline && disks.map((disk) => {
        const used = disk.total ? (100 * disk.used) / disk.total : 0;
        const roots = disk.roots.join(", ");
        return (
          <div key={roots} className="grid gap-1">
            <p className="truncate text-sm text-ink-2" title={`Holds ${roots}`}>{roots}</p>
            <Meter className="labels-none" name="" value={used} text={`${bytes(disk.used)} of ${bytes(disk.total)}`}
              label={`Disk holding ${roots}: ${percent(used)} used`} />
          </div>
        );
      })}
      {shown.isHost && (
        <>
          <Fact name={<span title="Disk used by Docker: images, containers, volumes and build cache">Docker</span>}>{orNa(lastWith(samples, "docker_disk"), bytes)}</Fact>
          <Fact name="Containers">{last?.docker === null || last?.docker === undefined ? "n/a" : `${last.docker} running`}</Fact>
          <Fact name="Overhead">{last?.self ? `${last.self.cpu.toFixed(1)}% of a core, ${bytes(last.self.rss)}` : "-"}</Fact>
          <Fact name="Viewers">{last?.viewers ?? "-"}</Fact>
        </>
      )}
      {!shown.isHost && !offline && !disks.length && <p className="text-sm text-ink-2">No disk data from this machine.</p>}
    </Panel>
  );
}
