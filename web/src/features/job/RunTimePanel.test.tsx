import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { JobDetail } from "../../lib/types";
import { TipProvider } from "../../ui/Tip";
import { RunTimePanel } from "./Waterfall";

afterEach(cleanup);

const run = (outcome?: string) => ({
  job_id: "job-1", kind: "runner", state: "finished", created_at: 0, started_at: 10, finished_at: 34,
  ci_result: outcome ? { outcome } : null,
}) as unknown as JobDetail;

describe("a GitHub run's Time panel", () => {
  it.each([["failed", /failed/i], ["cancelled", /cancelled/i], ["passed", /passed/i], [undefined, /released/i]])(
    "marks the run %s from its own result", (outcome, word) => {
      render(<TipProvider><RunTimePanel job={run(outcome)} live={null} cores={null} now={40} /></TipProvider>);
      expect(screen.getByRole("img", { name: word })).toBeTruthy();
    });
});
