// The Health tab of a node's settings window (the user's pick, option C's tab of
// design-system/resting/): its state and Check now, every check it runs with what it found, the
// failing ones with their fix, and its one setting, the least free space before it rests.

import { CircleCheck, HardDrive, OctagonAlert } from "lucide-react";
import { useId } from "react";

import { bytes, clockTime } from "../../lib/format";
import { checkRows, healthOf, isResting, isSick, sentence } from "../../lib/health";
import { MIN_FREE_DEFAULT, memoryGb, rowOf, type Draft, type NodeSettings, type SettingKey } from "../../lib/nodeSettings";
import type { Machine } from "../../lib/types";
import { WithCode } from "../../ui/Code";
import { cx } from "../../ui/cx";
import { Panel } from "../../ui/Panel";
import { Status } from "../../ui/Status";
import { Stepper } from "../../ui/Stepper";
import { CheckNow } from "./Health";
import { ROWS, Row, RunsWith, meaning } from "./SettingsRows";

interface Props {
  machine: Machine;
  view: NodeSettings;
  draft: Draft;
  locked: boolean;
  busy: boolean;
  onEdit: (change: Draft) => void;
  onDrop: (key: SettingKey) => void;
}

const LOW_SHARE_LINE = 10_000_000_000;
const spaced = (size: string | null | undefined) => String(size ?? "-").replace(/(\d)([A-Z])/, "$1 $2");  // "5GB": "5 GB"

function Summary({ machine }: { machine: Machine }) {
  const health = healthOf(machine), rows = checkRows(health);
  const failing = rows.filter((row) => row.problem).length;
  if (!health) {
    return <p className="text-ink-2">{machine.state === "offline" ? `${machine.name} is offline; its checks show when it is back.`
      : `${machine.name} runs a mulebox older than 1.41, which does not check itself.`}</p>;
  }
  const since = Math.min(...health.problems.map((p) => p.since));
  return (
    <div className="grid gap-2">
      <p className="inline-flex items-center gap-2 text-lg font-semibold">
        {isResting(machine) ? <Status state="resting" word={`Resting since ${clockTime(since)}`} size="l" />
          : isSick(machine) ? <Status state="warning" word={`Holds back some jobs since ${clockTime(since)}`} size="l" />
          : <Status state="passed" word="Every check passes" size="l" />}
      </p>
      <p className="text-sm text-ink-2">
        {failing ? `${failing} of ${rows.length} checks ${failing === 1 ? "fails" : "fail"}. It checks again every minute until all pass, and takes jobs as soon as they do.`
          : "It checks itself every five minutes, at once when a job could not start, and when asked."}
      </p>
      <CheckNow machine={machine} />
    </div>
  );
}

export function HealthTab({ machine, view, draft, locked, busy, onEdit, onDrop }: Props) {
  const rows = checkRows(healthOf(machine)), says = useId();
  const floor = rowOf(view, draft, "min_free"), reported = view.current?.min_free !== undefined;
  const gb = memoryGb(floor.yours ?? MIN_FREE_DEFAULT) ?? 5;
  const max = view.choices?.min_free?.max_gb ?? 1000, total = machine.disk_total;
  const warnAt = total ? Math.max(LOW_SHARE_LINE, total * 0.1) : LOW_SHARE_LINE;
  return (
    <div className="grid gap-3">
      <Summary machine={machine} />
      {rows.length > 0 && (
        <ul aria-label={`The checks of ${machine.name}`} className="divide-y divide-line border-y border-line">
          {rows.map((row) => (
            <li key={row.check} className="flex items-start gap-3 py-2">
              {row.problem ? <OctagonAlert aria-hidden className="status-icon mt-px size-icon flex-none text-danger" />
                : <CircleCheck aria-hidden className="status-icon mt-px size-icon flex-none text-passed" />}
              <div className="grid min-w-0 gap-1">
                <p>
                  <strong className="font-semibold">{row.name}</strong>{" "}
                  <span className={cx("text-sm", row.problem ? "num" : "text-ink-2")}>
                    {row.problem ? `fails since ${clockTime(row.problem.since)}` : row.passes}
                  </span>
                </p>
                {row.problem && (
                  <p className="text-sm">
                    {sentence(row.problem.message)}{" "}
                    <span className="text-ink-2"><WithCode text={sentence(row.problem.fix)} /></span>
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {reported && (
        <Panel subgrid title="Least free space" label="Least free space" icon={<HardDrive aria-hidden className="size-icon" />} bodyClassName={ROWS}>
          {meaning(`Under this, ${machine.name} rests: a job needs room to check out and install.`)}
          <Row label="Suggested" note="the default for every node"><span className="num font-medium">5 GB</span></Row>
          <Row label="Yours" noteId={says}
            note={`You are warned long before, under ${bytes(warnAt)} free${total ? ` of ${bytes(total)}` : ""}, and its cleanup runs then.`}>
            <Stepper value={gb} min={view.choices?.min_free?.min_gb ?? 1} max={max} label="Least free space" unit="GB" units="GB"
              disabled={locked || busy} onChange={(next) => onEdit({ min_free: `${next}GB` })} />
          </Row>
          <RunsWith now={floor.now === null ? null : spaced(floor.now)} yours={spaced(floor.yours)} mark={floor.mark}
            online={view.online} same={floor.now === MIN_FREE_DEFAULT} drop={() => onDrop("min_free")} busy={busy} />
        </Panel>
      )}
    </div>
  );
}
