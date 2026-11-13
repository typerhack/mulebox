// The settings window while things move under it: a save still in flight, answers that come
// back out of order, and a node that changes with the window open.

import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../../lib/api";
import { POLL_MS, type NodeSettings } from "../../lib/nodeSettings";
import { heldServer } from "../../lib/heldServer.testing";
import { cell, machine, open, reply, row, view } from "./testing";

// Until `hold()`, every request is answered at once with `first`.
const server = (first: NodeSettings) => heldServer(() => first);

const disabled = (role: string, name: string) => (screen.getByRole(role, { name }) as HTMLButtonElement).disabled;
const save = () => act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save changes" })); });
const PENDING = view({ pending: { slots: 3 }, pending_since: 1 });
const TAKEN = view({ current: { slots: 3, priority: "normal" } });

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); tokenStore.set(undefined); });

describe("a node's settings window while things move", () => {
  it("takes no edit while a save is in flight, so none is lost", async () => {
    const api = server(view());
    await open();
    api.hold();
    fireEvent.click(screen.getByRole("button", { name: "One slot more" }));
    await save();
    await waitFor(() => expect(api.posts()).toHaveLength(1));
    expect(disabled("radio", "Fallback")).toBe(true);
    expect(disabled("button", "One slot more")).toBe(true);
    expect(disabled("textbox", "Slots")).toBe(true);
    expect(screen.queryByRole("button", { name: /Use the suggested/ })).toBeNull();
    await api.posts()[0].answer(PENDING);
    expect(disabled("radio", "Fallback")).toBe(false);
    expect(disabled("button", "One slot more")).toBe(false);
  });

  it("drops a read that was asked before the save and answered after it", async () => {
    const api = server(view());
    const shown = await open();
    api.hold();
    shown.rerender(row(machine({ priority: "preferred" })));
    await waitFor(() => expect(api.gets()).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "One slot more" }));
    await save();
    await waitFor(() => expect(api.posts()).toHaveLength(1));
    await api.posts()[0].answer(PENDING);
    await api.gets()[0].answer(view());        // the node as it was before the save
    expect(cell("Slots", "Runs with")).toContain("3 pending");
    expect((screen.getByRole("textbox", { name: "Slots" }) as HTMLInputElement).value).toBe("3");
  });

  it("reads again once a save is done, so a late answer to it does not bring Pending back", async () => {
    const api = server(view());
    const shown = await open();
    api.hold();
    fireEvent.click(screen.getByRole("button", { name: "One slot more" }));
    await save();
    await waitFor(() => expect(api.posts()).toHaveLength(1));
    shown.rerender(row(machine({ slots: 3, free_slots: 3 })));   // the node took it meanwhile
    for (const read of api.gets()) await read.answer(TAKEN);
    const before = api.gets().length;
    await api.posts()[0].answer(PENDING);                         // the save's own answer, late
    await waitFor(() => expect(api.gets().length).toBeGreaterThan(before));
    for (const read of api.gets().slice(before)) await read.answer(TAKEN);
    expect(cell("Slots", "Runs with")).toBe("3 now");
  });

  it.each([
    ["goes offline", { state: "offline" }],
    ["is paused", { state: "draining" }],
    ["starts a job", { free_slots: 1, jobs: [{ id: "j1" } as never] }],
    ["is upgraded", { version: "1.18.0" }],
  ])("reads again when the node %s", async (_what, change) => {
    const api = server(view());
    const shown = await open();
    api.hold();
    shown.rerender(row(machine(change)));
    await waitFor(() => expect(api.gets()).toHaveLength(1));
  });

  it("asks again every few seconds, shows a write error that came meanwhile and keeps the edit", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = server(PENDING);
    await open(machine({ settings_pending: true }));
    api.hold();
    fireEvent.click(screen.getByRole("radio", { name: "Fallback" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS); });
    expect(api.gets()).toHaveLength(1);
    await api.gets()[0].answer({ ...PENDING, error: "node.toml is a symlink" });
    expect(screen.getByRole("alert").textContent).toContain("build-2 could not take the change. node.toml is a symlink.");
    expect(cell("Priority", "Runs with")).toContain("Fallback unsaved");
    // An answer that is slow does not get a second request on top of it.
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS); });
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS); });
    expect(api.gets()).toHaveLength(2);
  });

  it("shows a read that failed and takes the words away once one works", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = server(view());
    await open();
    vi.stubGlobal("fetch", vi.fn(() => reply("the coordinator is not answering\n", 502)));
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS); });
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Not read."));
    vi.stubGlobal("fetch", vi.fn(() => reply(view())));
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS); });
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(api.asked.length).toBeGreaterThan(0);
  });
});
