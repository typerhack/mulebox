// What one run used (`/api/usage/<id>`), for its page: asked once for a finished job, and every
// 10 s, the worker's own pace, while it runs and its page is open and in view. A job that never
// started has nothing to ask for. No answer, or a server without usage, shows nothing.

import { useEffect, useState } from "react";

import { READ_EVERY_S, askRun, type RunBody } from "../../lib/usage";
import type { JobDetail } from "../../lib/types";

export function useRunUsage(job: Pick<JobDetail, "job_id" | "kind" | "state" | "started_at">): RunBody | null {
  const [found, setFound] = useState<RunBody | null>(null);
  const id = job.job_id, finished = job.state === "finished";
  const measured = job.kind !== "upgrade" && Boolean(job.started_at);
  useEffect(() => {
    if (!measured) return undefined;
    let gone = false;
    const ask = () => askRun(id).then((body) => { if (!gone && body) setFound(body); }, () => undefined);
    void ask();
    if (finished) return () => { gone = true; };
    const timer = setInterval(() => { if (!document.hidden) void ask(); }, READ_EVERY_S * 1000);
    return () => { gone = true; clearInterval(timer); };
  }, [id, finished, measured]);
  return found?.run.job_id === id ? found : null;
}
