// Every finished job, newest first, 50 at a time, with the Statistics page's filters, the job
// name, the result and a live search (lib/history.ts). The filters live in the hash, so a
// reload or a shared link keeps them; an answer to a request a newer one replaced is dropped.

import { useCallback, useEffect, useRef, useState } from "react";

import { getJson } from "../../lib/api";
import { HISTORY_FILTERS, RESULTS, anyFilter, historyUrl, parseHistoryHash, setHistoryHash,
         type HistoryKey } from "../../lib/history";
import { useHash } from "../../lib/router";
import { label, type Dim } from "../../lib/stats";
import type { Job } from "../../lib/types";
import { Button } from "../../ui/Button";
import { FilterSelect } from "../../ui/FilterSelect";
import { Panel } from "../../ui/Panel";
import { DoneList } from "../jobs/DoneList";
import { HistorySearch } from "./HistorySearch";

interface Page { jobs: Job[]; next_before: number | null; choices?: Record<string, string[]> }

function optionsFor(key: Dim | "result", choices: Record<string, string[]>, chosen?: string): [string, string][] {
  if (key === "result") return RESULTS;
  const keys = choices[key] ?? [];
  const all = chosen && !keys.includes(chosen) ? [chosen, ...keys] : keys;  // a value from a link
  return all.map((value) => [value, label(key, value)]);
}

export function HistoryPage() {
  const hash = useHash();
  const filters = parseHistoryHash(hash);
  const asked = historyUrl(filters, null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [choices, setChoices] = useState<Record<string, string[]>>({});
  const [note, setNote] = useState("Loading");
  const turn = useRef(0);  // the newest request; an older one's answer is ignored

  const load = useCallback(async (url: string, more: boolean) => {
    const mine = ++turn.current;
    setNote("Loading");
    try {
      const page = await getJson<Page>(url);
      if (mine !== turn.current) return;
      const fresh = page.jobs.map((job) => ({ ...job, section: "recent" as const }));
      setJobs((had) => (more ? [...had, ...fresh] : fresh));
      if (page.choices) setChoices(page.choices);
      setNext(page.next_before);
      setNote(more || fresh.length ? "" : "empty");
    } catch (failure) {
      if (mine === turn.current) setNote(`Could not load the history: ${failure instanceof Error ? failure.message : "no answer"}`);
    }
  }, []);

  useEffect(() => { void load(asked, false); }, [asked, load]);
  const latest = useRef(filters);
  useEffect(() => { latest.current = filters; });
  const pick = (key: HistoryKey, value: string) => setHistoryHash({ ...latest.current, [key]: value });
  const clear = () => setHistoryHash({});
  const filtered = anyFilter(filters);

  return (
    <Panel title="History" label="History" strong
      note={jobs.length ? `${jobs.length} shown${next === null ? "" : ", more below"}` : null}>
      <div className="mb-4 grid gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <HistorySearch value={filters.q ?? ""} onSearch={(text) => pick("q", text)} />
          {filtered && note !== "empty" && <Button tone="ghost" onClick={clear}>Clear filters</Button>}
        </div>
        <div className="grid grid-cols-2 gap-3 md:flex md:flex-wrap">
          {HISTORY_FILTERS.map(([key, title, everything]) => (
            <FilterSelect key={key} title={title} everything={everything} value={filters[key] ?? ""}
              options={optionsFor(key, choices, filters[key])} onChange={(value) => pick(key, value)} />
          ))}
        </div>
      </div>
      {jobs.length > 0 && note !== "empty" && <DoneList jobs={jobs} last="finished" />}
      {note === "empty" ? (
        <div role="status" className="grid justify-items-start gap-2 pt-1 text-sm text-ink-2">
          <p>{filtered ? "No finished jobs match these filters." : "No job has finished yet."}</p>
          {filtered && <Button onClick={clear}>Clear filters</Button>}
        </div>
      ) : note && <p role="status" className="pt-3 text-sm text-ink-2">{note}</p>}
      {next !== null && note !== "empty" && <Button className="mt-3" onClick={() => void load(historyUrl(filters, next), true)}>Load more</Button>}
    </Panel>
  );
}
