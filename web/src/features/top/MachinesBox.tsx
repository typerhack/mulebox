// The Machines box of the top row. With one or two machines each gets a full row: state,
// Pause, CPU and memory meters, slots, network and what it offers. With more, one line per
// machine scrolling inside the box, and a link to the Machines page at its foot, so the top
// row never changes size with the number of machines. Clicking a machine's name shows that
// machine in CPU, Memory and Disk (docs/design-system.md, More than one machine).

import { ChevronRight, Server } from "lucide-react";

import { ago, percent, plural, soonest } from "../../lib/format";
import type { Machine, MachinesPanel } from "../../lib/types";
import { pick, type Shown } from "../../state/picked";
import { cx } from "../../ui/cx";
import { Meter } from "../../ui/Meter";
import { Empty, Panel } from "../../ui/Panel";
import { QuestionMark } from "../jobs/JobBits";
import { HostMark, MachinePause, MachineState, Net, Offers, Slots, StepMark, isLive } from "../machines/parts";

const FULL_ROWS = 2;

interface RowProps { machine: Machine; panel: MachinesPanel; picked: boolean; now: number }

function PickName({ machine, picked, children }: { machine: Machine; picked: boolean; children?: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={picked} onClick={() => pick(machine.name)}
      title={`Show ${machine.name} in CPU, Memory and Disk`}
      className="group inline-flex min-h-ctl-s touch:min-h-ctl-touch min-w-0 items-center gap-2">
      {children}<strong className="truncate font-semibold group-hover:underline">{machine.name}</strong>
    </button>
  );
}

const pickedLine = "before:absolute before:inset-y-2 before:left-0 before:w-hair before:rounded-hair before:bg-accent";

function FullRow({ machine, panel, picked, now }: RowProps) {
  const alone = soonest(machine.jobs);
  const readings = [["CPU", machine.cpu_pct], ["Mem", machine.mem_pct]]
    .filter((pair): pair is [string, number] => typeof pair[1] === "number");
  return (
    <div className={cx("relative grid gap-2 py-3 first:pt-0", picked && pickedLine, picked && "pl-3")}>
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <span className="inline-flex min-w-0 items-center gap-2">
          <PickName machine={machine} picked={picked} /><HostMark machine={machine} />
          <StepMark machine={machine} notices={panel.notices} />
        </span>
        <span className="inline-flex items-center gap-2"><MachineState machine={machine} /><MachinePause machine={machine} /></span>
      </div>
      <QuestionMark job={alone.job} count={alone.count} />
      {readings.length ? (
        <div className="labels-4 grid gap-1">
          {readings.map(([name, value]) => (
            <Meter key={name} name={name} value={value} text={percent(value)}
              label={`${machine.name} ${name}: ${percent(value)}`} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-ink-2">
          No live data.{isLive(machine) ? "" : ` Last seen ${ago(machine.last_seen, now)}.`}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-sm text-ink-2">
        <Slots machine={machine} /><Net machine={machine} />
      </div>
      <Offers machine={machine} word />
    </div>
  );
}

function SlimRow({ machine, panel, picked }: RowProps) {
  return (
    <div className={cx("relative flex min-h-ctl-touch items-center justify-between gap-2 border-b border-line pl-2",
                       picked && pickedLine, picked && "bg-surface-2")}>
      <span className="inline-flex min-w-0 items-center gap-2">
        <PickName machine={machine} picked={picked}><MachineState machine={machine} iconOnly /></PickName>
        <HostMark machine={machine} /><StepMark machine={machine} notices={panel.notices} />
      </span>
      <span className="inline-flex items-center gap-2"><Slots machine={machine} words={false} /><MachinePause machine={machine} /></span>
    </div>
  );
}

export function MachinesBox({ panel, shown, now }: { panel: MachinesPanel | null; shown: Shown; now: number }) {
  const rows = panel?.machines ?? [];
  const note = panel ? `${panel.online} of ${panel.total} online, ${plural(panel.free_slots, "slot")} free` : "Waiting for data";
  const icon = <Server aria-hidden className="size-icon" />;
  const isPicked = (m: Machine) => !shown.isHost && shown.machine?.name === m.name;
  if (!panel || !rows.length) {
    return (
      <Panel title="Machines" label="Machines" icon={icon} note={note}>
        {panel && <Empty title="No machine has checked in yet." hint="A worker shows here once it asks for its first job." />}
      </Panel>
    );
  }
  if (rows.length <= FULL_ROWS) {
    return (
      <Panel title="Machines" label="Machines" icon={icon} note={note} bodyClassName="divide-y divide-line">
        {rows.map((m) => <FullRow key={m.name} machine={m} panel={panel} picked={isPicked(m)} now={now} />)}
      </Panel>
    );
  }
  return (
    <Panel title="Machines" label="Machines" icon={icon} note={note} bodyClassName="relative min-h-col-m">
      <div className="absolute inset-x-3 top-2 bottom-7 overflow-y-auto">
        {rows.map((m) => <SlimRow key={m.name} machine={m} panel={panel} picked={isPicked(m)} now={now} />)}
      </div>
      <a href="#/machines"
        className="absolute inset-x-3 bottom-2 flex h-ctl-s items-center justify-between border-t border-line-strong text-sm font-medium no-underline hover:underline">
        <span>All {rows.length} machines</span><ChevronRight aria-hidden className="size-icon-s" />
      </a>
    </Panel>
  );
}
