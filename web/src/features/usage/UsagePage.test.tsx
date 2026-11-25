import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { reply } from "../../lib/heldServer.testing";
import type { Machine } from "../../lib/types";
import type { UsageJob } from "../../lib/usage";
import { machinesStore } from "../../state/live";
import { TipProvider } from "../../ui/Tip";
import { UsagePage } from "./UsagePage";

const GB = 1e9;
const job = (project: string, name: string, more: Partial<UsageJob> = {}): UsageJob => ({
  project, job: name, kind: "job", runs: 20, measured: 20, not_measured: 0, no_cores: 0,
  cores: { median: 5.4, max: 6.1 }, memory: { median: 3.1 * GB, max: 3.5 * GB }, fits: { cores: 7, memory: 3.5 * GB },
  machines: ["build-1"], ...more,
});
const JOBS = [
  job("example-app", "lint", { cores: { median: 0.9, max: 1.2 }, memory: { median: 412e6, max: 538e6 }, fits: { cores: 2, memory: 1 * GB } }),
  job("example-app", "check"),
  job("example-org__example-api", "e2e", { kind: "runner", runs: 12, measured: 12 }),
  job("example-site", "format", { no_cores: 20, cores: null, memory: { median: 148e6, max: 212e6 }, fits: { cores: null, memory: 0.5 * GB } }),
  job("example-legacy", "check", { runs: 6, measured: 0, not_measured: 6, cores: null, memory: null, fits: null, machines: ["build-2"] }),
];
const machine = (name: string, more: Partial<Machine> = {}): Machine =>
  ({ name, state: "available", slots: 2, free_slots: 2, capabilities: ["linux", "docker"], jobs: [], version: "1.36.0", ...more });

function serve(status = 200) {
  const asked: string[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    asked.push(url);
    if (status !== 200) return reply("404: Not Found", status);
    const query = new URL(url, "http://x").searchParams, worker = query.get("worker");
    const jobs = JOBS.filter((row) => (!worker || row.machines.includes(worker)) && (!query.get("project") || row.project === query.get("project")));
    return reply({ machines: { "build-1": { cores: 8, memory: 16 * GB }, "build-2": { cores: 4, memory: 8 * GB } },
                   jobs, runs: 20, all: query.get("all") === "1" });
  }));
  return asked;
}
const show = () => render(<TipProvider><UsagePage /></TipProvider>);
const rowOf = (node: string, text: string) =>
  within(screen.getByRole("region", { name: node })).getByRole("link", { name: new RegExp(`/ ${text}$`) }).closest("li") as HTMLElement;

afterEach(() => { cleanup(); vi.unstubAllGlobals(); machinesStore.set(null); });

describe("the Usage page", () => {
  it("groups the jobs by node, heaviest first, each bar on its node's scale with its numbers in words", async () => {
    machinesStore.set({ machines: [machine("build-1"), machine("build-2", { version: "1.35.5" })], total: 2, online: 2, free_slots: 4 });
    serve();
    show();
    const node = await screen.findByRole("region", { name: "build-1" });
    expect(node.textContent).toContain("Linux, 8 cores, 16.0 GB memory");
    expect(node.textContent).toContain("4 jobs, heaviest first");
    expect([...node.querySelectorAll("li a")].map((a) => a.textContent)).toEqual(
      ["example-app / check", "example-api / e2e", "example-app / lint", "example-site / format"]);
    const check = rowOf("build-1", "check");
    expect(check.textContent).toContain("20 passed runs, agent job");
    expect(check.textContent).toContain("6.1 at most, 5.4 usually");
    expect(check.textContent).toContain("3.5 GB at most, 3.1 GB usually");
    expect(check.textContent).toContain("7 of 8 cores");
    const cores = within(check).getByRole("img", { name: "Cores: usually 5.4, at most 6.1, of 8" });
    expect(cores.style.getPropertyValue("--med")).toBe("67.50%");
    expect(cores.style.getPropertyValue("--hi")).toBe("76.25%");
    expect(cores.style.getPropertyValue("--at")).toBe("87.50%");   // the size that fits, 7 of 8
    expect(cores.style.getPropertyValue("--unit")).toBe("12.50%"); // ruled core by core
    expect(within(check).getByRole("link").getAttribute("href")).toBe("#/history?kind=job&project=example-app&job=check");
    expect(rowOf("build-1", "e2e").textContent).toContain("12 passed runs, GitHub run");
  });

  it("says a gap in words and draws no bar for it", async () => {
    machinesStore.set({ machines: [machine("build-1"), machine("build-2", { version: "1.35.5" })], total: 2, online: 2, free_slots: 4 });
    serve();
    show();
    const short = rowOf((await screen.findByRole("region", { name: "build-1" })).getAttribute("aria-label") as string, "format");
    expect(short.textContent).toContain("Cores: too short to measure. Its runs end before two readings, 20 s.");
    expect(short.textContent).toContain("cores not known");
    expect(within(short).getAllByRole("img")).toHaveLength(1);
    const never = rowOf("build-2", "check");
    expect(never.textContent).toContain("Not measured: build-2 runs mulebox 1.35.5, which sends no usage. mulebox setup build-2 upgrades it.");
    expect(within(never).queryByRole("img")).toBeNull();
  });

  it("asks again with a filter and with failed runs taken in", async () => {
    const asked = serve();
    show();
    await screen.findByRole("region", { name: "build-1" });
    expect(asked[0]).toBe("/api/usage?");
    fireEvent.change(screen.getByLabelText("Project"), { target: { value: "example-app" } });
    await waitFor(() => expect(asked.at(-1)).toBe("/api/usage?project=example-app"));
    await waitFor(() => expect(screen.queryByRole("link", { name: /format/ })).toBeNull());
    fireEvent.click(screen.getByRole("radio", { name: "All runs" }));
    await waitFor(() => expect(asked.at(-1)).toBe("/api/usage?project=example-app&all=1"));
    await waitFor(() => expect(rowOf("build-1", "check").textContent).toContain("20 runs, agent job"));
    expect(screen.getByLabelText("Project").querySelectorAll("option")).toHaveLength(5);  // the choices of the unfiltered answer stay
    fireEvent.change(screen.getByLabelText("Project"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("radio", { name: "Passed runs" }));
  });

  it("says calmly that an older mulebox keeps no usage, with no error", async () => {
    serve(404);
    show();
    expect((await screen.findByText(/keeps no usage yet/)).closest("section")?.textContent).not.toMatch(/404|did not load/);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
