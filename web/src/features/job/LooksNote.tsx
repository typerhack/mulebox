// A running job's verdict on its page (design-system/stuck/, option B): a strip under the
// header, where "Needs an answer" stands, with the verdict's icon, its name, the server's
// sentence and the two ways on. The strip takes its level's colours: danger for stuck and
// asking, warning for slow, plain for a job that waits on purpose.

import { ChevronsDown } from "lucide-react";

import { tokenStore } from "../../lib/api";
import { afterLabel, type LooksLevel } from "../../lib/looks";
import { useStore } from "../../lib/store";
import type { JobDetail } from "../../lib/types";
import { Button } from "../../ui/Button";
import { cx } from "../../ui/cx";
import { LOOKS_ICON, LOOKS_TONE, useLooks } from "../jobs/LooksLine";
import { CancelControl, cancellable } from "./JobControls";
import { LOG_ID } from "./LogPanel";

const STRIP: Record<LooksLevel, string> = {
  danger: "border-danger bg-failed-soft", warning: "border-warning bg-warning-soft", info: "border-line-strong bg-surface-2",
};

function toLastLine() {
  const log = document.getElementById(LOG_ID);
  if (!log) return;
  log.scrollTop = log.scrollHeight;
  log.scrollIntoView({ block: "nearest" });
  log.focus();
}

export function LooksNote({ job }: { job: JobDetail }) {
  const view = useLooks(job);
  const token = useStore(tokenStore);
  if (!view || job.state === "finished") return null;
  const Icon = LOOKS_ICON[view.verdict];
  return (
    <div role="status" className={cx("flex min-w-0 items-start gap-3 rounded-m border px-3 py-2", STRIP[view.level])}>
      <Icon aria-hidden className={cx("status-icon mt-hair size-icon flex-none", LOOKS_TONE[view.level])} />
      <div className="flex min-w-0 flex-auto flex-wrap items-center gap-x-3 gap-y-2">
        <p className="min-w-0 flex-auto basis-col-l wrap-anywhere">
          <b className="font-semibold">{view.label}.</b> {afterLabel(view)}
        </p>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {job.kind === "job" && <Button onClick={toLastLine}><ChevronsDown aria-hidden className="size-icon-s" />Go to its last line</Button>}
          {token && cancellable(job) && <CancelControl job={job} />}
        </div>
      </div>
    </div>
  );
}
