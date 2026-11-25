// The rows of the Usage page (docs/design-system/usage/, option A): a node's heading, then a
// row per job with its cores and its memory as ranges on that node, and the size that fits
// every run. Heaviest first. A gap is said in words after a dashed circle, never drawn as zero.

import { ArrowDownWideNarrow, CircleDashed, Cpu, Laptop, MemoryStick, Server, Workflow } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

import { bytes, nameParts, plural } from "../../lib/format";
import { historyHash } from "../../lib/history";
import type { Job, Machine } from "../../lib/types";
import { coreUnit, coresWord, memoryUnit, one, part, whyNot, sendsNoUsage, type NodeGroup, type NodeSize, type Spread,
         type UsageJob } from "../../lib/usage";
import { WithCode } from "../../ui/Code";

interface RangeProps { spread: Spread; whole: number; unit: number; fit: number | null; label: string }

// The track is the whole node; solid to the usual peak, soft to the highest, a tick at the size.
export function Range({ spread, whole, unit, fit, label }: RangeProps) {
  const style = { "--med": part(spread.median, whole), "--hi": part(spread.max, whole), "--unit": part(unit, whole),
                  "--at": part(fit ?? 0, whole) } as CSSProperties;
  return (
    <div className="use-range" role="img" aria-label={label} title={label} style={style}>
      <i className="hi" /><i className="med" />{fit !== null && <i className="fit" />}
    </div>
  );
}

const Gap = ({ children, wide }: { children: ReactNode; wide?: boolean }) => (
  <p className={`flex items-start gap-2 text-sm text-ink-2 ${wide ? "use-wide" : ""}`}>
    <CircleDashed aria-hidden className="mt-px size-icon-s flex-none" /><span>{children}</span>
  </p>
);

interface MeasureProps { name: string; of: string; spread: Spread; whole: number | null | undefined; unit: number; fit: number | null;
                         say: (n: number) => string }

function Measure({ name, of, spread, whole, unit, fit, say }: MeasureProps) {
  return (
    <div className="grid min-w-0 gap-1">
      <span className="use-lab text-sm text-ink-2">{name}{of}</span>
      {whole ? <Range spread={spread} whole={whole} unit={unit} fit={fit}
        label={`${name}: usually ${say(spread.median)}, at most ${say(spread.max)}${of}`} /> : null}
      <p className="text-sm text-ink-2"><b className="num font-semibold text-ink-1">{say(spread.max)}</b> at most, <span className="num">{say(spread.median)}</span> usually</p>
    </div>
  );
}

const ofCores = (size: NodeSize) => (size.cores ? `, of ${size.cores}` : "");
const ofMemory = (size: NodeSize) => (size.memory ? `, of ${bytes(size.memory)}` : "");

function Row({ job, node, size, version, all }: { job: UsageJob; node: string; size: NodeSize; version?: string | null; all: boolean }) {
  const ci = job.kind === "runner";
  const [project, name] = nameParts({ job_id: "", state: "finished", kind: job.kind, project: job.project, job: job.job } as Job);
  const Icon = ci ? Workflow : Laptop;
  const counted = `${plural(job.runs, all ? "run" : "passed run")}, ${ci ? "GitHub run" : "agent job"}`
    + (job.measured && job.not_measured ? `, ${job.measured} measured` : "");
  const fits = job.fits;
  return (
    <li className="use-row">
      <div className="use-name flex min-w-0 flex-wrap items-center gap-x-2" title={ci ? "A GitHub run's job" : "An agent's job"}>
        <Icon aria-hidden className="size-icon-s flex-none text-ink-2" />
        <a href={historyHash({ project: job.project ?? "", job: job.job ?? "", kind: job.kind })}
          className="min-w-0 font-semibold break-words no-underline hover:underline">
          {project}{name && <> <span className="font-normal text-ink-3">/</span> {name}</>}
        </a>
        <small className="num text-sm text-ink-2">{counted}</small>
      </div>
      {!job.measured || (!job.cores && !job.memory) ? (
        <Gap wide>
          <WithCode text={`Not measured: ${whyNot(node, version, "these runs")}.${sendsNoUsage(version) ? ` \`mulebox setup ${node}\` upgrades it.` : ""}`} />
        </Gap>
      ) : (
        <>
          {job.cores ? <Measure name="Cores" of={ofCores(size)} spread={job.cores} whole={size.cores} unit={coreUnit(size.cores ?? 1)}
            fit={fits?.cores ?? null} say={one} />
            : <Gap>Cores: too short to measure. Its runs end before two readings, 20 s.</Gap>}
          {job.memory ? <Measure name="Memory" of={ofMemory(size)} spread={job.memory} whole={size.memory} unit={memoryUnit(size.memory ?? 1)}
            fit={fits?.memory ?? null} say={bytes} />
            : <Gap>Memory was not measured.</Gap>}
          <p className="use-fit min-w-0 font-semibold">
            <span className="use-lab text-sm font-normal text-ink-2">Fits every run</span>
            {fits?.cores ? <span className="num">{size.cores ? `${fits.cores} of ${coresWord(size.cores)}` : coresWord(fits.cores)}</span>
              : <span className="text-sm font-normal text-ink-2">cores not known</span>}
            {fits?.memory ? <span className="num">{bytes(fits.memory)}</span> : null}
          </p>
        </>
      )}
    </li>
  );
}

const SYSTEMS: Record<string, string> = { linux: "Linux", macos: "macOS" };

// A node's heading, its column names, and its jobs.
export function NodeRows({ group, machine, all }: { group: NodeGroup; machine: Machine | undefined; all: boolean }) {
  const { name, size, jobs } = group;
  const system = machine?.capabilities.map((offer) => SYSTEMS[offer]).find(Boolean);
  const facts = [system, size.cores ? coresWord(size.cores) : null, size.memory ? `${bytes(size.memory)} memory` : null].filter(Boolean);
  return (
    <section aria-label={name} className="min-w-0">
      <div className="use-node">
        <h3 className="inline-flex items-center gap-2 text-lg font-semibold"><Server aria-hidden className="size-icon text-ink-2" />{name}</h3>
        <span className="text-sm text-ink-2">{facts.length ? facts.join(", ") : "its size is not known: it has not reported"}</span>
        <span className="num ml-auto inline-flex items-center gap-1 text-sm text-ink-2">
          <ArrowDownWideNarrow aria-hidden className="size-icon-s" />{jobs.length === 1 ? "1 job" : `${jobs.length} jobs, heaviest first`}
        </span>
      </div>
      <div className="use-head" aria-hidden>
        <span>Job</span>
        <span className="inline-flex items-center gap-2"><Cpu className="size-icon-s" />Cores{ofCores(size)}</span>
        <span className="inline-flex items-center gap-2"><MemoryStick className="size-icon-s" />Memory{ofMemory(size)}</span>
        <span>Fits every run</span>
      </div>
      <ul>
        {jobs.map((job) => <Row key={`${job.kind}/${job.project}/${job.job}`} job={job} node={name} size={size} version={machine?.version} all={all} />)}
      </ul>
    </section>
  );
}
