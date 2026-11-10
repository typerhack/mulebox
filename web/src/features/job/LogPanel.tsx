// The Log panel of an agent job. Log text is appended as text nodes, never parsed as HTML.
// Following the newest line is a switch: scrolling up turns it off, pressing it jumps back.
// Under the log, a quiet job says how long it has been quiet and whether it is working.

import { ArrowDownToLine, Clock, Radio } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import type { JobDetail } from "../../lib/types";
import { IconButton, LinkButton } from "../../ui/Button";
import { cx } from "../../ui/cx";
import { Panel } from "../../ui/Panel";
import { useLog, type Stream } from "./useLog";

const KEEP_CHARS = 1024 * 1024;  // cap the page, not the job: the full log has its own link
const NEAR_END = 24;
const STREAM_WORD: Record<Stream, string> = {
  connecting: "Connecting", open: "Stream open", lost: "Reconnecting", ended: "Stream ended",
};

export const LOG_BOX = "max-h-log overflow-y-auto rounded-m border border-line bg-surface-2 p-3 font-mono text-sm leading-log break-words whitespace-pre-wrap text-ink-2";

export function StreamState({ stream }: { stream: Stream }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 px-1 text-sm font-medium whitespace-nowrap text-ink-2">
      <Radio aria-hidden className={cx("status-icon size-icon", stream === "open" ? "text-passed"
        : stream === "lost" ? "text-warning" : "text-ink-3")} />
      {STREAM_WORD[stream]}
    </span>
  );
}

interface Props {
  jobId: string;
  quiet: string;
  onState: (state: string) => void;
  onEnd: (job: JobDetail, atEnd: boolean) => void;
}

export function LogPanel({ jobId, quiet, onState, onEnd }: Props) {
  const pre = useRef<HTMLPreElement>(null);
  const [follow, setFollow] = useState(true);
  const following = useRef(true);
  const [fresh, setFresh] = useState(false);  // output came while not following
  const setFollowing = (on: boolean) => { following.current = on; setFollow(on); if (on) setFresh(false); };

  const onChunk = useCallback((text: string) => {
    const box = pre.current;
    if (!box) return;
    box.append(text);
    box.normalize();
    const node = box.firstChild as Text | null;
    if (node && node.length > KEEP_CHARS) node.deleteData(0, node.length - KEEP_CHARS);
    if (following.current) box.scrollTop = box.scrollHeight;
    else setFresh(true);
  }, []);
  const { stream, note } = useLog(jobId, {
    onChunk, onState, onEnd: (job) => onEnd(job, following.current),
  });

  const onScroll = () => {
    const box = pre.current;
    if (!box) return;
    const atEnd = box.scrollTop + box.clientHeight >= box.scrollHeight - NEAR_END;
    if (atEnd !== following.current) setFollowing(atEnd);
  };
  const toggle = () => {
    const box = pre.current;
    if (!following.current && box) box.scrollTop = box.scrollHeight;
    setFollowing(!following.current);
  };

  return (
    <Panel title="Log" label="Log" strong
      note={(
        <span className="inline-flex flex-wrap items-center justify-end gap-2 font-normal">
          <StreamState stream={stream} />
          <IconButton aria-pressed={follow} onClick={toggle}
            label={follow ? "Following the newest line" : fresh ? "New output: jump to the newest line" : "Follow the newest line"}>
            <ArrowDownToLine aria-hidden className={cx("size-icon", fresh && !follow && "text-accent")} />
          </IconButton>
          <LinkButton tone="ghost" href={`/api/jobs/${encodeURIComponent(jobId)}/log.txt`}>Full log as text</LinkButton>
        </span>
      )}>
      <pre ref={pre} tabIndex={0} aria-label="Job log" onScroll={onScroll} className={LOG_BOX} />
      {(note || quiet) && (
        <p role="status" className="mt-2 flex items-start gap-2 text-sm text-ink-2">
          <Clock aria-hidden className="mt-px size-icon-s" /><span>{[note, quiet].filter(Boolean).join(". ")}</span>
        </p>
      )}
    </Panel>
  );
}
