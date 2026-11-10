// A line of waiting jobs. A long one shows its first few rows and a control that opens the
// rest in place; the rows keep their real positions either way. The list is a container, so
// a row folds by the width it really has (styles/components.css, `.wait-row`).

import { ChevronDown, ChevronUp } from "lucide-react";
import { useId, useState } from "react";

import { WAIT_SHOWN, shownWaiting } from "../../lib/lanes";
import type { Job } from "../../lib/types";
import { Button } from "../../ui/Button";
import { WaitRow } from "./JobCard";

interface Props { jobs: Job[]; total: number; machineCount: number | null; label: string }

export function WaitList({ jobs, total, machineCount, label }: Props) {
  const [all, setAll] = useState(false);
  const id = useId();
  if (!jobs.length) return null;
  const { rows, long } = shownWaiting(jobs, all);
  const Icon = all ? ChevronUp : ChevronDown;
  return (
    <div className="@container grid min-w-0 justify-items-start gap-2">
      <ol id={id} aria-label={label} className="w-full border-t border-line">
        {rows.map((job) => <WaitRow key={job.job_id} job={job} total={total} machineCount={machineCount} />)}
      </ol>
      {long && (
        <Button aria-expanded={all} aria-controls={id} onClick={() => setAll(!all)}>
          <Icon aria-hidden className="size-icon" />
          {all ? `Show the first ${WAIT_SHOWN}` : `Show all waiting (${jobs.length})`}
        </Button>
      )}
    </div>
  );
}
