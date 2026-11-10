// The History page's filters (docs/interfaces-m2.md, /api/history): the Statistics page's
// own (lib/stats.ts FILTERS), the job name, the result and a search. They live in the hash,
// `#/history?project=example-app&q=main`, so a reload and a shared link keep them.

import { FILTERS, type Dim } from "./stats";

export type HistoryKey = Dim | "result" | "q";
export type HistoryFilters = Partial<Record<HistoryKey, string>>;

export const RESULTS: [string, string][] = [["passed", "Passed"], ["failed", "Failed"], ["cancelled", "Cancelled"]];
// The dropdowns, in order: the Statistics page's four, then job name and result.
export const HISTORY_FILTERS: [Dim | "result", string, string][] = [
  ...FILTERS, ["job", "Job name", "All job names"], ["result", "Result", "All results"]];
const KEYS: HistoryKey[] = [...HISTORY_FILTERS.map(([key]) => key), "q"];
export const SEARCH_MS = 300;

// The filters in a hash such as `#/history?kind=job&q=fix`; unknown names are left out.
export function parseHistoryHash(hash: string): HistoryFilters {
  const at = hash.indexOf("?");
  if (at < 0) return {};
  const found: HistoryFilters = {};
  new URLSearchParams(hash.slice(at + 1)).forEach((value, key) => {
    if ((KEYS as string[]).includes(key) && value) found[key as HistoryKey] = value;
  });
  return found;
}

const asQuery = (filters: HistoryFilters) =>
  new URLSearchParams(KEYS.filter((key) => filters[key]).map((key) => [key, filters[key] as string]));

export function historyHash(filters: HistoryFilters): string {
  const query = asQuery(filters).toString();
  return query ? `#/history?${query}` : "#/history";
}

// The request for one page: the filters and, after the first page, where it left off.
export function historyUrl(filters: HistoryFilters, before: number | null, limit = 50): string {
  const query = asQuery(filters);
  query.set("limit", String(limit));
  if (before !== null) query.set("before", String(before));
  return `/api/history?${query}`;
}

export const anyFilter = (filters: HistoryFilters) => KEYS.some((key) => filters[key]);

// Swap the hash in place: a filter is not a step back, so it adds no browser history. The
// hashchange it sends lets the router and the page read the new filters.
export function setHistoryHash(filters: HistoryFilters) {
  const hash = historyHash(filters);
  if (window.location.hash === hash) return;
  window.history.replaceState(window.history.state, "", hash);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

// Calls `run` once `ms` have passed with no new call; `cancel` drops a waiting call.
export function debounce<A extends unknown[]>(run: (...args: A) => void, ms: number) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const call = (...args: A) => {
    clearTimeout(timer);
    timer = setTimeout(() => run(...args), ms);
  };
  call.cancel = () => clearTimeout(timer);
  return call;
}
