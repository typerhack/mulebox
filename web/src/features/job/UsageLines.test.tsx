import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { reply } from "../../lib/heldServer.testing";
import type { Job, JobDetail } from "../../lib/types";
import type { Peaks, RunBody } from "../../lib/usage";
import { TipProvider } from "../../ui/Tip";
import { useRunUsage } from "./useRunUsage";
import { RunTimePanel, StagesPanel } from "./Waterfall";

const GB = 1e9;
const STAGES = ["prepare", "install", "setup", "command"];
const agent = (state: string): JobDetail => ({
  job_id: "job-1", kind: "job", state, created_at: 0, started_at: 100, finished_at: state === "finished" ? 140 : null,
  steps: STAGES.map((stage, index) => ({ stage, started_at: 100 + index * 10,
                                         finished_at: state !== "finished" && index === 3 ? null : 110 + index * 10 })),
}) as JobDetail;
const ci = (state: string) => ({ job_id: "job-1", kind: "runner", state, created_at: 0, started_at: 100,
                                 finished_at: state === "finished" ? 230 : null }) as JobDetail;
const used = (state: string, usage: Peaks | null, more: Partial<RunBody["run"]> = {}): RunBody => ({
  machines: { "build-1": { cores: 8, memory: 16 * GB } },
  run: { job_id: "job-1", kind: "job", worker: "build-1", state, run_s: 232, usage, average_cores: 3.5, ...more },
});
const FULL: Peaks = { peak_cores: 6.1, peak_cores_stage: "command", peak_memory: 3.5 * GB, peak_memory_stage: "install", cpu_s: 812, samples: 23 };
const live = { job_id: "job-1", kind: "job", state: "running", doing: { stage: "command", cpu_pct: 390 } } as Job;
const rowOf = (stage: string) => screen.getByText(stage).closest("li") as HTMLElement;
const show = (panel: React.ReactNode) => render(<TipProvider>{panel}</TipProvider>);

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("what a run used, on its Stages panel", () => {
  it("writes each peak under the stage it happened in, and the average as the last line", () => {
    show(<StagesPanel job={agent("finished")} live={null} cores={8} now={200} used={used("finished", FULL)} />);
    expect(rowOf("command").textContent).toContain("6.1 of 8 cores, its busiest 10 s");
    expect(rowOf("install").textContent).toContain("3.5 GB of 16.0 GB, the most it held");
    expect(rowOf("setup").textContent).not.toMatch(/cores|held/);
    const panel = screen.getByRole("region", { name: "Stages" });
    expect(panel.lastElementChild?.lastElementChild?.textContent).toBe("3.5 cores on average over 3m 52s, from 23 readings.");
    expect(panel.textContent).not.toContain("so far");
    expect(panel.textContent).not.toContain("peak so far");
  });

  it("says so far while the job runs, and ticks the Cores meter at the peak so far", () => {
    show(<StagesPanel job={agent("running")} live={live} cores={8} now={135} used={used("running", { ...FULL, peak_cores: 4.2, samples: 3 })} />);
    expect(rowOf("command").textContent).toContain("4.2 of 8 cores, its busiest 10 s so far");
    const meter = screen.getByRole("meter", { name: "Cores this job uses: 3.9 of 8, its peak so far 4.2" });
    expect((meter.parentElement?.querySelector(".meter-tick") as HTMLElement).style.getPropertyValue("--at")).toBe("52.5%");
    expect(screen.getByText("On Cores: its peak so far")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Stages" }).textContent).toContain("3.5 cores on average over 3m 52s so far, from 3 readings.");
  });

  it("puts a peak whose stage is not drawn under the last stage, by name", () => {
    show(<StagesPanel job={agent("finished")} live={null} cores={8} now={200} used={used("finished", { ...FULL, peak_cores_stage: "cleanup" })} />);
    expect(rowOf("command").textContent).toContain("6.1 of 8 cores, its busiest 10 s, in cleanup");
  });

  it("says a gap in words: too short for cores, and never measured", () => {
    const short = { peak_cores: null, peak_memory: 212e6, peak_memory_stage: "command", samples: 1 };
    const { unmount } = show(<StagesPanel job={agent("finished")} live={null} cores={8} now={200}
      used={used("finished", short, { average_cores: null })} />);
    expect(rowOf("command").textContent).toContain("212.0 MB of 16.0 GB, the most it held");
    expect(screen.getByText("Too short to measure cores: it ended before two readings. Memory from 1 reading.")).toBeTruthy();
    unmount();
    show(<StagesPanel job={agent("finished")} live={null} cores={8} now={200} used={used("finished", null)} version="1.35.5" />);
    expect(screen.getByText("Cores and memory were not measured: build-1 runs mulebox 1.35.5, which sends no usage.")).toBeTruthy();
  });

  it("shows nothing new without an answer, or before a running job's first reading", () => {
    const { unmount } = show(<StagesPanel job={agent("finished")} live={null} cores={8} now={200} used={null} />);
    expect(screen.getByRole("region", { name: "Stages" }).textContent).not.toMatch(/cores|measured|held/);
    unmount();
    show(<StagesPanel job={agent("running")} live={live} cores={8} now={135} used={used("running", {})} />);
    const panel = screen.getByRole("region", { name: "Stages" });
    expect(panel.textContent).not.toMatch(/measured|held|average/);
    expect(panel.querySelector(".meter-tick")).toBeNull();
  });
});

describe("what a GitHub run used, on its Time panel", () => {
  it("sets both lines under its one bar and names the step of each", () => {
    const peaks = { ...FULL, peak_cores: 5.9, peak_cores_stage: "Run tests", peak_memory: 7.4 * GB, peak_memory_stage: "Install dependencies" };
    show(<RunTimePanel job={ci("running")} live={{ ...live, kind: "runner" }} cores={8} now={230}
      used={used("running", peaks, { kind: "runner", average_cores: 3.1, run_s: 130 })} />);
    const row = within(screen.getByRole("region", { name: "Time" })).getByRole("listitem");
    expect(row.textContent).toContain("5.9 of 8 cores, its busiest 10 s so far, in Run tests");
    expect(row.textContent).toContain("7.4 GB of 16.0 GB, the most it held so far, in Install dependencies");
    expect(screen.getAllByText(/The cores count the run's Compose containers/)).toHaveLength(1);
    expect(screen.getByText(/3.1 cores on average/).closest("p")?.textContent).toContain("over 2m 10s so far, from 23 readings.");
  });
});

function Asker({ job }: { job: JobDetail }) {
  const found = useRunUsage(job);
  return <p>{found ? `peak ${found.run.usage?.peak_cores}` : "nothing"}</p>;
}

describe("asking for one run's usage", () => {
  it("asks every 10 s while the job runs and once more when it ends", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let peak = 1;
    const fetched = vi.fn(() => reply(used("running", { peak_cores: peak++, samples: 2 })));
    vi.stubGlobal("fetch", fetched);
    const { rerender } = render(<Asker job={agent("running")} />);
    await waitFor(() => expect(screen.getByText("peak 1")).toBeTruthy());
    await vi.advanceTimersByTimeAsync(10_000);
    await waitFor(() => expect(screen.getByText("peak 2")).toBeTruthy());
    rerender(<Asker job={agent("finished")} />);
    await waitFor(() => expect(screen.getByText("peak 3")).toBeTruthy());
    await vi.advanceTimersByTimeAsync(30_000);
    expect(fetched).toHaveBeenCalledTimes(3);
    expect(fetched).toHaveBeenLastCalledWith("/api/usage/job-1", expect.anything());
  });

  it("asks nothing for a job that never started, and shows nothing on a 404", async () => {
    const fetched = vi.fn(() => reply("404: Not Found", 404));
    vi.stubGlobal("fetch", fetched);
    const { unmount } = render(<Asker job={{ ...agent("queued"), started_at: null }} />);
    expect(fetched).not.toHaveBeenCalled();
    unmount();
    render(<Asker job={agent("finished")} />);
    await waitFor(() => expect(fetched).toHaveBeenCalledTimes(1));
    expect(screen.getByText("nothing")).toBeTruthy();
  });
});
