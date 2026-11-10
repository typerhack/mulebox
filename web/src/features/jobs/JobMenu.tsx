// The three dots on a job card or waiting row, and the four move arrows of a waiting row.
// Both are absent where this page has no controls or the job has nothing to steer.

import { ChevronDown, ChevronUp, ChevronsDown, ChevronsUp, Ellipsis, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { controlJob, problemText, tokenStore, type JobAction } from "../../lib/api";
import { jobName } from "../../lib/format";
import { jobGroups, steerable } from "../../lib/menu";
import { useStore } from "../../lib/store";
import type { Job } from "../../lib/types";
import { IconButton } from "../../ui/Button";
import { cx } from "../../ui/cx";
import { ActionMenu } from "../../ui/Menu";
import { Tip } from "../../ui/Tip";

export function JobMenu({ job, total }: { job: Job; total: number }) {
  const token = useStore(tokenStore);
  if (!token || !steerable(job)) return null;
  const label = `Actions for ${jobName(job)}`;
  return (
    <ActionMenu groups={jobGroups(job, total)} label={label}>
      <IconButton small label={label} tip="Actions" aria-haspopup="menu"><Ellipsis aria-hidden className="size-icon" /></IconButton>
    </ActionMenu>
  );
}

const MOVES: [JobAction, string, LucideIcon][] = [
  ["first", "Move to the front of the line", ChevronsUp], ["up", "Move one place up", ChevronUp],
  ["down", "Move one place down", ChevronDown], ["last", "Move to the end of the line", ChevronsDown],
];

// Positions are the real line's, across every lane, so "up" passes the job just ahead of it in
// the whole queue. The queue event that follows redraws the list; until then the row waits.
export function MoveButtons({ job, total }: { job: Job; total: number }) {
  const token = useStore(tokenStore);
  const [moving, setMoving] = useState<number | null>(null);  // the position it was sent from
  const [problem, setProblem] = useState<string | null>(null);
  const at = job.position;
  if (!token || !at || job.cancel_requested) return null;
  const busy = moving === at;
  const blocked: Record<string, boolean> = { first: at === 1, up: at === 1, down: at >= total, last: at >= total };
  const move = async (action: JobAction) => {
    setProblem(null);
    setMoving(at);
    try {
      await controlJob(job.job_id, action);
    } catch (failure) {
      setMoving(null);
      setProblem(`Not moved. ${problemText(failure)}`);
    }
  };
  return (
    <span className="inline-flex flex-wrap items-center justify-end gap-2">
      {problem && <span role="alert" className="text-sm font-medium">{problem}</span>}
      {busy && <span role="status" className="text-sm text-ink-2">Moving</span>}
      <span role="group" aria-label={`Move ${jobName(job)} in line`} className="inline-flex">
        {MOVES.map(([action, label, Icon], index) => (
          <Tip key={action} text={label}>
            <button type="button" aria-label={label} disabled={blocked[action] || busy} onClick={() => void move(action)}
              className={cx("inline-grid size-ctl-s touch:size-ctl-touch place-items-center border border-line-strong bg-surface-1 text-ink-1 transition-colors",
                            "hover:relative hover:border-ink-1 hover:bg-surface-3 off:border-line off:bg-surface-2 off:text-ink-3",
                            index > 0 && "-ml-px", index === 0 && "rounded-l-m", index === MOVES.length - 1 && "rounded-r-m")}>
              <Icon aria-hidden className="size-icon" />
            </button>
          </Tip>
        ))}
      </span>
    </span>
  );
}
