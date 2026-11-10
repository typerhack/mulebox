// Every finished job, newest first, 50 at a time, with a filter by project.

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { getJson } from "../../lib/api";
import type { Job } from "../../lib/types";
import { Button } from "../../ui/Button";
import { Panel } from "../../ui/Panel";
import { DoneList } from "../jobs/DoneList";

interface Page { jobs: Job[]; next_before: number | null }

export function HistoryPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [note, setNote] = useState("Loading");
  const [typed, setTyped] = useState("");
  const project = useRef("");

  const load = useCallback(async (before: number | null) => {
    const query = new URLSearchParams({ limit: "50" });
    if (before !== null) query.set("before", String(before));
    if (project.current) query.set("project", project.current);
    setNote("Loading");
    try {
      const page = await getJson<Page>(`/api/history?${query}`);
      const fresh = page.jobs.map((job) => ({ ...job, section: "recent" as const }));
      setJobs((had) => {
        const all = before === null ? fresh : [...had, ...fresh];
        setNote(all.length ? "" : "No finished jobs match.");
        return all;
      });
      setNext(page.next_before);
    } catch (failure) {
      setNote(`Could not load the history: ${failure instanceof Error ? failure.message : "no answer"}`);
    }
  }, []);

  useEffect(() => { void load(null); }, [load]);
  const filter = (event: FormEvent) => {
    event.preventDefault();
    project.current = typed.trim();
    void load(null);
  };

  return (
    <Panel title="History" label="History" strong
      note={jobs.length ? `${jobs.length} shown${next === null ? "" : ", more below"}` : null}>
      <form onSubmit={filter} className="mb-3 flex flex-wrap gap-2">
        <input type="search" value={typed} onChange={(event) => setTyped(event.target.value)}
          placeholder="Project name" aria-label="Filter by project"
          className="h-ctl touch:h-ctl-touch min-w-0 flex-1 basis-col-m rounded-m border border-line-strong bg-surface-1 px-3 text-ink-1 placeholder:text-ink-3" />
        <Button type="submit">Filter</Button>
      </form>
      {jobs.length > 0 && <DoneList jobs={jobs} last="finished" />}
      {note && <p role="status" className="pt-3 text-sm text-ink-2">{note}</p>}
      {next !== null && <Button className="mt-3" onClick={() => void load(next)}>Load more</Button>}
    </Panel>
  );
}
