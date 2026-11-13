// A running job's download, as its card says it (features/jobs/DownloadMeter.tsx): how far,
// what, how fast, and for how long no byte has moved. The reading is the worker's
// (`doing.download`, docs/interfaces.md); nothing here judges a download, it only words it.

import { bytes, duration } from "./format";
import type { Download } from "./types";

export interface DownloadView {
  share: number | null;    // percent of the total, null unless both the bytes so far and the total are known
  sized: boolean;          // the total is known, whether or not the bytes so far are
  amount: string;          // "12 of 41 MB", "18 MB so far", "906 MB to download"; "at least" first for a floor
  subject: string;         // "pip cache"; "" when nothing names it
  speed: string | null;    // "0.6 MB/s"
  wholeNode: boolean;      // the speed is the node's traffic, not this job's alone
  quiet: string | null;    // "No bytes for 45 s" once the worker counts the download as stopped
  age: number | null;      // how old the printed figures are, in seconds
}

const KINDS: Record<string, string> = {
  cache: "a cache", tool: "a tool", package: "packages", browser: "a browser", image: "images",
};
const known = (value: number | null | undefined): value is number => typeof value === "number" && value >= 0;

// "12 of 41 MB" when both share a unit, as one reads it; else each with its own.
function ofTotal(done: number, total: number): string {
  const [number, unit] = bytes(done).split(" "), whole = bytes(total);
  return whole.endsWith(` ${unit}`) ? `${number} of ${whole}` : `${number} ${unit} of ${whole}`;
}

// A size alone is what is to come, never what has arrived. `floor`: the figures are a lower
// bound (a GitHub runner writes its output in blocks), said in the words, not a hover alone.
function amountOf(done: number | null, total: number | null, floor: boolean): string {
  const least = floor ? "at least " : "";
  if (done !== null && total !== null) return least + ofTotal(done, total);
  if (done !== null) return `${least}${bytes(done)} so far`;
  return total !== null ? `${bytes(total)} to download` : "size not known";
}

const seconds = (s: number) => (s < 90 ? `${Math.round(s)} s` : duration(s));

// The speed to show: the job's own measured traffic first, then what its tool printed, and
// the node's traffic last and named as such, never as the job's.
function speedOf(download: Download): { speed: string | null; wholeNode: boolean } {
  const net = known(download.net_bytes_s) ? download.net_bytes_s : null;
  if (net !== null && download.net_scope === "job") return { speed: `${bytes(net)}/s`, wholeNode: false };
  if (known(download.rate_bytes_s)) return { speed: `${bytes(download.rate_bytes_s)}/s`, wholeNode: false };
  if (net !== null && download.net_scope === "machine") return { speed: `${bytes(net)}/s`, wholeNode: true };
  return { speed: null, wholeNode: false };
}

export function downloadView(download: Download | null | undefined, floor = false): DownloadView | null {
  if (!download) return null;
  const done = known(download.done_bytes) ? download.done_bytes : null;
  const total = known(download.total_bytes) && download.total_bytes > 0 ? download.total_bytes : null;
  const quiet = download.stalled === true
    ? (known(download.quiet_s) ? `No bytes for ${seconds(download.quiet_s)}` : "No bytes moving")
    : null;
  return {
    share: total === null || done === null ? null : Math.min(100, (done / total) * 100),
    sized: total !== null,
    amount: amountOf(done, total, floor),
    subject: download.name?.trim() || KINDS[download.what ?? ""] || "",
    ...(quiet ? { speed: null, wholeNode: false } : speedOf(download)),
    quiet,
    age: known(download.as_of_s) ? download.as_of_s : null,
  };
}
