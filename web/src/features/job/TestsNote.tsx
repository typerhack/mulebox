// What a finished job's test count did to it, on its page (design-system/tests/, option B): a
// strip under the header, where a running job's verdict stands. Danger when the count turned
// the pass into a failure (fewer tests, none, or no summary where one is required), with the
// command that lets a drop through and two ways on; warning for a drop the agent allowed,
// with its reason. A normal pass and an ordinary failure have no strip.

import { ScrollText } from "lucide-react";

import { jobHref } from "../../lib/format";
import { FEWER_COMMAND, testsView } from "../../lib/tests";
import type { JobDetail } from "../../lib/types";
import { Button, LinkButton } from "../../ui/Button";
import { WithCode } from "../../ui/Code";
import { CopyButton } from "../../ui/Copy";
import { cx } from "../../ui/cx";
import { TESTS_ICON, TESTS_TONE } from "../jobs/TestsBits";
import { LOG_ID } from "./LogPanel";
import { toSummary } from "./logMarks";

export function TestsNote({ job }: { job: JobDetail }) {
  const view = testsView(job);
  if (!view?.strip) return null;
  const Icon = TESTS_ICON[view.kind], bad = view.tone === "failed";
  const last = view.compared?.job_id;
  return (
    <div role="status" className={cx("flex min-w-0 items-start gap-3 rounded-m border px-3 py-2",
                                     bad ? "border-danger bg-failed-soft" : "border-warning bg-warning-soft")}>
      <Icon aria-hidden className={cx("status-icon mt-hair size-icon flex-none", bad ? "text-danger" : TESTS_TONE[view.tone])} />
      <div className="flex min-w-0 flex-auto flex-wrap items-center gap-x-3 gap-y-2">
        <p className="min-w-0 flex-auto basis-col-l wrap-anywhere">
          <b className="font-semibold">{view.strip.title}</b> <WithCode text={view.strip.text} codeClassName="font-semibold" />
          {view.kind === "fewer" && (
            <> Removed on purpose? The agent runs it again with the reason:{" "}
              <span className="inline-flex flex-wrap items-center gap-1 align-middle">
                <code className="font-semibold wrap-anywhere">{FEWER_COMMAND}</code>
                <CopyButton text={FEWER_COMMAND} label="Copy the command" />
              </span>
            </>
          )}
        </p>
        {bad && (view.counted || last) && (
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            {view.counted && (
              <Button onClick={() => toSummary(document.getElementById(LOG_ID), view.summaries, true)}>
                <ScrollText aria-hidden className="size-icon-s" />Go to the runner's summary
              </Button>
            )}
            {last && <LinkButton href={jobHref({ job_id: last })}>Open the last pass</LinkButton>}
          </div>
        )}
      </div>
    </div>
  );
}
