// "Where the time went": one table, by project, type, source, machine or job name, for today
// or all time; the top 8 with a way to show all.

import { CircleHelp, Clock } from "lucide-react";
import type { CSSProperties } from "react";

import { duration } from "../../lib/format";
import { LIMIT, average, int, label, runsText, share, toneOf, type Dim } from "../../lib/stats";
import type { Stats } from "../../lib/types";
import { cx } from "../../ui/cx";
import { Tip } from "../../ui/Tip";

interface Props { found: Stats; by: Dim; title: string; open: boolean; onToggle: () => void }

export function Breakdown({ found, by, title, open, onToggle }: Props) {
  const rows = found.by[by] ?? [];
  if (!rows.length) return <p className="py-2 text-sm text-ink-2">Nothing ran in this period.</p>;
  const max = Math.max(...rows.map((row) => row.seconds), 1), sum = found.total.seconds;
  const shown = open ? rows : rows.slice(0, LIMIT);
  return (
    <>
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">{title}</th><th scope="col" className="max-md:hidden"><span className="sr-only">Share</span></th>
            <th scope="col" className="end">Run time</th><th scope="col" className="end">Runs</th>
            <th scope="col" className="end max-md:hidden">Average</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((row) => (
            <tr key={row.key}>
              <td>
                <span className="inline-flex items-center gap-x-2 whitespace-nowrap">
                  <span className="max-w-col-m truncate max-md:max-w-col-s" title={label(by, row.key)}>{label(by, row.key)}</span>
                  {row.unknown > 0 && (
                    <Tip text={`${runsText(row.unknown)} with no recorded length`}>
                      <span tabIndex={0} className="num inline-flex items-center gap-1 text-xs text-ink-2">
                        <CircleHelp aria-hidden className="size-icon-s" />{row.unknown}
                      </span>
                    </Tip>
                  )}
                  {row.running > 0 && (
                    <Tip text={`${row.running} still running, ${duration(row.running_seconds)} so far`}>
                      <span tabIndex={0} className="num inline-flex items-center gap-1 text-xs text-ink-2">
                        <Clock aria-hidden className="size-icon-s" />{row.running}
                      </span>
                    </Tip>
                  )}
                </span>
              </td>
              <td className="w-full max-md:hidden">
                <Tip text={`${label(by, row.key)}: ${duration(row.seconds)}, ${share(row.seconds, sum)} of the time`}>
                  <div tabIndex={0} className="share-bar min-w-col-s">
                    <i className={cx(toneOf(by, row.key))} style={{ "--v": `${(100 * row.seconds) / max}%` } as CSSProperties} />
                  </div>
                </Tip>
              </td>
              <td className="num end">{duration(row.seconds)}</td>
              <td className="num end text-ink-2">{int(row.runs)}</td>
              <td className="num end text-ink-2 max-md:hidden">{average(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > LIMIT && (
        <p className="pt-2">
          <button type="button" onClick={onToggle} className="text-sm font-medium text-accent underline hover:text-accent-hover">
            {open ? `Show the top ${LIMIT}` : `Show all ${rows.length}`}
          </button>
        </p>
      )}
    </>
  );
}
