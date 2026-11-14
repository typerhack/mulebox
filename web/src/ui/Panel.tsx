// A panel: a hairline box with its title, a note on the right of the title, and a body. A chart's
// caption goes in the title line too, so nothing lies over the chart.

import type { ReactNode } from "react";

import { WithCode } from "./Code";
import { cx } from "./cx";

interface Props {
  title: ReactNode;
  label: string;            // the region's accessible name
  icon?: ReactNode;
  head?: ReactNode;         // beside the title: which machine, a way back
  caption?: ReactNode;      // what the panel's chart shows: its time window and scale
  note?: ReactNode;
  strong?: boolean;         // a page's main panel: its title in the main text colour
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}

export function Panel({ title, label, icon, head, caption, note, strong, className, bodyClassName, children }: Props) {
  const shownNote = note !== undefined && note !== null
    && <span className="num text-sm font-medium text-ink-1">{note}</span>;
  return (
    <section aria-label={label}
      className={cx("flex min-w-0 flex-col rounded-l border border-line bg-surface-1", className)}>
      <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-3 pt-3">
        <span className="inline-flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          <h2 className={cx("flex items-center gap-2 font-semibold",
                            strong ? "text-lg text-ink-1" : "text-sm text-ink-2")}>{icon}{title}</h2>
          {head}
        </span>
        {caption ? (
          // The caption follows the title and the note stays at the end; in a narrow panel the two
          // share the next line.
          <span className="inline-flex min-w-0 flex-auto flex-wrap items-center justify-between gap-x-3 gap-y-1">
            <span className="text-xs whitespace-nowrap text-ink-2">{caption}</span>{shownNote}
          </span>
        ) : shownNote}
      </header>
      <div className={cx("min-w-0 flex-1 p-3", bodyClassName)}>{children}</div>
    </section>
  );
}

// The line a list shows when it has nothing: what is so, and what to do about it.
export function Empty({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="grid gap-1 py-2">
      {icon && <span className="text-ink-2">{icon}</span>}
      <p className="font-semibold">{title}</p>
      {hint && <p className="text-sm text-ink-2"><WithCode text={hint} /></p>}
    </div>
  );
}

export const Fact = ({ name, children }: { name: ReactNode; children: ReactNode }) => (
  <p className="flex justify-between gap-3 text-sm text-ink-2">
    <span>{name}</span><span className="num text-ink-1">{children}</span>
  </p>
);
