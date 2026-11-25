// What a run used, on its page (docs/design-system/usage/, option B): each peak as one line
// under the stage it happened in, the average as the panel's last line, and the share of the
// node at which the Cores meter gets its tick while the job runs. A GitHub run has one bar, so
// both lines sit under it and name the step. A gap is said in words, never drawn as zero.

import { CircleDashed, Cpu, MemoryStick } from "lucide-react";
import type { ReactNode } from "react";

import { duration } from "../../lib/format";
import { coresOf, memoryOf, one, readings, whyNot, type NodeSize, type RunBody } from "../../lib/usage";

export interface Used {
  under: Map<number, ReactNode>;   // the lines, by the row they sit under
  foot: ReactNode;
  peakShare: number | null;        // the peak so far as a share of the node's cores, 0 to 100
  peakText: string | null;
}

const NOTHING: Used = { under: new Map(), foot: null, peakShare: null, peakText: null };

const Line = ({ icon, bold, rest }: { icon: ReactNode; bold: string; rest: string }) => (
  <p className="stage-peak">{icon}<span><b className="font-semibold text-ink-1">{bold}</b>{rest}</span></p>
);

const Gap = ({ children }: { children: ReactNode }) => (
  <p className="flex items-start gap-2 border-t border-line pt-2 text-sm text-ink-2">
    <CircleDashed aria-hidden className="mt-px size-icon-s flex-none" /><span>{children}</span>
  </p>
);

// `stages`: the names of the rows drawn, in order. `single`: a GitHub run's one bar.
export function usedOf(body: RunBody | null, stages: string[], single: boolean, version?: string | null): Used {
  if (!body || !stages.length) return NOTHING;
  const run = body.run, peaks = run.usage ?? {}, live = run.state !== "finished";
  const size: NodeSize = (run.worker && body.machines[run.worker]) || {};
  const count = peaks.samples ?? 0, soFar = live ? " so far" : "";
  if (!count && peaks.peak_memory == null && peaks.peak_cores == null) {
    // A running job has not been read yet; a finished one never was.
    return live ? NOTHING : { ...NOTHING, foot: <Gap>Cores and memory were not measured: {whyNot(run.worker, version, "this run")}.</Gap> };
  }
  const rowOf = (stage: string | null | undefined) => (single ? 0 : stages.lastIndexOf(stage ?? ""));
  // A stage the panel does not draw: the line goes under the last row and names the stage.
  const where = (stage: string | null | undefined) => (stage && (single || rowOf(stage) < 0) ? `, in ${stage}` : "");
  const lines = new Map<number, ReactNode[]>();
  const put = (stage: string | null | undefined, line: ReactNode) => {
    const at = rowOf(stage) < 0 ? stages.length - 1 : rowOf(stage);
    lines.set(at, [...(lines.get(at) ?? []), line]);
  };
  if (typeof peaks.peak_cores === "number") {
    put(peaks.peak_cores_stage, <Line key="cores" icon={<Cpu aria-hidden className="size-icon-s" />}
      bold={coresOf(peaks.peak_cores, size)} rest={`, its busiest 10 s${soFar}${where(peaks.peak_cores_stage)}`} />);
  }
  if (typeof peaks.peak_memory === "number") {
    put(peaks.peak_memory_stage, <Line key="memory" icon={<MemoryStick aria-hidden className="size-icon-s" />}
      bold={memoryOf(peaks.peak_memory, size)} rest={`, the most it held${soFar}${where(peaks.peak_memory_stage)}`} />);
  }
  const tail = single ? " The cores count the run's Compose containers." : "";
  const foot = typeof peaks.peak_cores !== "number"
    ? (live ? null : <Gap>Too short to measure cores: it ended before two readings. Memory from {readings(count)}.</Gap>)
    : (
      <p className="border-t border-line pt-2 text-sm text-ink-2">
        {typeof run.average_cores === "number" && (
          <><b className="font-semibold text-ink-1">{one(run.average_cores)} cores on average</b> over {duration(run.run_s)}{soFar}, from </>
        )}
        {typeof run.average_cores === "number" ? readings(count) : `From ${readings(count)}`}.{tail}
      </p>
    );
  const peak = live && typeof peaks.peak_cores === "number" ? peaks.peak_cores : null;
  return {
    under: new Map([...lines].map(([at, found]) => [at, <>{found}</>])), foot,
    peakShare: peak !== null && size.cores ? (100 * peak) / size.cores : null,
    peakText: peak !== null ? one(peak) : null,
  };
}
