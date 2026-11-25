import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../../lib/api";
import { TipProvider } from "../../ui/Tip";
import { CheckNow, HealthLines, HealthUnder } from "./Health";
import { shownState, slotsText } from "./parts";
import { machine } from "./testing";

const DISK = { check: "disk", message: "1.2 GB free on the disk of its cache folder, under its min_free of 5.0 GB",
               fix: "free space on build-2: `mulebox storage clean`", since: 1000 };
const resting = machine({ state: "resting", free_slots: 0, disk_free: 1.2e9, disk_total: 490e9,
  health: { resting: true, problems: [DISK], withheld: [], answers: 0, checked_at: Date.now() / 1000 - 20 } });

afterEach(() => { cleanup(); tokenStore.set(null); vi.restoreAllMocks(); });

describe("a node that rests, on the page", () => {
  it("reads Resting and takes no job", () => {
    expect(shownState(resting).word).toBe("Resting");
    expect(slotsText(resting)).toBe("takes no job");
  });

  it("says the problem once in the strip, with its fix and Storage, and no 10% line beside it", () => {
    render(<TipProvider><ul><HealthLines machines={[resting]} /></ul></TipProvider>);
    expect(screen.getByText("build-2 is resting and takes no job.")).toBeTruthy();
    expect(screen.getByText(/^1.2 GB free on the disk/)).toBeTruthy();
    expect(screen.getByText(/^Free space on build-2:/)).toBeTruthy();  // a sentence: capitalised
    expect(screen.getByRole("link", { name: "Open Storage" })).toBeTruthy();
    expect(screen.queryByText(/under 10%/)).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("checked 20 s ago");
  });

  it("warns of a disk under 10% long before a rest", () => {
    render(<ul><HealthLines machines={[machine({ disk_free: 21e9, disk_total: 250e9 })]} /></ul>);
    expect(screen.getByText("build-2 has 21.0 GB free of 250.0 GB, under 10%.")).toBeTruthy();
  });

  it("Check now asks the node and waits for its answer", async () => {
    tokenStore.set("t");
    const sent = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) =>
      new Response(String(url).endsWith("/api/session") ? '{"action_token": "t"}' : "{}", { status: 200 }));
    const { rerender } = render(<CheckNow machine={resting} />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check now" })); });
    expect(sent.mock.calls.map((call) => String(call[0]))).toContain("/api/machines/build-2/control");
    expect(screen.getByRole("button", { name: "Checking" })).toHaveProperty("disabled", true);
    const answered = { ...resting, health: { ...resting.health!, answers: 1, checked_at: Date.now() / 1000 } };
    rerender(<CheckNow machine={answered} />);
    expect(screen.getByRole("status").textContent).toBe("Still failing, checked just now");
  });

  it("the Machines page's row holds the problem and Check now", () => {
    render(<HealthUnder machine={resting} />);
    expect(screen.getByText("build-2 is resting and takes no job.")).toBeTruthy();
    expect(screen.getByText(/^since /)).toBeTruthy();
  });
});
