// The Statistics page (`#/stats`): how long jobs ran, today and since the first job, with
// filters, the last 14 days and one breakdown table. Asked again each minute while open.

import { CircleHelp, Clock, Info } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";

import { duration } from "../../lib/format";
import { DAYS, DIMS, FILTERS, SERIES, askStats, dayName, int, label, runsText, share, type Dim } from "../../lib/stats";
import type { Stats } from "../../lib/types";
import { cx } from "../../ui/cx";
import { FilterSelect } from "../../ui/FilterSelect";
import { Panel } from "../../ui/Panel";
import { Segmented } from "../../ui/Segmented";
import { Tabs } from "../../ui/Tabs";
import { Tip } from "../../ui/Tip";
import { Breakdown } from "./Breakdown";
import { DayChart, Legend } from "./DayChart";

const REFRESH_MS = 60_000;
type Range = "today" | "all";
// Kept between visits to the page, not between reloads.
const kept = { filters: {} as Partial<Record<Dim, string>>, by: "project" as Dim, range: "all" as Range };

function Apart({ total }: { total: Stats["total"] }) {
  return (
    <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-2">
      <Tip text="Runs still going count up to now, and grow until they end.">
        <span tabIndex={0} className="inline-flex items-center gap-1">
          <Clock aria-hidden className="size-icon-s" />
          {total.running ? `${int(total.running)} still running, ${duration(total.running_seconds)} so far` : "None running now"}
        </span>
      </Tip>
      <Tip text="Most often a run cut off by a restart. Counted apart, never as zero.">
        <span tabIndex={0} className="inline-flex items-center gap-1">
          <CircleHelp aria-hidden className="size-icon-s" />
          {total.unknown ? `${runsText(total.unknown)} with no recorded length` : "Every length recorded"}
        </span>
      </Tip>
    </p>
  );
}

function Head({ range, found }: { range: Range; found: Stats }) {
  const total = found.total;
  const rows = SERIES.map((series) => ({ series, row: found.by.kind?.find((r) => r.key === series.kind) }))
    .filter((pair) => pair.row);
  return (
    <div className="grid content-start gap-2 rounded-m border border-line bg-surface-2 p-3">
      <p className="text-sm text-ink-2">
        <b className="font-semibold text-ink-1">{range === "today" ? "Today" : "All time"}</b>
        {range === "today" ? `, ${dayName(found.from ?? 0, { weekday: "long", day: "numeric", month: "short" })}`
          : found.first_started_at ? `, since the first job on ${dayName(found.first_started_at, { day: "numeric", month: "short", year: "numeric" })}` : ""}
      </p>
      <p className="num text-xl leading-tight font-semibold">{duration(total.seconds)}</p>
      <p className="num text-sm text-ink-2">{int(total.seconds / 60)} minutes in {runsText(total.runs)}</p>
      {rows.length > 0 && total.seconds > 0 && (
        <>
          <div role="img" className="split-bar"
            aria-label={rows.map(({ series, row }) => `${series.name} ${share(row?.seconds ?? 0, total.seconds)}`).join(", ")}>
            {rows.filter(({ row }) => (row?.seconds ?? 0) > 0).map(({ series, row }) => (
              <i key={series.kind} className={series.tone} style={{ "--n": row?.seconds } as CSSProperties} />
            ))}
          </div>
          <ul className="grid gap-1 text-sm">
            {rows.map(({ series, row }) => (
              <li key={series.kind} className="flex items-center gap-2">
                <i className={cx("block size-slot rounded-hair", series.tone)} />
                <span className="flex-1">{series.name}</span>
                <span className="num font-medium">{duration(row?.seconds ?? 0)}</span>
                <span className="num min-w-7 text-right text-ink-2">{share(row?.seconds ?? 0, total.seconds)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <Apart total={total} />
    </div>
  );
}

export function StatsPage() {
  const [data, setData] = useState<{ today: Stats; all: Stats } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState(kept.filters);
  const [by, setBy] = useState<Dim>(kept.by);
  const [range, setRange] = useState<Range>(kept.range);
  const [open, setOpen] = useState(false);
  const choosing = useRef(false);

  const load = useCallback(async (chosen: Partial<Record<Dim, string>>) => {
    try {
      setData(await askStats(chosen));
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "no answer");
    }
  }, []);
  useEffect(() => {
    void load(filters);
    const timer = setInterval(() => { if (!document.hidden && !choosing.current) void load(filters); }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [filters, load]);

  if (error && !data) {
    return (
      <Panel title="Statistics" label="Statistics" strong>
        <p role="alert">The numbers did not load: {error}. <code>mulebox stats</code> gives the same in a terminal.</p>
      </Panel>
    );
  }
  if (!data) return <Panel title="Statistics" label="Statistics" strong><p className="text-ink-2">Adding up job minutes</p></Panel>;
  const { today, all } = data;
  // The series that ran under these filters (a GitHub source leaves only GitHub runs).
  const ran = new Set((all.by.kind ?? []).filter((row) => row.runs || row.unknown).map((row) => row.key));
  const shown = SERIES.map((series) => series.kind).filter((kind) => ran.has(kind));
  const pickFilter = (dim: Dim, value: string) => { kept.filters = { ...filters, [dim]: value }; setFilters(kept.filters); };

  return (
    <Panel title="Statistics" label="Statistics" strong bodyClassName="grid gap-4">
      <div className="flex flex-wrap gap-3">
        {FILTERS.map(([dim, title, everything]) => (
          <FilterSelect key={dim} title={title} everything={everything} value={filters[dim] ?? ""}
            options={(all.choices?.[dim] ?? []).map((key) => [key, label(dim, key)])}
            onChange={(value) => pickFilter(dim, value)}
            onFocus={() => { choosing.current = true; }} onBlur={() => { choosing.current = false; }} />
        ))}
      </div>
      <div className="grid gap-gap md:grid-cols-2"><Head range="today" found={today} /><Head range="all" found={all} /></div>
      <p className="flex items-start gap-2 text-sm text-ink-2">
        <Info aria-hidden className="mt-px size-icon-s" />
        <span>Run time is added up: two jobs side by side for ten minutes count as twenty.</span>
      </p>
      <div className="grid items-start gap-5 lg:grid-cols-2">
        <section aria-label={`Last ${DAYS} days`} className="grid min-w-0 gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">Last {DAYS} days</h3><Legend shown={shown} />
          </div>
          <DayChart days={all.days ?? []} shown={shown} />
        </section>
        <section aria-label="Where the time went" className="grid min-w-0 gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">Where the time went</h3>
            <Segmented small choices={[{ value: "today", label: "Today" }, { value: "all", label: "All time" }]} value={range} label="Period for the table"
              onChange={(next) => { kept.range = next; setRange(next); }} />
          </div>
          <Tabs items={DIMS.map(([id, text]) => ({ id, label: text }))} value={by} label="Break down by"
            onChange={(next) => { kept.by = next; setBy(next); setOpen(false); }} />
          <Breakdown found={range === "today" ? today : all} by={by} title={Object.fromEntries(DIMS)[by]}
            open={open} onToggle={() => setOpen((was) => !was)} />
        </section>
      </div>
    </Panel>
  );
}
