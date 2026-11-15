// A running job's verdict on its card (design-system/stuck/, option B, the user's pick): one
// line across the card's foot with the verdict's icon in its level's colour, its name and
// the one figure that matters. It is a button: pressed, it opens in place to the server's
// sentence and the two ways on, the job's log and Cancel (only where this page has controls).
// The state icon above keeps turning, since the job is still running.

import { ChevronDown, Hourglass, OctagonAlert, ScrollText, Snail, TextCursorInput, type LucideIcon } from "lucide-react";
import { useId, useState } from "react";

import { tokenStore } from "../../lib/api";
import { jobHref } from "../../lib/format";
import { looksView, type LooksLevel, type LooksView } from "../../lib/looks";
import { useStore } from "../../lib/store";
import type { Job } from "../../lib/types";
import { tickStore } from "../../state/live";
import { LinkButton } from "../../ui/Button";
import { cx } from "../../ui/cx";
import { CancelControl, cancellable } from "../job/JobControls";

export const LOOKS_ICON: Record<LooksView["verdict"], LucideIcon> = {
  slow: Snail, waiting: Hourglass, asking: TextCursorInput, stuck: OctagonAlert,
};
export const LOOKS_TONE: Record<LooksLevel, string> = { warning: "text-warning", info: "text-queued", danger: "text-danger" };

// The verdict now, with its quiet time counting on once a second.
export function useLooks(job: Job): LooksView | null {
  useStore(tickStore);
  return looksView(job, Date.now() / 1000);
}

export function LooksLine({ job }: { job: Job }) {
  const view = useLooks(job);
  const token = useStore(tokenStore);
  const [open, setOpen] = useState(false);
  const id = useId();
  if (!view) return null;
  const Icon = LOOKS_ICON[view.verdict];
  return (
    <div className="grid min-w-0 basis-full gap-2 border-t border-line pt-2">
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}
        className="flex min-h-ctl-s touch:min-h-ctl-touch w-full flex-wrap items-center gap-x-2 rounded-s text-left hover:bg-surface-3">
        <Icon aria-hidden className={cx("status-icon size-icon-s flex-none", LOOKS_TONE[view.level])} />
        <b className="font-semibold">{view.label}</b>
        {view.figure && <span className="num text-sm text-ink-2">{view.figure}</span>}
        <ChevronDown aria-hidden className={cx("ml-auto size-icon-s flex-none text-ink-2", open && "rotate-180")} />
      </button>
      <div id={id} hidden={!open} className="grid min-w-0 gap-2">
        {view.text && <p className="wrap-anywhere">{view.text}</p>}
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <LinkButton href={jobHref(job)}><ScrollText aria-hidden className="size-icon-s" />Open its log</LinkButton>
          {token && cancellable(job) && <CancelControl job={job} />}
        </div>
      </div>
    </div>
  );
}
