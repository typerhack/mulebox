// A node's own checks on the page (docs/design.md, A node that rests; lib/health.ts). The
// strip says each problem once, with the node's fix and Check now; a node with one part down
// gets a small triangle beside its name; the Machines page a second row under the node.

import { HardDrive, OctagonAlert, Stethoscope, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { controlMachine, problemText, tokenStore } from "../../lib/api";
import { bytes, clockTime } from "../../lib/format";
import { checkedText, headline, healthOf, isResting, isSick, lowDisk, problemsOf, sentence } from "../../lib/health";
import { useStore } from "../../lib/store";
import type { Machine } from "../../lib/types";
import { tickStore } from "../../state/live";
import { Button, LinkButton } from "../../ui/Button";
import { WithCode } from "../../ui/Code";
import { cx } from "../../ui/cx";
import { Tip } from "../../ui/Tip";

const ANSWER_WAIT_MS = 60_000;  // the node answers at its next claim or heartbeat, then checks

// Check now: the node checks itself at once (`mulebox machine check`). The button waits until
// the node's report counts one more answer, and says when it checked and checks again.
export function CheckNow({ machine, children }: { machine: Machine; children?: React.ReactNode }) {
  const token = useStore(tokenStore);
  useStore(tickStore);
  const health = healthOf(machine), answers = health?.answers ?? 0;
  const [asked, setAsked] = useState<number | null>(null);   // the answers counted when asked
  const [answered, setAnswered] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const waiting = asked !== null && answers <= asked;
  useEffect(() => {
    if (asked !== null && answers > asked) { setAsked(null); setAnswered(true); }
  }, [answers, asked]);
  useEffect(() => {
    if (!waiting) return;
    const timer = setTimeout(() => { setAsked(null); setProblem(`${machine.name} did not answer yet; it checks again on its own.`); },
                             ANSWER_WAIT_MS);
    return () => clearTimeout(timer);
  }, [waiting, machine.name]);
  const ask = async () => {
    setProblem(null);
    setAnswered(false);
    setAsked(answers);
    try {
      await controlMachine(machine.name, "check");
    } catch (failure) {
      setAsked(null);
      setProblem(`Not asked. ${problemText(failure)}`);
    }
  };
  const when = checkedText(health, Date.now() / 1000);
  const said = problem ?? (waiting ? `Asked ${machine.name} to check` : `${answered && isSick(machine) ? "Still failing, " : ""}${when}`);
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
      {token && (
        <Button disabled={waiting} onClick={() => void ask()}>
          <Stethoscope aria-hidden className="size-icon-s" />{waiting ? "Checking" : "Check now"}
        </Button>
      )}
      {children}
      <span role="status" className="num text-sm text-ink-2">{said}</span>
    </span>
  );
}

// Option B's mark: a node that holds back Docker or Xcode, with the strip above saying why.
export function HealthMark({ machine }: { machine: Machine }) {
  if (!isSick(machine) || isResting(machine)) return null;
  const text = `${headline(machine)}: see the strip above`;
  return (
    <Tip text={text}>
      <span role="img" aria-label={headline(machine)} className="inline-grid place-items-center">
        <TriangleAlert aria-hidden className="status-icon size-icon-s text-warning" />
      </span>
    </Tip>
  );
}

const since = (machine: Machine) => Math.min(...problemsOf(machine).map((p) => p.since));
const hasDisk = (machine: Machine) => problemsOf(machine).some((p) => p.check === "disk");

// What is wrong and what to do: the node's own sentences.
function Problems({ machine }: { machine: Machine }) {
  return (
    <>
      {problemsOf(machine).map((p) => (
        <span key={p.check} className="block">
          <strong className="font-semibold">{sentence(p.message)}</strong>{" "}
          {p.fix && <span className="text-ink-2"><WithCode text={sentence(p.fix)} /></span>}
        </span>
      ))}
    </>
  );
}

const OpenStorage = () => (
  <LinkButton href="#/storage"><HardDrive aria-hidden className="size-icon-s" />Open Storage</LinkButton>
);

// The strip's lines: a node that rests or holds something back, then a disk under 10% free.
export function healthCount(machines: Machine[]): number {
  return machines.filter((m) => isSick(m) || lowDisk(m)).length;
}
export const anyResting = (machines: Machine[]) => machines.some(isResting);

export function HealthLines({ machines }: { machines: Machine[] }) {
  return (
    <>
      {machines.filter(isSick).map((m) => {
        const resting = isResting(m), Icon = resting ? OctagonAlert : TriangleAlert;
        return (
          <li key={`health-${m.name}`} className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Icon aria-hidden className={cx("status-icon size-icon flex-none self-start mt-px", resting ? "text-danger" : "text-warning")} />
            <p className="min-w-0 flex-1 basis-col-l">
              <strong className="font-semibold">{headline(m)}.</strong>{" "}
              <Problems machine={m} />
              <span className="text-ink-2"> Since {clockTime(since(m))}.</span>
            </p>
            <CheckNow machine={m}>{hasDisk(m) && <OpenStorage />}</CheckNow>
          </li>
        );
      })}
      {machines.map((m) => ({ m, low: lowDisk(m) })).filter(({ low }) => low).map(({ m, low }) => (
        <li key={`disk-${m.name}`} className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <TriangleAlert aria-hidden className="status-icon size-icon flex-none self-start mt-px text-warning" />
          <p className="min-w-0 flex-1 basis-col-l">
            <strong className="font-semibold">
              {m.name} has {bytes(low!.free)} free{low!.total ? ` of ${bytes(low!.total)}` : ""}, under {low!.total && low!.total * 0.1 > 10e9 ? "10%" : "10 GB"}.
            </strong>{" "}
            <span className="text-ink-2">
              Its cleanup runs first. Under {bytes(healthOf(m)?.min_free ?? 5e9)} it rests and takes no job.
            </span>
          </p>
          <OpenStorage />
        </li>
      ))}
    </>
  );
}

// The Machines page's second row (option A's): always open, the problem, the fix, Check now.
export function HealthUnder({ machine }: { machine: Machine }) {
  const resting = isResting(machine), Icon = resting ? OctagonAlert : TriangleAlert;
  return (
    <div className={cx("flex items-start gap-3 rounded-m border px-3 py-2",
                       resting ? "border-danger bg-failed-soft" : "border-warning bg-warning-soft")}>
      <Icon aria-hidden className={cx("status-icon mt-px size-icon flex-none", resting ? "text-danger" : "text-warning")} />
      <div className="grid min-w-0 gap-2">
        <p><strong className="font-semibold">{headline(machine)}.</strong>{" "}<Problems machine={machine} /></p>
        <CheckNow machine={machine}><span className="num text-sm text-ink-2">since {clockTime(since(machine))}</span></CheckNow>
      </div>
    </div>
  );
}
