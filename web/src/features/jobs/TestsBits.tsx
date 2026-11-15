// The tests a finished job ran, on its row (design-system/tests/, option B, the user's pick):
// the count as a quiet number before the node and the run time, "+12" when the suite grew,
// and, only when the count failed the job or a drop was let through, a line in words under
// the job's name. The colour sits on the line's icon alone: failed for fewer and none,
// warning for a drop the agent allowed, with its reason in its own words.

import { ListChecks, ListMinus, ListPlus, ListX, type LucideIcon } from "lucide-react";

import { plural } from "../../lib/format";
import type { RunnerMark, TestsKind, TestsTone, TestsView } from "../../lib/tests";
import { cx } from "../../ui/cx";

export const TESTS_ICON: Record<TestsKind, LucideIcon> = {
  ok: ListChecks, more: ListPlus, fewer: ListMinus, zero: ListX, allowed: ListMinus, missing: ListX,
};
export const MARK_ICON: Record<Exclude<RunnerMark, null>, LucideIcon> = { zero: ListX, fewer: ListMinus, more: ListPlus };
export const TESTS_TONE: Record<TestsTone, string> = { failed: "text-failed", warn: "text-warning", plain: "text-ink-2" };

export function TestCount({ view }: { view: TestsView | null }) {
  if (!view?.counted) return null;
  const said = `${plural(view.ran, "test")} ran, ${view.skipped} skipped`;
  return (
    <span title={said} className="inline-flex items-center gap-1 font-medium whitespace-nowrap text-ink-1">
      <ListChecks aria-hidden className="status-icon size-icon-s text-ink-2" />
      <span className="num">{view.ran}</span>
      <span className="font-normal text-ink-2">{view.ran === 1 ? "test" : "tests"}</span>
      {view.delta && <span className="num font-normal text-ink-2" title="More than the last pass">{view.delta}</span>}
    </span>
  );
}

export function TestsWhy({ view }: { view: TestsView | null }) {
  if (!view?.line) return null;
  const Icon = TESTS_ICON[view.kind];
  return (
    <span className="flex min-w-0 basis-full items-start gap-2 text-sm wrap-anywhere text-ink-2">
      <Icon aria-hidden className={cx("status-icon mt-hair size-icon-s flex-none", TESTS_TONE[view.tone])} />
      <span className="min-w-0"><b className="font-semibold text-ink-1">{view.line.bold}</b>{view.line.rest}</span>
    </span>
  );
}
