import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../../lib/api";
import type { Job, JobDetail, Looks } from "../../lib/types";
import { tickStore } from "../../state/live";
import { TipProvider } from "../../ui/Tip";
import { LooksNote } from "../job/LooksNote";
import { JobCard } from "./JobCard";

const NOW = 1_800_000_000;
const STUCK = "Looks stuck: no output, no CPU, no I/O for 5m 10s in stage command. Last line: \"Running migrations...\". Look at its log or cancel it.";
const job = (looks?: Looks | null, more: Partial<Job> = {}): Job => ({
  job_id: "job-01EXAMPLEE93B21", project: "example-app", job: "migrate", state: "running", kind: "job",
  doing: { stage: "command", cpu_pct: 0 }, looks, ...more,
});
const quiet = (verdict: string, text: string, seconds: number): Looks =>
  ({ verdict, text, stage: "command", last_line: "", limit_s: 120, since: NOW - seconds, quiet_s: seconds });
const card = (row: Job) => render(<TipProvider><JobCard job={row} cores={8} total={1} /></TipProvider>);

beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(NOW * 1000); tokenStore.set("token"); });
afterEach(() => { cleanup(); vi.useRealTimers(); tokenStore.set(undefined); });

describe("a running card's verdict line", () => {
  it("shows nothing for a working job, a job with no verdict, or a verdict it does not know", () => {
    for (const looks of [undefined, null, { verdict: "working", text: "" }, { verdict: "dreaming", text: "Something new." }]) {
      const { container } = card(job(looks));
      expect(container.textContent).not.toMatch(/quiet|Slow|Asks for input|Looks stuck|Waiting on purpose|Something new/);
      expect(screen.queryByText("Open its log")).toBeNull();
      cleanup();
    }
  });

  it.each([
    ["waiting", "Waiting on purpose", "text-queued", 240, "quiet 4m 00s"],
    ["asking", "Asks for input", "text-danger", 150, "quiet 2m 30s"],
    ["stuck", "Looks stuck", "text-danger", 310, "quiet 5m 10s"],
  ])("names %s with its icon in the level's colour and how long it has been quiet", (verdict, label, tone, seconds, figure) => {
    const { container } = card(job(quiet(verdict, "The sentence.", seconds)));
    const line = screen.getByRole("button", { name: new RegExp(label) });
    expect(line.textContent).toContain(figure);
    expect(line.querySelector("svg")?.getAttribute("class")).toContain(tone);
    expect(container.querySelector(".animate-spin")).toBeTruthy();   // still running, still turning
  });

  it("gives a slow job its download's speed, and keeps the Down meter", () => {
    card(job({ verdict: "slow", text: "Downloading slowly: 12 KB/s." }, { doing: { stage: "toolchain", cpu_pct: 0, download: {
      name: "node-v22.tar.xz", done_bytes: 41e6, total_bytes: 300e6, net_bytes_s: 12_000, net_scope: "job" } } }));
    const line = screen.getByRole("button", { name: /Slow download/ });
    expect(line.textContent).toContain("12.0 KB/s");
    expect(line.querySelector("svg")?.getAttribute("class")).toContain("text-warning");
    expect(screen.getByText("Down")).toBeTruthy();
  });

  it("counts the quiet time on from `since` between updates", () => {
    card(job(quiet("stuck", STUCK, 310)));
    act(() => { vi.setSystemTime((NOW + 5) * 1000); tickStore.set(1); });
    expect(screen.getByRole("button", { name: /Looks stuck/ }).textContent).toContain("quiet 5m 15s");
  });

  it("opens in place, by a press, to the sentence, the log and a two-step cancel", () => {
    card(job(quiet("stuck", STUCK, 310)));
    const line = screen.getByRole("button", { name: /Looks stuck/ });
    const panel = document.getElementById(line.getAttribute("aria-controls") ?? "");
    expect(panel?.hidden).toBe(true);
    fireEvent.click(line);
    expect(line.getAttribute("aria-expanded")).toBe("true");
    expect(panel?.hidden).toBe(false);
    expect(screen.getByText(STUCK)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open its log" }).getAttribute("href")).toBe("#/job/job-01EXAMPLEE93B21");
    fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));
    expect(screen.getByRole("button", { name: "Yes, cancel job" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Keep job" })).toBeTruthy();
    fireEvent.click(line);
    expect(panel?.hidden).toBe(true);
  });

  it("offers only the log where this page has no controls", () => {
    tokenStore.set(null);
    card(job(quiet("stuck", STUCK, 310)));
    fireEvent.click(screen.getByRole("button", { name: /Looks stuck/ }));
    expect(screen.getByRole("link", { name: "Open its log" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancel job" })).toBeNull();
  });
});

describe("a job page's verdict strip", () => {
  const note = (looks: Looks | null, more: Partial<JobDetail> = {}) => render(<LooksNote job={{ ...job(looks), ...more }} />);

  it("says the verdict once, with the sentence and the two ways on", () => {
    note(quiet("stuck", STUCK, 310));
    const strip = screen.getByRole("status");
    expect(strip.className).toContain("border-danger");
    expect(strip.textContent).toContain("Looks stuck. No output, no CPU, no I/O for 5m 10s");
    expect(strip.textContent?.match(/Looks stuck/g)).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Go to its last line" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel job" })).toBeTruthy();
  });

  it("is a warning for slow, plain for waiting, and absent for working, none and a finished job", () => {
    note({ verdict: "slow", text: "Downloading slowly: 12 KB/s." });
    expect(screen.getByRole("status").className).toContain("border-warning");
    cleanup();
    note(quiet("waiting", "Quiet for 4m, but its last line says it is waiting.", 240));
    expect(screen.getByRole("status").className).toContain("bg-surface-2");
    expect(screen.getByRole("status").textContent).toContain("Waiting on purpose. Quiet for 4m");
    cleanup();
    for (const [looks, more] of [[null, {}], [{ verdict: "working", text: "" }, {}], [quiet("stuck", STUCK, 310), { state: "finished" }]] as const) {
      expect(note(looks, more).container.innerHTML).toBe("");
      cleanup();
    }
  });

  it("has no cancel where this page has no controls", () => {
    tokenStore.set(null);
    note(quiet("asking", "Waiting for an answer it will never get.", 150));
    expect(screen.queryByRole("button", { name: "Cancel job" })).toBeNull();
    expect(screen.getByRole("button", { name: "Go to its last line" })).toBeTruthy();
  });
});
