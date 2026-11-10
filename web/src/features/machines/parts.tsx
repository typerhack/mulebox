// The pieces every view of a machine shares: its state, the host mark, the out-of-step mark,
// its slots as boxes, its network, what it offers and its Pause button.

import { ArrowDown, ArrowUp, House, OctagonAlert, Pause, Play } from "lucide-react";
import { useState } from "react";

import { controlMachine, problemText, tokenStore } from "../../lib/api";
import { rate } from "../../lib/format";
import { useStore } from "../../lib/store";
import type { Machine, Notice } from "../../lib/types";
import { IconButton } from "../../ui/Button";
import { cx } from "../../ui/cx";
import { Status } from "../../ui/Status";
import { Tip } from "../../ui/Tip";

export const isLive = (m: Machine) => m.state !== "offline";
export const isHeld = (m: Machine) => m.state === "draining";

// The server says `draining` for a paused machine; with nothing running it is simply paused.
export function shownState(m: Machine): { state: string; word: string; tip?: string } {
  if (m.state === "offline") return { state: "offline", word: "Offline" };
  if (m.state === "draining") {
    return m.jobs.length ? { state: "draining", word: "Draining", tip: "Draining: takes no new jobs; what runs finishes" }
                         : { state: "paused", word: "Paused", tip: "Paused: takes no new jobs" };
  }
  if (m.state === "busy") return { state: "busy", word: "Busy", tip: "Busy: every slot is in use" };
  return { state: "idle", word: m.jobs.length ? "Working" : "Idle", tip: "Takes jobs" };
}

export function MachineState({ machine, iconOnly }: { machine: Machine; iconOnly?: boolean }) {
  const { state, word, tip } = shownState(machine);
  return <Status state={state} word={word} tip={tip} iconOnly={iconOnly} still={state !== "busy"} />;
}

export const HostMark = ({ machine }: { machine: Machine | null }) => (machine?.host ? (
  <Tip text="Dashboard host">
    <span role="img" aria-label="Dashboard host" className="inline-grid place-items-center text-ink-2">
      <House aria-hidden className="size-icon-s" />
    </span>
  </Tip>
) : null);

// A worker on another mulebox than the coordinator, as the notices say (dashboard/notices.py).
export function StepMark({ machine, notices }: { machine: Machine; notices: Notice[] | undefined }) {
  const notice = notices?.find((n) => n.kind === "worker" && n.name === machine.name);
  if (!notice) return null;
  const text = `Out of step: ${notice.text} ${notice.fix}`.replaceAll("`", "");
  return (
    <Tip text={text}>
      <span role="img" aria-label="Out of step" className="inline-grid place-items-center">
        <OctagonAlert aria-hidden className="status-icon size-icon-s text-danger" />
      </span>
    </Tip>
  );
}

export function usedSlots(m: Machine): number {
  if (!isLive(m)) return 0;
  return isHeld(m) ? m.jobs.length : Math.max(0, m.slots - m.free_slots);
}

export function slotsText(m: Machine): string {
  if (!isLive(m)) return `${m.slots} ${m.slots === 1 ? "slot" : "slots"}`;
  if (isHeld(m)) return `takes no new jobs, ${m.jobs.length} running`;
  return `${m.free_slots} of ${m.slots} ${m.slots === 1 ? "slot" : "slots"} free`;
}

export function Slots({ machine, words = true }: { machine: Machine; words?: boolean }) {
  const used = usedSlots(machine), text = slotsText(machine);
  return (
    <span className="inline-flex items-center gap-2" title={words ? undefined : text}>
      <span role="img" aria-label={text} className="inline-flex gap-1">
        {Array.from({ length: machine.slots }, (_, index) => (
          <i key={index} className={cx("block size-slot rounded-hair border",
                                       index < used ? "border-ink-1 bg-ink-1" : "border-ink-2")} />
        ))}
      </span>
      {words && <span className="num">{text}</span>}
    </span>
  );
}

// Text only: a rate has no fixed top, so a bar would mean nothing. Counts the machine's
// physical interfaces, so a VPN tunnel's traffic is not added to Wi-Fi's.
export function Net({ machine }: { machine: Machine }) {
  const { net_in_kib_s: inbound, net_out_kib_s: outbound } = machine;
  if (typeof inbound !== "number" || typeof outbound !== "number") return null;
  return (
    <span aria-label="Network" className="num inline-flex flex-wrap items-center gap-x-2 gap-y-1">
      <span title="Coming in" className="inline-flex items-center gap-1"><ArrowDown aria-hidden className="size-icon-s" />{rate(inbound)}</span>
      <span title="Going out" className="inline-flex items-center gap-1"><ArrowUp aria-hidden className="size-icon-s" />{rate(outbound)}</span>
    </span>
  );
}

export const Offers = ({ machine, word }: { machine: Machine; word?: boolean }) => (machine.capabilities.length ? (
  <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm text-ink-2">
    {word && "Offers"}
    {machine.capabilities.map((name) => (
      <code key={name} className="rounded-s border border-line bg-surface-2 px-1 text-xs whitespace-nowrap">{name}</code>
    ))}
  </p>
) : null);

// Pause: no new jobs there, what runs finishes (`mulebox machine pause|resume`). Until the
// machines event shows the change the button waits; a refusal is said beside it.
export function MachinePause({ machine }: { machine: Machine }) {
  const token = useStore(tokenStore);
  const [asked, setAsked] = useState<{ held: boolean } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  if (!token || !isLive(machine)) return null;
  const held = isHeld(machine);
  const waiting = asked !== null && asked.held === held;  // not shown by the server yet
  const act = async () => {
    setProblem(null);
    setAsked({ held });
    try {
      await controlMachine(machine.name, held ? "resume" : "pause");
    } catch (failure) {
      setAsked(null);
      setProblem(`Not changed. ${problemText(failure)}`);
    }
  };
  return (
    <span className="inline-flex items-center gap-2">
      {problem && <span role="alert" className="text-sm font-medium whitespace-normal">{problem}</span>}
      <IconButton small disabled={waiting} onClick={() => void act()}
        label={`${held ? "Resume" : "Pause"} ${machine.name}`}
        tip={waiting ? (held ? "Resuming" : "Pausing")
          : held ? "Let this machine take jobs again" : "Take no new jobs here; what runs finishes"}>
        {held ? <Play aria-hidden className="size-icon-s" /> : <Pause aria-hidden className="size-icon-s" />}
      </IconButton>
    </span>
  );
}
