// One job's detail, asked for again every 5 s while it is unfinished, and when the tab comes
// back. The live log's `end` event brings the final state, after which nothing is asked.

import { useCallback, useEffect, useRef, useState } from "react";

import { getJson } from "../../lib/api";
import type { JobDetail } from "../../lib/types";

const ASK_EVERY_MS = 5000;

export interface JobState {
  job: JobDetail | null;
  first: JobDetail | null;   // as it was when the page opened
  error: string | null;
  finish: (final: JobDetail) => void;
  merge: (part: Partial<JobDetail>) => void;
}

export function useJob(jobId: string): JobState {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [first, setFirst] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ended = useRef(false);

  useEffect(() => {
    let gone = false;
    ended.current = false;
    setJob(null);
    setFirst(null);
    setError(null);
    const ask = (opening: boolean) => getJson<JobDetail>(`/api/jobs/${encodeURIComponent(jobId)}`)
      .then((fresh) => {
        if (gone || ended.current) return;
        setJob(fresh);
        if (opening) setFirst(fresh);
      })
      .catch((failure: unknown) => {
        // Later failures are left to the next try, and the log shows the connection.
        if (!gone && opening) setError(failure instanceof Error ? failure.message : "no answer");
      });
    void ask(true);
    const timer = setInterval(() => { if (!document.hidden && !ended.current) void ask(false); }, ASK_EVERY_MS);
    const onShow = () => { if (!document.hidden && !ended.current) void ask(false); };
    document.addEventListener("visibilitychange", onShow);
    return () => { gone = true; clearInterval(timer); document.removeEventListener("visibilitychange", onShow); };
  }, [jobId]);

  const finish = useCallback((final: JobDetail) => { ended.current = true; setJob(final); }, []);
  const merge = useCallback((part: Partial<JobDetail>) => setJob((had) => (had ? { ...had, ...part } : had)), []);
  return { job, first, error, finish, merge };
}
