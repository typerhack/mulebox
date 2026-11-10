// The strip above the panels: what is out of step between the build machine, its workers and
// the laptops that send jobs (dashboard/notices.py), each with the command that fixes it.
// Two levels: `danger` (a worker, jobs can fail) in red, `warning` (a laptop, its jobs still
// run) in amber; the strip takes its worst line's colour. A mark in the header, with the
// count, stays in sight when the page scrolls and brings the strip back into view. Both are
// absent while everything is in step, the usual case.

import { OctagonAlert, TriangleAlert } from "lucide-react";

import type { Notice } from "../../lib/types";
import { useMachines } from "../../state/live";
import { WithCode } from "../../ui/Code";
import { cx } from "../../ui/cx";
import { Tip } from "../../ui/Tip";

const STRIP_ID = "out-of-step";
const worst = (items: Notice[]) => (items.some((item) => item.level === "danger") ? "danger" : "warning");
const iconOf = (level: string) => (level === "danger" ? OctagonAlert : TriangleAlert);
const toneOf = (level: string) => (level === "danger" ? "text-danger" : "text-warning");

export function OutOfStepMark() {
  const items = useMachines()?.notices ?? [];
  if (!items.length) return null;
  const level = worst(items), Icon = iconOf(level);
  const word = `${items.length} out of step`;
  const show = () => {
    const strip = document.getElementById(STRIP_ID);
    strip?.scrollIntoView({ block: "start" });
    strip?.focus({ preventScroll: true });
  };
  return (
    <Tip text={word}>
      <button type="button" aria-label={`${word}: show`} onClick={show}
        className="inline-flex h-ctl-icon touch:h-ctl-touch items-center gap-1 rounded-m border border-line-strong bg-surface-1 px-2 text-sm font-semibold hover:border-ink-1 hover:bg-surface-3">
        <Icon aria-hidden className={cx("status-icon size-icon", toneOf(level))} />
        <span className="num">{items.length}</span>
      </button>
    </Tip>
  );
}

export function OutOfStepStrip() {
  const items = useMachines()?.notices ?? [];
  if (!items.length) return null;
  const level = worst(items);
  return (
    <section id={STRIP_ID} role="status" aria-label="Out of step" tabIndex={-1}
      className={cx("scroll-mt-8 rounded-m border px-3 py-2",
                    level === "danger" ? "border-danger bg-failed-soft" : "border-warning bg-warning-soft")}>
      <ul className="grid gap-1">
        {items.map((item, index) => {
          const Icon = iconOf(item.level);
          return (
            <li key={index} className="flex items-start gap-3">
              <Icon aria-hidden className={cx("status-icon mt-px size-icon", toneOf(item.level))} />
              <p className="min-w-0">
                <strong className="font-semibold"><WithCode text={item.text} /></strong>{" "}
                <span className="text-ink-2"><WithCode text={item.fix} /></span>
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
