// A state as an icon with its own shape, and its word (design-system.md, Color and Icons).
// The status colour sits on the icon only; the word stays in the text colour. On cards the
// icon stands alone and the word is its tooltip.

import { Ban, Circle, CircleCheck, CircleHelp, CircleMinus, CirclePause, CircleX, Clock, FlaskConical, Hourglass,
         LoaderCircle, PowerOff, TriangleAlert, type LucideIcon } from "lucide-react";

import { stateText } from "../lib/format";
import { cx } from "./cx";
import { Tip } from "./Tip";

interface Look { Icon: LucideIcon; tone: string; spins?: boolean }
const RUN: Look = { Icon: LoaderCircle, tone: "text-running", spins: true };
const WAIT: Look = { Icon: Clock, tone: "text-queued" };
const WARN: Look = { Icon: TriangleAlert, tone: "text-warning" };
const LOOKS: Record<string, Look> = {
  running: RUN, starting: RUN, cleaning: RUN, busy: RUN,
  queued: WAIT, uploading: WAIT,
  passed: { Icon: CircleCheck, tone: "text-passed" },
  failed: { Icon: CircleX, tone: "text-failed" },
  cancelled: { Icon: Ban, tone: "text-cancelled" },
  timed_out: WARN, interrupted: WARN, "stopped: stuck": WARN,
  released: { Icon: CircleMinus, tone: "text-cancelled" },
  skipped: { Icon: CircleMinus, tone: "text-cancelled" },
  available: { Icon: Circle, tone: "text-queued" },
  idle: { Icon: Circle, tone: "text-queued" },
  offline: { Icon: PowerOff, tone: "text-cancelled" },
  draining: { Icon: Hourglass, tone: "text-queued" },
  dev: { Icon: FlaskConical, tone: "text-queued" },
  paused: { Icon: CirclePause, tone: "text-queued" },
  stuck: { Icon: CircleHelp, tone: "text-queued" },
};
const UNKNOWN: Look = { Icon: Circle, tone: "text-queued" };
const SIZES = { s: "size-icon-s", m: "size-icon", l: "size-icon-m", xl: "size-icon-l" };

interface Props {
  state: string | null | undefined;
  word?: string;          // what to call it; the state's own words by default
  tip?: string;           // a longer explanation for the tooltip
  iconOnly?: boolean;
  still?: boolean;        // a running job that is frozen does not turn
  size?: keyof typeof SIZES;
  className?: string;
}

export function Status({ state, word, tip, iconOnly, still, size = "m", className }: Props) {
  const look = LOOKS[String(state)] ?? UNKNOWN;
  const text = word ?? stateText(state);
  const icon = <look.Icon aria-hidden className={cx("status-icon", SIZES[size], look.tone,
                                                    look.spins && !still && "animate-spin")} />;
  if (iconOnly) {
    return (
      <Tip text={tip ?? text}>
        <span role="img" aria-label={text} className={cx("inline-grid place-items-center", className)}>{icon}</span>
      </Tip>
    );
  }
  const body = (
    <span className={cx("inline-flex items-center gap-2 font-medium whitespace-nowrap text-ink-1", className)}>
      {icon}<span>{text}</span>
    </span>
  );
  return tip ? <Tip text={tip}>{body}</Tip> : body;
}
