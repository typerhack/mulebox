// The Tests panel of a finished job's page, under its stages (design-system/tests/, option B):
// every runner whose summary its log had, with what ran, what was skipped, and how that
// differs from the pass it was compared with, which is a link. A drop the agent allowed shows
// its reason in its own words. A job with no summary (a lint) has no panel.

import { ListChecks, MessageSquareQuote } from "lucide-react";

import { dayTime, jobHref, shortId } from "../../lib/format";
import { testsView, type TestsView } from "../../lib/tests";
import type { JobDetail } from "../../lib/types";
import { cx } from "../../ui/cx";
import { Panel } from "../../ui/Panel";
import { MARK_ICON, TESTS_TONE } from "../jobs/TestsBits";

function Compared({ view, now }: { view: TestsView; now: number }) {
  const last = view.compared;
  if (!last?.job_id) {
    return <>{view.passed ? "No earlier pass of this job to compare with." : "Not compared: only a pass is held to the last pass."}</>;
  }
  return (
    <>
      Compared with <a href={jobHref({ job_id: last.job_id })} title={`Job id ${last.job_id}`}><code>{shortId({ job_id: last.job_id })}</code></a>,
      the last pass{last.branch ? ` on ${last.branch}` : ""}{last.finished_at ? `, ${dayTime(last.finished_at, now)}` : ""}.
    </>
  );
}

export function TestsPanel({ job, now }: { job: JobDetail; now: number }) {
  const view = testsView(job);
  if (!view) return null;
  return (
    <Panel title="Tests" label="Tests" icon={<ListChecks aria-hidden className="size-icon-s" />}
      note={view.counted ? `${view.ran} ran, ${view.skipped} skipped` : null}>
      {view.counted ? (
        <dl className="grid min-w-0">
          {view.rows.map((row) => {
            const Icon = row.mark && MARK_ICON[row.mark];
            return (
              <div key={row.name} className="flex flex-wrap items-baseline justify-between gap-x-3 border-t border-line py-2 first:border-t-0 first:pt-0">
                <dt className="font-mono font-medium">{row.name}</dt>
                <dd className="min-w-0"><b className="num font-semibold">{row.ran}</b> ran <span className="num text-ink-2">{row.skipped} skipped</span></dd>
                {row.text && (
                  <dd className="flex basis-full items-start gap-2 text-sm text-ink-2">
                    {Icon && <Icon aria-hidden className={cx("status-icon mt-hair size-icon-s flex-none", TESTS_TONE[row.tone])} />}
                    <span className="min-w-0">{row.text}</span>
                  </dd>
                )}
              </div>
            );
          })}
        </dl>
      ) : <p>No test runner's summary in its log.</p>}
      {view.reason && (
        <div className="mt-2 flex items-start gap-2 rounded-m border border-line bg-surface-2 px-3 py-2">
          <MessageSquareQuote aria-hidden className="mt-hair size-icon-s flex-none text-ink-2" />
          <p className="min-w-0 wrap-anywhere">
            <b className="block text-sm font-semibold text-ink-2">The agent's reason for fewer tests</b>{`“${view.reason}”`}
          </p>
        </div>
      )}
      <p className="mt-2 border-t border-line pt-2 text-sm text-ink-2"><Compared view={view} now={now} /></p>
    </Panel>
  );
}
