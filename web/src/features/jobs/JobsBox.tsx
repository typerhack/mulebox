// The Jobs box: tabs with live counts, remembered per browser, each showing one thing. Queue
// is what is happening now, by machine; Failed and Passed are the results that are one or the
// other, GitHub jobs included; Recent is the last finished jobs the queue keeps (a cancelled
// job is neither a pass nor a failure, so only Recent and History list it).

import { TriangleAlert } from "lucide-react";
import { useState } from "react";

import { FAILED, stateOf } from "../../lib/format";
import { remembered } from "../../lib/prefs";
import type { Job, QueueSnapshot } from "../../lib/types";
import { useMachines, useQueue } from "../../state/live";
import { Empty, Panel } from "../../ui/Panel";
import { Tabs, type TabItem } from "../../ui/Tabs";
import { DoneList } from "./DoneList";
import { Lanes } from "./Lanes";

type TabId = "queue" | "failed" | "passed" | "recent";
const TABS: { id: TabId; label: string; pick: (s: QueueSnapshot) => Job[] }[] = [
  { id: "queue", label: "Queue", pick: (s) => [...s.running, ...s.queued] },
  { id: "failed", label: "Failed", pick: (s) => s.recent.filter((j) => FAILED.has(stateOf(j))) },
  { id: "passed", label: "Passed", pick: (s) => s.recent.filter((j) => stateOf(j) === "passed") },
  { id: "recent", label: "Recent", pick: (s) => s.recent },
];
const saved = remembered<TabId>("mulebox-jobs-tab", TABS.map((tab) => tab.id), "queue");
const PANEL_ID = "jobs-panel";

function Finished({ tab, jobs, kept }: { tab: TabId; jobs: Job[]; kept: number }) {
  const scope = tab === "recent" ? `The last ${kept} finished jobs.`
    : jobs.length ? `${jobs.length} of the last ${kept} finished jobs.` : `None of the last ${kept} finished jobs.`;
  return (
    <>
      {jobs.length > 0 && <DoneList jobs={jobs} last="machine" />}
      <p className="pt-3 text-sm text-ink-2">{scope} <a href="#/history">History</a> has them all.</p>
    </>
  );
}

export function JobsBox() {
  const snapshot = useQueue(), machines = useMachines();
  const [tab, setTab] = useState<TabId>(saved.read);
  const choose = (id: TabId) => { saved.write(id); setTab(id); };
  const current = TABS.find((item) => item.id === tab) ?? TABS[0];
  const asked = snapshot ? TABS[0].pick(snapshot).filter((job) => job.question).length : 0;
  const items: TabItem<TabId>[] = TABS.map((item) => ({
    id: item.id, label: item.label, count: snapshot ? item.pick(snapshot).length : null,
    extra: item.id === "queue" && asked ? (
      <span title={`${asked} waiting for an answer`} className="inline-flex items-center gap-1 text-xs">
        <TriangleAlert aria-hidden className="status-icon size-icon-s text-warning" />
        <span className="sr-only">{asked} waiting for an answer</span>
      </span>
    ) : null,
  }));
  return (
    <Panel title="Jobs" label="Jobs" strong>
      <Tabs items={items} value={tab} onChange={choose} label="Job views" panelId={PANEL_ID} className="mb-3" />
      <div role="tabpanel" id={PANEL_ID} aria-labelledby={`tab-${tab}`}>
        {!snapshot ? <Empty title="Waiting for data" hint="If this stays, a browser extension may be blocking the page's scripts; `mulebox queue` shows the same in a terminal." />
          : tab === "queue" ? <Lanes snapshot={snapshot} machines={machines} />
            : <Finished tab={tab} jobs={current.pick(snapshot)} kept={snapshot.recent.length} />}
      </div>
    </Panel>
  );
}
