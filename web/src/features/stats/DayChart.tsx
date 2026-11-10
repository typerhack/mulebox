// Run time per day: one column per day, mulebox jobs and GitHub runs stacked, on one scale
// with the hours on the left and the day numbers below. Each column says its numbers on hover
// and on focus, and the legend names the two series, so colour never carries them alone.

import type { CSSProperties } from "react";

import { duration } from "../../lib/format";
import { SERIES, dayName, dayScale, hourTick, runsText } from "../../lib/stats";
import type { StatDay } from "../../lib/types";
import { cx } from "../../ui/cx";
import { Tip } from "../../ui/Tip";

export const Legend = ({ shown }: { shown: string[] }) => (
  <p className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-2">
    {SERIES.filter((series) => shown.includes(series.kind)).map((series) => (
      <span key={series.kind} className="inline-flex items-center gap-2">
        <i className={cx("block size-slot rounded-hair", series.tone)} />{series.name}
      </span>
    ))}
  </p>
);

export function DayChart({ days, shown }: { days: StatDay[]; shown: string[] }) {
  const { step, max, value } = dayScale(days, shown);
  const last = days.length - 1;
  return (
    <div role="group" aria-label={`Run time per day, last ${days.length} days`} className="day-chart">
      <div className="num flex flex-col justify-between text-right text-xs leading-none text-ink-3" aria-hidden>
        {[2, 1, 0].map((n) => <span key={n}>{hourTick(step * n)}</span>)}
      </div>
      <div className="day-plot">
        <div className="day-cols">
          {days.map((day, index) => {
            const total = value(day);
            const title = `${dayName(day.from, { weekday: "short", day: "numeric", month: "short" })}${index === last ? ", today" : ""}`;
            const lines = total > 0
              ? [`${duration(total)} in ${runsText(day.runs)}`,
                 ...(shown.length > 1 ? SERIES.map((s) => `${s.name} ${duration(day.kinds?.[s.kind] ?? 0)}`) : [])]
              : ["Nothing ran"];
            return (
              <Tip key={day.from} text={<span className="grid"><b className="font-semibold">{title}</b>{lines.map((line) => <span key={line}>{line}</span>)}</span>}>
                <button type="button" className="day-col"
                  aria-label={`${dayName(day.from, { weekday: "long", day: "numeric", month: "long" })}: ${duration(total)}`}>
                  {total > 0 && (
                    <span className="day-stack" style={{ "--h": `${Math.max(1.5, (100 * total) / max)}%` } as CSSProperties}>
                      {[...SERIES].reverse().filter((s) => shown.includes(s.kind) && (day.kinds?.[s.kind] ?? 0) > 0).map((s) => (
                        <i key={s.kind} className={s.tone} style={{ "--n": day.kinds?.[s.kind] } as CSSProperties} />
                      ))}
                    </span>
                  )}
                </button>
              </Tip>
            );
          })}
        </div>
      </div>
      <span />
      <div className="day-axis num text-xs text-ink-3">
        {days.map((day, index) => (
          <span key={day.from} className={index === last ? "font-semibold text-ink-1" : undefined}>
            {new Date(day.from * 1000).getDate()}
          </span>
        ))}
      </div>
    </div>
  );
}
