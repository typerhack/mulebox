// The hash routes of the page: `#/` the queue, `#/machines`, `#/history`, `#/stats` and
// `#/job/<id>`. A hash needs nothing from the server, so a reload stays where it was.

import { useSyncExternalStore } from "react";

export type Route =
  | { page: "queue" } | { page: "machines" } | { page: "history" } | { page: "stats" }
  | { page: "job"; jobId: string };

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#\/?/, "");
  if (path.startsWith("job/")) {
    let jobId = path.slice(4);
    try { jobId = decodeURIComponent(jobId); } catch { /* a broken escape: use it as typed */ }
    return { page: "job", jobId };
  }
  for (const page of ["machines", "history", "stats"] as const) {
    if (path === page || path.startsWith(`${page}/`)) return { page };
  }
  return { page: "queue" };
}

const subscribe = (listener: () => void) => {
  window.addEventListener("hashchange", listener);
  return () => window.removeEventListener("hashchange", listener);
};

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  return parseRoute(hash);
}

export const go = (hash: string) => { window.location.hash = hash; };
