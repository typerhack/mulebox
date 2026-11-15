// A page left open across an upgrade runs the old code until reloaded: the dashboard restarts
// with every upgrade, so its event stream drops and opens again. On each reopening the page asks
// `/healthz` for the version; when it differs from the one the page loaded with, it reloads,
// keeping its address. Not under an open window (a node's settings, a review), where a reload
// would lose what the viewer is doing: then once no window is open, checked every 2 s.

const WAIT_MS = 2000;

export const isNewer = (loaded: string | undefined, now: string | undefined) =>
  Boolean(loaded && now && loaded !== now);

export const busy = (doc: Document = document) => doc.querySelector('[role="dialog"]') !== null;

export function reloadWhenFree(reload: () => void = () => window.location.reload(),
                               isBusy: () => boolean = busy): () => void {
  if (!isBusy()) {
    reload();
    return () => undefined;
  }
  const timer = setInterval(() => {
    if (isBusy()) return;
    clearInterval(timer);
    reload();
  }, WAIT_MS);
  return () => clearInterval(timer);
}
