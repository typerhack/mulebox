// The Stages panel: the waterfall of lib/timeline.ts, its axis and key, and the cores the job
// uses now. For a GitHub run, whose stages GitHub keeps, one bar for the whole run. What the
// run used (UsageLines.tsx) is written under the stage of each peak, and as the last line.

import type { CSSProperties, ReactNode } from "react";

import { coresText } from "../../lib/doing";
import { duration, roughly } from "../../lib/format";
import { timeline, type StageRow } from "../../lib/timeline";
import type { Job, JobDetail } from "../../lib/types";
import type { RunBody } from "../../lib/usage";
import { Meter } from "../../ui/Meter";
import { Panel } from "../../ui/Panel";
import { Status } from "../../ui/Status";
import { usedOf, type Used } from "./UsageLines";

const share = (part: number, whole: number) => `${((100 * part) / whole).toFixed(2)}%`;

function Row({ row, scale, under }: { row: StageRow; scale: number; under?: ReactNode }) {
  const bar = { "--from": share(row.from, scale), "--len": share(row.length, scale) } as CSSProperties;
  const tick = row.usualAt === null ? null : ({ "--at": share(row.usualAt, scale) } as CSSProperties);
  return (
    <li title={row.tip} className="grid gap-1">
      <div className="stage">
        <span className="inline-flex min-w-0 items-center gap-2 whitespace-nowrap">
          <Status state={row.state} iconOnly size="s" /><span className="truncate">{row.name}</span>
        </span>
        <div className="stage-track" role="img" aria-label={row.tip}>
          <i className="stage-bar" data-tone={row.state === "failed" ? "failed" : undefined} style={bar} />
          {tick && <i className="stage-usual" style={tick} />}
        </div>
        <span className="num text-right text-sm text-ink-2">{row.took}</span>
      </div>
      {row.extra && (row.extra.code
        ? <code className="block truncate text-xs text-ink-1" title={row.extra.text}>{row.extra.text}</code>
        : <p className="text-sm text-ink-2">{row.extra.text}</p>)}
      {under}
    </li>
  );
}

const Tick = () => <i className="block h-3 w-hair bg-ink-1" />;
// `usual`: the stages carry the tick; `peak`: the Cores meter does.
const Key = ({ usual, peak }: { usual: boolean; peak: boolean }) => (usual || peak ? (
  <p className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-2">
    <span className="inline-flex items-center gap-2"><i className="block h-meter w-4 rounded-meter bg-meter-fill" />This run</span>
    {usual && <span className="inline-flex items-center gap-2"><Tick />Where it usually ends</span>}
    {peak && <span className="inline-flex items-center gap-2"><Tick />On Cores: its peak so far</span>}
  </p>
) : null);

const pctOf = (live: Job | null) => live?.doing?.cpu_pct;
const metered = (live: Job | null, cores: number | null | undefined) => typeof pctOf(live) === "number" && Boolean(cores);

function Cores({ live, cores, use }: { live: Job | null; cores: number | null | undefined; use: Used }) {
  const pct = pctOf(live);
  if (typeof pct !== "number" || !cores) return null;
  const peak = use.peakText ? `, its peak so far ${use.peakText}` : "";
  return <Meter name="Cores" value={pct / cores} mark={use.peakShare} text={coresText(pct)} label={`Cores this job uses: ${coresText(pct)} of ${cores}${peak}`} />;
}

// `used`: what the run used, once asked (useRunUsage.ts); `version`: the mulebox of its node.
interface Props { job: JobDetail; live: Job | null; cores: number | null | undefined; now: number; used?: RunBody | null; version?: string | null }

export function StagesPanel({ job, live, cores, now, used, version }: Props) {
  const made = timeline(job, now);
  if (!made) {
    return (
      <Panel title="Stages" label="Stages" strong>
        <p className="text-sm text-ink-2">{job.state === "finished" ? "No stages were recorded." : "No stage has started yet."}</p>
      </Panel>
    );
  }
  const note = `${duration(made.elapsed)}${made.running ? " so far" : ""}${made.usual ? ` of usually ${roughly(made.usual)}` : ""}`;
  const use = usedOf(used ?? null, made.rows.map((row) => row.name), false, version);
  return (
    <Panel title="Stages" label="Stages" note={note} strong bodyClassName="grid gap-3">
      <ol className="grid gap-2">
        {made.rows.map((row, index) => <Row key={`${row.name}-${index}`} row={row} scale={made.scale} under={use.under.get(index)} />)}
      </ol>
      <div className="stage text-xs text-ink-3" aria-hidden>
        <span />
        <div className="num flex justify-between">{made.axis.map((text, index) => <span key={index}>{text}</span>)}</div>
        <span />
      </div>
      <Key usual peak={use.peakShare !== null && metered(live, cores)} />
      <Cores live={live} cores={cores} use={use} />
      {use.foot}
    </Panel>
  );
}

// A GitHub run: how long it has run beside what its job usually takes, and its cores, which
// count the run's Compose containers.
export function RunTimePanel({ job, live, cores, now, used, version }: Props) {
  const started = job.started_at ?? job.created_at ?? now;
  const elapsed = Math.max(0, (job.finished_at ?? now) - started);
  const usual = live?.usual_s ?? null;
  const scale = Math.max(elapsed, usual ?? 0, 1);
  const running = job.state !== "finished";
  // The run's own result from the runner's diary; an older slot without one was only released.
  const end = job.ci_result?.outcome;
  const state: StageRow["state"] = running ? "running"
    : end === "passed" || end === "failed" || end === "cancelled" ? end : "released";
  const row: StageRow = {
    name: "CI run", state, from: 0, length: elapsed, usualAt: usual,
    took: duration(elapsed), extra: null,
    tip: `This run: ${duration(elapsed)}${running ? " so far" : ""}${usual ? `, usually ${duration(usual)}` : ""}`,
  };
  const use = usedOf(used ?? null, [row.name], true, version);
  return (
    <Panel title="Time" label="Time" strong bodyClassName="grid gap-3"
      note={`${duration(elapsed)}${usual ? ` of usually ${roughly(usual)}` : ""}`}>
      <ol><Row row={row} scale={scale} under={use.under.get(0)} /></ol>
      <Key usual={Boolean(usual)} peak={use.peakShare !== null && metered(live, cores)} />
      <Cores live={live} cores={cores} use={use} />
      {use.foot ?? (running && <p className="text-sm text-ink-2">The cores count the run's Compose containers.</p>)}
    </Panel>
  );
}
