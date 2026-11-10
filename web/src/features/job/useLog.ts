// A job's live log. A reopened stream resumes by byte offset; the stream ends with an `end`
// event. The note says what the stream is doing until output arrives: a blank box must never
// mean "connected and empty" and "could not connect" at once. A browser allows about six
// open connections per site over plain HTTP, so with several tabs open the stream can wait in
// line; the full log link is a plain request and still works.

import { useEffect, useRef, useState } from "react";

import { liveStream } from "../../lib/live";
import type { JobDetail } from "../../lib/types";

const TAIL = 256 * 1024;
// eslint-disable-next-line no-control-regex
const ANSI = /\x1b\[[0-9;?]*[ -/]*[@-~]/g;
export const EARLIER = "[earlier output not shown, see the full log]\n";

export type Stream = "connecting" | "open" | "lost" | "ended";
export interface LogHandlers {
  onChunk: (text: string) => void;
  onState?: (state: string) => void;
  onEnd: (job: JobDetail) => void;
}

export function useLog(jobId: string, handlers: LogHandlers): { stream: Stream; note: string } {
  const [stream, setStream] = useState<Stream>("connecting");
  const [note, setNote] = useState("Connecting to the live log");
  const latest = useRef(handlers);
  latest.current = handlers;

  useEffect(() => {
    let offset: number | null = null, started = false;
    const url = () => {
      const query = offset === null ? `tail=${TAIL}` : `offset=${offset}`;
      return `/api/jobs/${encodeURIComponent(jobId)}/log?${query}`;
    };
    setStream("connecting");
    setNote("Connecting to the live log");
    const stop = liveStream(url, {
      state: (event) => latest.current.onState?.((JSON.parse(event.data) as { state: string }).state),
      log: (event) => {
        const chunk = JSON.parse(event.data) as { offset: number; next_offset: number; data: string };
        if (!started) {
          started = true;
          setNote("");
          if (chunk.offset > 0) latest.current.onChunk(EARLIER);
        }
        latest.current.onChunk(chunk.data.replace(ANSI, ""));
        offset = chunk.next_offset;
      },
      end: (event) => {
        stop();
        setStream("ended");
        setNote(started ? "" : "The job wrote no output");
        latest.current.onEnd(JSON.parse(event.data) as JobDetail);
      },
    }, {
      opened: () => { setStream("open"); setNote(started ? "" : "Connected, no output yet"); },
      lost: (closed) => {
        setStream("lost");
        setNote(closed ? "Live log closed, trying again; the full log link works meanwhile"
                       : "Live log not connected, retrying; the full log link works meanwhile");
      },
    });
    return stop;
  }, [jobId]);

  return { stream, note };
}
