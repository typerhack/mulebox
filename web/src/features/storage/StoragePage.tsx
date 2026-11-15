// The Storage page (the user's pick, "by project"): for the node the top row shows, its disk
// as one ruler, its automatic cleanup (what it does, what the last one did, Run now), then
// everything mulebox holds there: projects and their branch folders, caches, toolchains,
// runners and Docker's totals, and last the history of its cleanups.
// The numbers are the node's last report, an hour old at most; the page measures nothing.

import { Folder, HardDrive, Lock } from "lucide-react";
import { useRef, useState } from "react";

import { problemText } from "../../lib/api";
import { ago, bytes, plural } from "../../lib/format";
import { useStore } from "../../lib/store";
import { branchOf, cleanable, held, measuredAt, sendKeep, sendRemove, suggestions } from "../../lib/storage";
import { tickStore, useMachines } from "../../state/live";
import { hostOf, pick, pickStore } from "../../state/picked";
import { markGone, refreshStorage, setKeeps, useStorage } from "../../state/storage";
import { Button } from "../../ui/Button";
import { WithCode } from "../../ui/Code";
import { Panel } from "../../ui/Panel";
import { Segmented } from "../../ui/Segmented";
import { CleanupHistory } from "./CleanupHistory";
import { CleanupLine } from "./CleanupLine";
import { DiskRuler } from "./DiskRuler";
import { GoingNextWindow } from "./GoingNext";
import { Head, OtherRows } from "./OtherRows";
import { ProjectRows, type Asking, type Controls } from "./ProjectRows";

export function StoragePage() {
  const { body, problem: unread } = useStorage();
  const panel = useMachines();
  const picked = useStore(pickStore);
  useStore(tickStore);
  const now = Date.now() / 1000;
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [asking, setAsking] = useState<Asking | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [showNext, setShowNext] = useState(false);
  const nextButton = useRef<HTMLButtonElement>(null);

  if (!body) {
    return (
      <Panel strong title="Storage" label="Storage" icon={<HardDrive aria-hidden className="size-icon" />}>
        <p className="text-ink-2">{unread ? `The storage report could not be read. ${unread}` : "Reading what the nodes hold"}</p>
      </Panel>
    );
  }
  const name = body.nodes.find((n) => n.node === picked)?.node ?? body.nodes.find((n) => n.node === hostOf(panel)?.name)?.node
    ?? body.nodes[0]?.node ?? null;
  const node = body.nodes.find((n) => n.node === name) ?? null;
  const report = node?.report ?? null;

  const keep = (project: string, branch: string | null, on: boolean) => {
    setSaid(null);
    sendKeep(project, branch, on).then((reply) => setKeeps(reply.keeps),
      (failure) => setSaid(`Not ${on ? "kept" : "changed"}. ${problemText(failure)}`));
  };
  const remove = async () => {
    if (!asking || busy) return;
    setBusy(true);
    setProblem(null);
    // One folder, the whole project (an idle one's "Clean it"), or each folder that would go anyway.
    const project = report?.projects.find((p) => p.project === asking.project);
    const targets: (string | null)[] = asking.folder !== null ? [asking.folder] : asking.reset ? [null]
      : project ? cleanable(body, project).goes.map((f) => f.folder) : [];
    const failed: string[] = [];
    for (const folder of targets) {
      try {
        const went = await sendRemove(asking.project, folder === null ? null : branchOf(body, asking.project, folder));
        if (went.length) failed.push(...went); else markGone(asking.project, folder);
      } catch (failure) {
        failed.push(problemText(failure));
      }
    }
    if (failed.length) setProblem([...new Set(failed)].join(" "));
    else {
      setAsking(null);
      setSaid("Removed. The sizes follow with each node's next cleanup, within the hour.");
    }
    setBusy(false);
    void refreshStorage();
  };
  const ctl: Controls = {
    editable: body.editable, open, asking, busy, problem, keep, remove,
    toggle: (project) => setOpen((had) => { const next = new Set(had); if (!next.delete(project)) next.add(project); return next; }),
    ask: (next) => { setProblem(null); setSaid(null); setAsking(next); },
  };
  const folders = report?.projects.reduce((a, p) => a + p.folders.length, 0) ?? 0;
  const asks = suggestions(report).length;

  return (
    <Panel strong title="Storage" label="Storage" icon={<HardDrive aria-hidden className="size-icon" />}
      head={body.nodes.length > 1 && (
        <Segmented small label="Node" value={name} choices={body.nodes.map((n) => ({ value: n.node, label: n.node }))}
          onChange={(next) => { setAsking(null); pick(next); }} />
      )}
      note={report ? `${name} holds ${bytes(held(report))}, measured ${ago(measuredAt(report), now)}` : undefined}
      bodyClassName="grid gap-3">
      {!body.editable && (
        <p className="flex items-start gap-3 rounded-m border border-line-strong bg-surface-2 px-3 py-2">
          <Lock aria-hidden className="status-icon mt-px size-icon flex-none text-queued" />
          <span><strong className="font-semibold">Read only: this dashboard's controls are off.</strong>{" "}
            <span className="text-ink-2"><WithCode text="Keep or clean from a dev machine: `mulebox project keep <project>`, `mulebox project reset <project>`." /></span></span>
        </p>
      )}
      {!node ? <p className="text-ink-2">No node has registered yet.</p> : !report ? (
        <p className="text-ink-2">
          <WithCode text={node.online
            ? `${name} has sent no report yet. A node sends one after each sweep, the first a minute after it starts; a node on a mulebox older than 1.24 sends none: upgrade it with \`mulebox setup ${name}\`.`
            : `${name} is offline and never sent a report.`} />
        </p>
      ) : (
        <>
          <DiskRuler report={report} legend />
          <CleanupLine node={node.node} online={node.online} report={report} editable={body.editable} now={now}
            machine={panel?.machines.find((m) => m.name === node.node) ?? null}>
            <Button ref={nextButton} aria-haspopup="dialog" onClick={() => setShowNext(true)}>Show what goes next</Button>
          </CleanupLine>
          {said && <p role="status" className="text-sm font-medium">{said}</p>}
          <div className="keep-list">
            <Head icon={Folder} title="Projects" columns={["Size", "Last job", "What happens"]}
              note={`${plural(folders, "branch folder")}${asks ? `, ${plural(asks, "suggestion")}` : ""}`} />
            <ProjectRows body={body} report={report} now={now} ctl={ctl} />
            {!report.projects.some((p) => p.folders.length || p.home) && <p className="py-2 text-sm text-ink-2">No project has run a job on this node yet.</p>}
            <OtherRows report={report} />
          </div>
          <CleanupHistory sweeps={(body.history ?? []).filter((sweep) => sweep.node === node.node)} body={body}
            days={report.policy.unused_days} now={now} />
          {showNext && (
            <GoingNextWindow node={node.node} body={body} report={report} now={now} opener={nextButton}
              onKeep={body.editable ? keep : undefined} onClose={() => setShowNext(false)} />
          )}
        </>
      )}
    </Panel>
  );
}
