import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Download, Job } from "../../lib/types";
import { TipProvider } from "../../ui/Tip";
import { DownloadMeter } from "./DownloadMeter";
import { JobCard } from "./JobCard";

const MB = 1024 ** 2;
const cache: Download = { what: "cache", name: "npm cache", done_bytes: 12 * MB, total_bytes: 41 * MB,
                          rate_bytes_s: 0.5 * MB, as_of_s: 30, net_bytes_s: 0.6 * MB, net_scope: "job", quiet_s: 0, stalled: false };

afterEach(cleanup);

describe("a card's Down meter", () => {
  it("fills to the share when the total is known, with the word and the speed as two facts", () => {
    const { container } = render(<DownloadMeter download={cache} trails />);
    const meter = screen.getByRole("meter", { name: "Downloaded at least 12.0 of 41.0 MB" });
    expect(meter.getAttribute("aria-valuenow")).toBe("29");
    expect(meter.hasAttribute("data-level")).toBe(false);
    expect(meter.className).toContain("meter-flat");
    expect(screen.getByText("at least 12.0 of 41.0 MB").title).toContain("figures from 30 s ago");
    expect(screen.getByText("Downloading npm cache")).toBeTruthy();
    expect(screen.getByText("614 KB/s").className).toContain("num");
    expect(container.querySelector(".track-open")).toBeNull();
  });

  it("is an open track when the total is not known", () => {
    const { container } = render(<DownloadMeter download={{ what: "package", name: "pnpm install", done_bytes: 18 * MB,
      net_bytes_s: 3 * MB, net_scope: "machine" }} />);
    expect(screen.queryByRole("meter")).toBeNull();
    expect(container.querySelector(".track-open")).toBeTruthy();
    expect(screen.getByRole("img", { name: /total is not known/ })).toBeTruthy();
    expect(screen.getByText("18.0 MB so far")).toBeTruthy();
    expect(screen.getByText("3.0 MB/s, whole node")).toBeTruthy();
  });

  it("shows a GitHub run's floor visibly, and a size alone as an open track, not 0%", () => {
    render(<DownloadMeter download={{ what: "package", done_bytes: 18 * MB }} trails />);
    expect(screen.getByText("at least 18.0 MB so far")).toBeTruthy();
    cleanup();
    const { container } = render(<DownloadMeter download={{ what: "package", name: "torch", total_bytes: 906 * MB }} />);
    expect(screen.queryByRole("meter")).toBeNull();
    expect(container.querySelector(".track-open")).toBeTruthy();
    expect(screen.getByText("906 MB to download")).toBeTruthy();
    expect(container.textContent).not.toMatch(/in all/);
  });

    it("turns to the warning colour and counts the seconds when no byte moves", () => {
    const { container } = render(<DownloadMeter download={{ ...cache, quiet_s: 75, stalled: true }} />);
    expect(screen.getByRole("meter").getAttribute("data-level")).toBe("warn");
    expect(screen.getByText("No bytes for 75 s")).toBeTruthy();
    expect(screen.getByText("npm cache")).toBeTruthy();
    expect(container.querySelector("svg.text-warning")).toBeTruthy();
    expect(container.textContent).not.toMatch(/stalled|KB\/s/i);
  });

  it("is absent while nothing downloads, on the card too", () => {
    expect(render(<DownloadMeter download={null} />).container.innerHTML).toBe("");
    cleanup();
    const job: Job = { job_id: "job-1", project: "example-app", job: "check", state: "running", kind: "job",
                       doing: { stage: "install", cpu_pct: 30, download: null } };
    const { rerender } = render(<TipProvider><JobCard job={job} cores={8} total={1} /></TipProvider>);
    expect(screen.queryByText("Down")).toBeNull();
    rerender(<TipProvider><JobCard job={{ ...job, doing: { ...job.doing, download: cache } }} cores={8} total={1} /></TipProvider>);
    expect(screen.getByText("Down")).toBeTruthy();
    expect(screen.getAllByRole("meter")).toHaveLength(2);
  });
});
