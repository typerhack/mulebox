import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Sample } from "../../lib/types";
import type { Shown } from "../../state/picked";
import { DiskPanel, MemoryPanel } from "./LoadPanels";

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const GB = 1024 ** 3;
const sample: Sample = {
  t: 1, cpu: [10, 20], memory: { total: 16 * GB, available: 12 * GB, used: 4 * GB },
  swap: { total: 4 * GB, used: 0 }, jobs_memory: 1.5 * GB, docker_disk: 14 * GB, docker: 2,
  self: { cpu: 1.2, rss: 50 * 1024 ** 2 }, viewers: 1,
  disk: [{ roots: ["cache", "jobs"], total: 400 * GB, used: 300 * GB, free: 100 * GB }],
};
const host = (samples: Sample[]) => ({ samples, isHost: true, machine: null, lastSeen: null }) as unknown as Shown;
const fact = (name: string) => screen.getByText(name).closest("p")?.textContent;

describe("the Memory and Disk boxes on the dashboard's machine", () => {
  it("show the jobs' memory, swap and Docker's disk use", () => {
    render(<><MemoryPanel shown={host([sample])} now={2} /><DiskPanel shown={host([sample])} now={2} /></>);
    expect(fact("Jobs")).toBe("Jobs1.5 GB");
    expect(fact("Swap")).toBe("Swap0 B of 4.0 GB");
    expect(fact("Docker")).toBe("Docker14.0 GB");
    expect(screen.queryByText("Available")).toBeNull();
  });

  it("say n/a when a reading is missing, and Off without swap", () => {
    const bare = { ...sample, swap: { total: 0, used: 0 }, jobs_memory: null, docker_disk: null };
    render(<><MemoryPanel shown={host([bare])} now={2} /><DiskPanel shown={host([bare])} now={2} /></>);
    expect(fact("Jobs")).toBe("Jobsn/a");
    expect(fact("Swap")).toBe("SwapOff");
    expect(fact("Docker")).toBe("Dockern/a");
  });
});
