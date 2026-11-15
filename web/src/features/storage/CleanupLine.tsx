// The automatic cleanup of a node, at the top of the Storage page: whether it is on and what
// it does, as the node's settings stand; what its last cleanup did and what goes next; what
// mulebox holds against the sizes at which it warns and stops. With the controls on, Settings
// opens the node's settings window on its Storage tab, and Run now runs the cleanup at once,
// Docker too, and shows each node's own answer.

import { CircleCheck, CirclePause, OctagonAlert, Play, Settings2, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { problemText } from "../../lib/api";
import { ago, bytes, plural } from "../../lib/format";
import { TRIGGERS, nextLine, policyLines, sendSweep, sizeState, type Report, type SweepAnswer } from "../../lib/storage";
import type { Machine } from "../../lib/types";
import { refreshStorage } from "../../state/storage";
import { Button } from "../../ui/Button";
import { cx } from "../../ui/cx";
import { NodeSettingsWindow } from "../machines/NodeSettings";

const REREAD_MS = [3000, 12000, 30000];  // the node's next report follows its cleanup by seconds

// The settings window opens on its first tab; the Storage tab is pressed for the viewer once the
// window has read the node's settings and drawn its tabs.
function useStorageTab(open: boolean) {
  useEffect(() => {
    if (!open) return undefined;
    let tries = 0;
    const timer = setInterval(() => {
      const tab = document.getElementById("tab-storage");
      tries += 1;
      if (tab) tab.click();
      if (tab || tries > 40) clearInterval(timer);
    }, 100);
    return () => clearInterval(timer);
  }, [open]);
}

function Size({ report }: { report: Report }) {
  const size = sizeState(report);
  const limits = [size.warn !== null && `warns agents over ${bytes(size.warn)}`,
                  size.max !== null && `removes older folders over ${bytes(size.max)}`].filter(Boolean).join("; ");
  return (
    <p className={cx("flex items-start gap-2 text-sm", size.warned || size.over > 0 ? "font-medium text-warning" : "text-ink-2")}>
      {(size.warned || size.over > 0) && <TriangleAlert aria-hidden className="status-icon mt-px size-icon-s flex-none" />}
      <span>
        mulebox holds <strong className="num font-semibold">{bytes(size.held)}</strong> on this node{limits ? `; ${limits}` : ""}.
        {size.warned && size.warn !== null && ` That is ${bytes(size.held - size.warn)} over the size at which agents are warned.`}
        {size.over > 0 && size.max !== null && ` Still ${bytes(size.over)} over the limit: what is left ${
          size.blocks.length ? `are ${size.blocks.join(", ").replace(/, ([^,]*)$/, " and $1")} folders, which the cleanup never removes` : "is not branch folders"}.`}
      </span>
    </p>
  );
}

interface Props {
  node: string;
  online: boolean;
  report: Report;
  editable: boolean;
  machine: Machine | null;      // the node's row, for its settings window
  now: number;
  children?: ReactNode;         // more buttons beside these (what goes next)
}

export function CleanupLine({ node, online, report, editable, machine, now, children }: Props) {
  const { on, rules } = policyLines(report.policy);
  const last = report.sweep ?? null;
  const [settings, setSettings] = useState(false);
  const [running, setRunning] = useState(false);
  const [answers, setAnswers] = useState<SweepAnswer[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  useStorageTab(settings);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const run = async () => {
    setRunning(true);
    setAnswers(null);
    setProblem(null);
    try {
      setAnswers(await sendSweep(node));
      timers.current = REREAD_MS.map((ms) => setTimeout(() => void refreshStorage(), ms));
    } catch (failure) {
      setProblem(problemText(failure));
    }
    setRunning(false);
  };
  const StateIcon = on ? CircleCheck : CirclePause;
  const freedDocker = last?.docker ? last.docker.build_cache + last.docker.images : 0;

  return (
    <section aria-label="Automatic cleanup" className="grid gap-2 rounded-m border border-line bg-surface-2 px-3 py-3">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <StateIcon aria-hidden className={cx("status-icon mt-px size-icon flex-none", on ? "text-passed" : "text-warning")} />
        <p className="min-w-0 flex-1 basis-col-l">
          <strong className="font-semibold">Automatic cleanup: {on ? "on" : "off"}.</strong>{" "}
          {!on && "mulebox only measures and removes nothing by itself. "}
          {rules.join("; ")}.
        </p>
        <span className="flex flex-wrap gap-2">
          {children}
          {editable && machine && (
            <Button ref={opener} aria-haspopup="dialog" onClick={() => setSettings(true)}>
              <Settings2 aria-hidden className="size-icon-s" />Settings
            </Button>
          )}
          {editable && (
            <Button disabled={running || !online} title={online ? undefined : "The node is offline"} onClick={() => void run()}>
              <Play aria-hidden className="size-icon-s" />{running ? "Cleaning" : "Run now"}
            </Button>
          )}
        </span>
      </div>
      <p className="text-sm text-ink-2">
        {last ? (
          <>
            <strong className="font-medium text-ink-1">
              The last cleanup, {ago(last.started, now)} ({TRIGGERS[last.trigger]?.toLowerCase() ?? last.trigger}),{" "}
              {last.count ? `removed ${plural(last.count, "branch folder")}, ${bytes(last.bytes)}` : "removed no branch folder"}
              {last.slimmed ? `, slimmed ${plural(last.slimmed, "branch folder")}, ${bytes(last.slimmed_bytes ?? 0)}` : ""}
              {last.docker ? ` and freed ${bytes(freedDocker)} in Docker` : ""}.
            </strong>{" "}
            {last.errors.length > 0 && `${plural(last.errors.length, "error")}, in the history below. `}
          </>
        ) : report.removed.count ? `The last cleanup, ${ago(report.at, now)}, removed ${plural(report.removed.count, "branch folder")}, ${bytes(report.removed.bytes)}. `
          : `The last cleanup, ${ago(report.at, now)}, removed nothing. `}
        {nextLine(report, now)}{!online && " The node is offline now."}
      </p>
      <Size report={report} />
      {problem && (
        <p role="alert" className="flex items-start gap-2 text-sm font-medium">
          <OctagonAlert aria-hidden className="status-icon mt-px size-icon-s flex-none text-danger" />Not run. {problem}
        </p>
      )}
      {answers && (
        <ul role="status" aria-label="The cleanup's answers" className="grid gap-1 border-t border-line pt-2 text-sm">
          {answers.map((answer) => (
            <li key={answer.node} className="flex items-start gap-2">
              {answer.ok ? <CircleCheck aria-hidden className="status-icon mt-px size-icon-s flex-none text-passed" />
                : <OctagonAlert aria-hidden className="status-icon mt-px size-icon-s flex-none text-danger" />}
              <span className="min-w-0"><strong className="font-semibold">{answer.node}</strong>{" "}
                <span className="whitespace-pre-line wrap-anywhere">{answer.text}</span></span>
            </li>
          ))}
          <li className="text-ink-2">The page follows with the node's next report, in a few seconds.</li>
        </ul>
      )}
      {settings && machine && <NodeSettingsWindow machine={machine} opener={opener} onClose={() => setSettings(false)} />}
    </section>
  );
}
