// A job's controls on its page: pause or resume, its place in line, boost, and cancel
// (coordinator/job_control.py).
//
// Each acts at once, apart from cancel: none loses work, and each has its way back on the same
// spot. A short line says what is on now, in the words of what it does to this job.
// Cancelling does lose work, so it asks twice, in the page rather than a browser dialog: the
// first press puts "Keep job" under the focus, so Enter or a double press keeps the job.

import { ChevronDown, ChevronUp, ChevronsDown, ChevronsUp, Minus, Pause, Play, Snowflake, X, Zap,
         type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ApiError, cancelJob, controlJob, problemText, type JobAction } from "../../lib/api";
import { RUNNING, WAITING, safeUrl } from "../../lib/format";
import type { JobDetail } from "../../lib/types";
import { Button } from "../../ui/Button";

const live = (job: JobDetail) => WAITING.has(job.state) || RUNNING.has(job.state);

export function steers(job: JobDetail): boolean {
  const runner = job.kind === "runner" && (RUNNING.has(job.state) || Boolean(job.position));
  return (job.kind === "job" || runner) && live(job) && !job.cancel_requested;
}

export function said(job: JobDetail): string {
  const running = RUNNING.has(job.state);
  const parts: string[] = [];
  if (job.paused) {
    parts.push(running ? "Paused: frozen on its machine, containers too. Resume goes on where it stopped."
                       : "Paused: it keeps its place in line and does not start.");
  }
  if (job.boost) {
    parts.push(running ? "Boosted: it gets the machine's CPU and disk first, and the machine takes no new job until it ends."
                       : "Boosted: first in line, and it gets its machine to itself once it starts.");
  } else if (job.position && WAITING.has(job.state)) {
    parts.push(`#${job.position} in line.`);
  }
  return parts.join(" ");
}

// A GitHub run's slot only moves while it waits, and is frozen or boosted once it runs.
export function buttonsFor(job: JobDetail): [JobAction, string, LucideIcon][] {
  const waiting = WAITING.has(job.state), running = RUNNING.has(job.state);
  const holds = job.kind === "job" || !waiting;
  const list: [JobAction, string, LucideIcon][] = [];
  if (holds) list.push(job.paused ? ["resume", "Resume", Play] : ["pause", running ? "Freeze" : "Pause", running ? Snowflake : Pause]);
  if (waiting && job.position) {
    list.push(["first", "To front", ChevronsUp], ["up", "Up", ChevronUp], ["down", "Down", ChevronDown],
              ["last", "To end", ChevronsDown]);
  }
  if (holds) list.push(job.boost ? ["normal", "End boost", Minus] : ["boost", "Boost", Zap]);
  return list;
}

interface SteerProps { job: JobDetail; onChange: (part: Partial<JobDetail>) => void; onProblem: (text: string | null) => void }

export function SteerButtons({ job, onChange, onProblem }: SteerProps) {
  const [busy, setBusy] = useState(false);
  const act = async (action: JobAction) => {
    setBusy(true);
    onProblem(null);
    try {
      onChange(await controlJob(job.job_id, action) as Partial<JobDetail>);
    } catch (failure) {
      onProblem(`Not changed. ${problemText(failure)}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      {buttonsFor(job).map(([action, text, Icon]) => (
        <Button key={action} disabled={busy} onClick={() => void act(action)}>
          <Icon aria-hidden className="size-icon-s" />{text}
        </Button>
      ))}
    </>
  );
}

export function cancellable(job: JobDetail): boolean {
  const upgradeWaits = job.kind === "upgrade" && WAITING.has(job.state);
  const run = job.kind === "runner" && Boolean(safeUrl(job.run_url));  // GitHub is asked
  return (job.kind === "job" || upgradeWaits || run) && live(job) && !job.cancel_requested;
}

type View = "idle" | "armed" | "sending" | "requested" | "gone";

export function CancelControl({ job }: { job: JobDetail }) {
  const [view, setView] = useState<View>("idle");
  const [problem, setProblem] = useState<{ text: string; signIn?: boolean } | null>(null);
  const keep = useRef<HTMLButtonElement>(null), start = useRef<HTMLButtonElement>(null);
  const run = job.kind === "runner";
  const words = run
    ? { start: "Cancel on GitHub", sure: "Yes, cancel the run", keep: "Keep run",
        note: "GitHub is asked to cancel the run; the slot frees when the runner stops.",
        sending: "Asking GitHub", done: "GitHub is cancelling the run." }
    : { start: "Cancel job", sure: "Yes, cancel job", keep: "Keep job",
        note: "This stops the job for whoever is waiting on it.", sending: "Cancelling",
        done: "Cancel requested. The job is stopping." };

  useEffect(() => { if (view === "armed") keep.current?.focus(); }, [view]);
  const disarm = () => { setView("idle"); requestAnimationFrame(() => start.current?.focus()); };
  const send = async () => {
    setView("sending");
    setProblem(null);
    try {
      const done = await cancelJob(job.job_id);
      setView(done.state === "finished" ? "gone" : "requested");
    } catch (failure) {
      const status = failure instanceof ApiError ? failure.status : null;
      if (status === 409) {  // the server knows better than this page by now
        setProblem({ text: failure instanceof Error ? failure.message : "" });
        setView("gone");
        return;
      }
      setProblem(status === 401 ? { text: "Your sign-in has ended.", signIn: true }
                                : { text: `Not cancelled. ${problemText(failure)}` });
      setView("idle");
    }
  };

  const alert = problem && (
    <p role="alert" className="basis-full text-sm font-medium">
      {problem.text} {problem.signIn && <a href="/login">Sign in again</a>}
    </p>
  );
  if (view === "gone") return alert;
  if (view === "sending") return <p role="status" className="text-sm text-ink-2">{words.sending}</p>;
  if (view === "requested") return <p role="status" className="text-sm text-ink-2">{words.done}</p>;
  if (view === "armed") {
    return (
      <span className="inline-flex flex-wrap items-center gap-2"
        onKeyDown={(event) => { if (event.key === "Escape") disarm(); }}>
        <span className="basis-full text-sm text-ink-2">{words.note}</span>
        <Button tone="danger" onClick={() => void send()}>{words.sure}</Button>
        <Button ref={keep} onClick={disarm}>{words.keep}</Button>
      </span>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {alert}
      <Button ref={start} tone="danger" onClick={() => setView("armed")}><X aria-hidden className="size-icon-s" />{words.start}</Button>
    </span>
  );
}
