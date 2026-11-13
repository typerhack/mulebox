// The Order panel while things move under it: a save still in flight, answers that come back
// out of order, another viewer's change, and a line whose lane goes while the panel is open.

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../../lib/api";
import { heldServer } from "../../lib/heldServer.testing";
import { REREAD_MS } from "../../lib/turns";
import type { Job, Rules, RulesBody } from "../../lib/types";
import { machinesStore, queueStore } from "../../state/live";
import { EMPTY_ORDER, orderStore } from "../../state/order";
import { TipProvider } from "../../ui/Tip";
import { JobsBox } from "../jobs/JobsBox";
import { OrderHarness } from "./testing";

const rules = (more: Partial<Rules> = {}): Rules =>
  ({ projects: {}, branches: {}, workflows: {}, github: 0, aging_min: 30, shortest_first: false, fair_turns: false, ...more });
const body = (stored: Rules): RulesBody =>
  ({ rules: stored, defaults: rules(), levels: { min: -3, max: 3, words: { low: -1, normal: 0, high: 1 } }, projects: ["example-app"] });

// A server holding the rules: a read gives them, a change replaces them with `after`.
function stored(first: Rules, after?: Rules) {
  let now = first;
  const api = heldServer((_url, post) => {
    if (post && after) now = after;
    return body(now);
  });
  return { ...api, set: (next: Rules) => { now = next; } };
}

const dialog = () => screen.getByRole("dialog", { name: "Order of the line" });
const toggle = (name: string) => within(dialog()).getByRole("switch", { name });
const on = (name: string) => toggle(name).getAttribute("aria-checked") === "true";
const order = () => screen.getAllByRole("button", { name: /^Order/ })[0];

async function openPanel() {
  render(<OrderHarness />);
  fireEvent.click(order());
  await within(await screen.findByRole("dialog")).findByRole("switch", { name: "Fair turns" });
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  tokenStore.set(undefined);
  queueStore.set({ snapshot: null, at: 0 });
  machinesStore.set(null);
  orderStore.set(EMPTY_ORDER);
});

describe("the Order panel while things move", () => {
  it("takes no edit while a save is on its way, so none is lost", async () => {
    const api = stored(rules());
    tokenStore.set("token");
    await openPanel();
    fireEvent.click(toggle("Fair turns"));
    api.hold();
    fireEvent.click(within(dialog()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.posts()).toHaveLength(1));
    expect((toggle("Shortest first") as HTMLButtonElement).disabled).toBe(true);
    expect((within(dialog()).getAllByRole("radio", { name: "High" })[0] as HTMLButtonElement).disabled).toBe(true);
    expect((within(dialog()).getAllByRole("button", { name: "Add" })[0] as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(toggle("Shortest first"));  // a click meanwhile changes nothing
    expect(on("Shortest first")).toBe(false);
    await api.posts()[0].answer(body(rules({ fair_turns: true })));
    expect((toggle("Shortest first") as HTMLButtonElement).disabled).toBe(false);
    expect(on("Fair turns")).toBe(true);
  });

  it("lays only the viewer's own edits over rules another viewer changed", async () => {
    const api = stored(rules());
    tokenStore.set("token");
    await openPanel();
    fireEvent.click(toggle("Shortest first"));  // unsaved
    fireEvent.keyDown(dialog(), { key: "Escape" });
    api.set(rules({ fair_turns: true }));  // someone else turns fair turns on
    fireEvent.click(order());
    await waitFor(() => expect(on("Fair turns")).toBe(true));
    expect(on("Shortest first")).toBe(true);
    fireEvent.click(within(dialog()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.posts()).toHaveLength(1));
    expect(api.posts()[0].body).toEqual({ rules: { shortest_first: true } });
  });

  it("drops a read asked before a save and answered after it", async () => {
    const api = stored(rules());
    tokenStore.set("token");
    await openPanel();
    api.hold();
    fireEvent.click(order());  // closes
    fireEvent.click(order());  // opens again: a read on its way
    await waitFor(() => expect(api.gets()).toHaveLength(1));
    fireEvent.click(toggle("Fair turns"));
    fireEvent.click(within(dialog()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.posts()).toHaveLength(1));
    await api.posts()[0].answer(body(rules({ fair_turns: true })));
    await api.gets()[0].answer(body(rules()));  // the old read, last
    expect(on("Fair turns")).toBe(true);
    expect(within(dialog()).queryByText("Saving")).toBeNull();
    expect(within(dialog()).getByText("Saved. The line follows these rules now.")).toBeTruthy();
  });

  it("reads the rules again while open, keeping what is not saved", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = stored(rules());
    tokenStore.set("token");
    await openPanel();
    fireEvent.click(toggle("Shortest first"));
    const before = api.gets().length;
    api.set(rules({ fair_turns: true }));
    await act(async () => { await vi.advanceTimersByTimeAsync(REREAD_MS); });
    expect(api.gets().length).toBe(before + 1);
    expect(on("Fair turns")).toBe(true);
    expect(on("Shortest first")).toBe(true);
    expect(within(dialog()).getByText("Unsaved changes")).toBeTruthy();
  });
});

describe("the Order panel over live lanes", () => {
  const job = (id: string): Job =>
    ({ job_id: `job-${id}`, project: "example-app", job: "check", state: "queued", kind: "job", section: "queued",
       position: 1, can_run_on: ["build-1", "build-2"] });

  it("stays open with what is typed when its lane goes, and gives the focus to an Order button left", async () => {
    stored(rules());
    tokenStore.set("token");
    machinesStore.set({ machines: ["build-1", "build-2"].map((name) => ({ name, state: "available", slots: 1, free_slots: 1, capabilities: [], jobs: [] })),
                        total: 2, online: 2, free_slots: 2 });
    queueStore.set({ at: performance.now(), snapshot: { now: 0, running: [], recent: [], queued: [job("a")] } });
    render(<TipProvider><JobsBox /></TipProvider>);
    const lane = screen.getByRole("region", { name: "Next free machine" });
    fireEvent.click(within(lane).getByRole("button", { name: "Order" }));
    const box = await within(dialog()).findByRole("textbox", { name: "Branch name or pattern" });
    box.focus();
    fireEvent.change(box, { target: { value: "release/*" } });
    act(() => { queueStore.set({ at: performance.now(), snapshot: { now: 0, running: [], recent: [], queued: [] } }); });
    expect(screen.queryByRole("region", { name: "Next free machine" })).toBeNull();
    const still = within(dialog()).getByRole("textbox", { name: "Branch name or pattern" });
    expect(still).toBe(box);
    expect((still as HTMLInputElement).value).toBe("release/*");
    expect(document.activeElement).toBe(still);
    fireEvent.keyDown(dialog(), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Order" }));
  });
});
