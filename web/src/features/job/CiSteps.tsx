// The Steps panel of a GitHub job: every step as it starts, and a step's output once the
// runner writes it, often only when the step ends (lib/cilog.ts). GitHub has it second by
// second, and the result.

import { Clock } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { parseCiLog } from "../../lib/cilog";
import type { JobDetail } from "../../lib/types";
import { LinkButton } from "../../ui/Button";
import { Panel } from "../../ui/Panel";
import { Status } from "../../ui/Status";
import { LOG_BOX, StreamState } from "./LogPanel";
import { useLog } from "./useLog";

const KEEP_CHARS = 1024 * 1024;

interface Props {
  job: JobDetail;
  onState: (state: string) => void;
  onEnd: (job: JobDetail, atEnd: boolean) => void;
}

export function CiSteps({ job, onState, onEnd }: Props) {
  const [text, setText] = useState("");
  const onChunk = useCallback((chunk: string) => setText((had) => (had + chunk).slice(-KEEP_CHARS)), []);
  const { stream, note } = useLog(job.job_id, { onChunk, onState, onEnd: (final) => onEnd(final, true) });
  const { steps, other } = useMemo(() => parseCiLog(text), [text]);
  const running = job.state !== "finished";
  const failedStep = job.ci_result?.step;
  const stateOf = (name: string, index: number) => (name === failedStep ? "failed"
    : running && index === steps.length - 1 ? "running" : "passed");

  return (
    <Panel title="Steps" label="Steps and output" strong
      note={(
        <span className="inline-flex flex-wrap items-center justify-end gap-2 font-normal">
          <StreamState stream={stream} />
          <LinkButton tone="ghost" href={`/api/jobs/${encodeURIComponent(job.job_id)}/log.txt`}>Full log as text</LinkButton>
        </span>
      )}>
      <ol className="divide-y divide-line">
        {steps.map((step, index) => {
          const state = stateOf(step.name, index);
          const head = (
            <>
              <Status state={state} word={state === "passed" ? (running ? "Started" : "Done") : undefined} iconOnly />
              <span className="min-w-0 flex-1 break-words">{step.name}</span>
              <span className="text-sm text-ink-3">{step.output ? "output" : ""}</span>
            </>
          );
          return (
            <li key={`${step.name}-${index}`}>
              {step.output ? (
                <details open={state !== "passed"}>
                  <summary className="flex min-h-tab touch:min-h-ctl-touch cursor-pointer items-center gap-2">{head}</summary>
                  <pre className={`${LOG_BOX} mb-2`}>{step.output}</pre>
                </details>
              ) : <div className="flex min-h-tab touch:min-h-ctl-touch items-center gap-2">{head}</div>}
            </li>
          );
        })}
      </ol>
      {other && <pre tabIndex={0} aria-label="Other output" className={`${LOG_BOX} mt-2`}>{other}</pre>}
      <p role="status" className="mt-2 flex items-start gap-2 text-sm text-ink-2">
        <Clock aria-hidden className="mt-px size-icon-s" />
        <span>{note || "The runner hands over a step's output in blocks, or when the step ends. GitHub has every line."}</span>
      </p>
    </Panel>
  );
}
