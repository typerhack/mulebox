// The Usage page (`#/usage`; docs/design-system/usage/, option A): what each job really used,
// a row per project and job under the node it ran on, each measure a bar whose whole length is
// that node. Read only: nothing here changes a node. Asked again each minute while open.

import { CircleDashed } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useMachines } from "../../state/live";
import { label } from "../../lib/stats";
import { askUsage, type UsageFilters, type UsageView } from "../../lib/usage";
import { FilterSelect } from "../../ui/FilterSelect";
import { Empty, Panel } from "../../ui/Panel";
import { Segmented } from "../../ui/Segmented";
import { NodeRows } from "./UsageRows";

const REFRESH_MS = 60_000;
const NOTE = "What each job really used, measured every 10 s";
const KINDS: [string, string][] = [["job", "Agent jobs"], ["runner", "GitHub runs"]];
// Kept between visits to the page, not between reloads.
const kept = { filters: {} as UsageFilters, all: false, projects: [] as string[] };

const Key = () => (
  <p className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-2">
    <span className="inline-flex items-center gap-2"><i className="block h-meter w-4 rounded-meter bg-meter-fill" />Usual peak, the median</span>
    <span className="inline-flex items-center gap-2"><i className="block h-meter w-4 rounded-meter bg-meter-soft" />Highest peak</span>
    <span className="inline-flex items-center gap-2"><i className="block h-3 w-hair bg-ink-1" />Fits every run: the highest, rounded up</span>
  </p>
);

export function UsagePage() {
  const panel = useMachines();
  const [view, setView] = useState<UsageView | null | undefined>(undefined);  // null: this server keeps no usage
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState(kept.filters);
  const [all, setAll] = useState(kept.all);
  const [projects, setProjects] = useState(kept.projects);
  const choosing = useRef(false);

  useEffect(() => {
    let gone = false;
    const load = () => askUsage(filters, all).then((found) => {
      if (gone) return;
      setView(found);
      setError(null);
      if (found?.projects) { kept.projects = found.projects; setProjects(found.projects); }
    }, (failure: unknown) => { if (!gone) setError(failure instanceof Error ? failure.message : "no answer"); });
    void load();
    const timer = setInterval(() => { if (!document.hidden && !choosing.current) void load(); }, REFRESH_MS);
    return () => { gone = true; clearInterval(timer); };
  }, [filters, all]);

  if (view === null) {
    return (
      <Panel title="Usage" label="Usage" strong>
        <p className="flex items-start gap-2 text-ink-2">
          <CircleDashed aria-hidden className="mt-px size-icon flex-none" />
          <span>This dashboard's mulebox keeps no usage yet. From 1.36.0 it measures every job and GitHub run.</span>
        </p>
      </Panel>
    );
  }
  if (view === undefined) {
    return (
      <Panel title="Usage" label="Usage" strong>
        {error ? <p role="alert">The figures did not load: {error}. <code>mulebox usage</code> gives the same in a terminal.</p>
          : <p className="text-ink-2">Reading what the jobs used</p>}
      </Panel>
    );
  }
  const pick = (key: keyof UsageFilters, value: string) => { kept.filters = { ...filters, [key]: value }; setFilters(kept.filters); };
  const hold = { onFocus: () => { choosing.current = true; }, onBlur: () => { choosing.current = false; } };
  const filtered = Object.values(filters).some(Boolean);

  return (
    <Panel title="Usage" label="Usage" strong note={<span className="font-normal whitespace-normal text-ink-2">{NOTE}</span>} bodyClassName="grid gap-3">
      <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
        <FilterSelect title="Project" everything="All projects" value={filters.project ?? ""} {...hold}
          options={projects.map((key) => [key, label("project", key)])} onChange={(value) => pick("project", value)} />
        <FilterSelect title="Node" everything="All nodes" value={filters.worker ?? ""} {...hold}
          options={view.machines.map((key) => [key, key])} onChange={(value) => pick("worker", value)} />
        <FilterSelect title="Type" everything="Agent jobs and GitHub runs" value={filters.kind ?? ""} {...hold}
          options={KINDS} onChange={(value) => pick("kind", value)} />
        <Segmented choices={[{ value: "passed", label: "Passed runs" }, { value: "all", label: "All runs" }]} label="Which runs count"
          value={all ? "all" : "passed"} onChange={(next) => { kept.all = next === "all"; setAll(kept.all); }} />
        <span className="num flex min-h-ctl items-center text-sm text-ink-2">the last {view.runs} of each job</span>
      </div>
      <Key />
      {view.nodes.length ? (
        <div className="use-list">
          {view.nodes.map((group) => (
            <NodeRows key={group.name} group={group} all={view.all} machine={panel?.machines.find((m) => m.name === group.name)} />
          ))}
        </div>
      ) : (
        <Empty title={filtered ? "No job matches these filters" : all ? "No job has finished yet" : "No job has passed yet"}
          hint={filtered ? "Choose another project, node or type." : "Usage shows here once a job or a GitHub run finishes. `mulebox usage` prints the same figures."} />
      )}
    </Panel>
  );
}
