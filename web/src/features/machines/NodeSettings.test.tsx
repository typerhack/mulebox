import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../../lib/api";
import type { NodeSettings } from "../../lib/nodeSettings";
import type { Machine } from "../../lib/types";
import { TipProvider } from "../../ui/Tip";
import { NodeSettingsButton } from "./NodeSettings";

const machine = (more: Partial<Machine> = {}): Machine =>
  ({ name: "build-2", state: "available", slots: 2, free_slots: 2, capabilities: ["docker"], jobs: [], cores: 16,
     version: "1.17.2", priority: "normal", settings_pending: false, ...more });
const view = (more: Partial<NodeSettings> = {}): NodeSettings => ({
  worker: "build-2", online: true, draining: false, version: "1.17.2", running: 0, applies: true,
  current: { slots: 2, priority: "normal" }, pending: null, pending_since: null, error: null,
  suggested: { slots: 4, reason: "16 cores and 32 GB of memory, at about 4 cores and 6 GB a job" },
  choices: { slots: { min: 1, max: 64 }, priority: ["preferred", "normal", "fallback"] }, editable: true, ...more,
});
const reply = (body: unknown, status = 200) => Promise.resolve(new Response(
  typeof body === "string" ? body : JSON.stringify(body), { status }));

// The server: GET answers `first`; a POST is kept and answered with `after`.
function serve(first: NodeSettings, after: NodeSettings | [number, string] = first) {
  const posts: { body: unknown; token: string | null }[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (url === "/api/session") return reply({ action_token: "token" });
    expect(url).toBe("/api/machines/build-2/settings");
    if (init?.method !== "POST") return reply(first);
    posts.push({ body: JSON.parse(String(init.body)), token: new Headers(init.headers).get("X-Mulebox-Token") });
    return Array.isArray(after) ? reply(after[1], after[0]) : reply(after);
  }));
  return posts;
}

async function open(row = machine()) {
  const shown = render(<TipProvider><NodeSettingsButton machine={row} /></TipProvider>);
  fireEvent.click(screen.getByRole("button", { name: "Settings of build-2" }));
  await screen.findByRole("table", { name: "Settings" });
  return shown;
}
const cell = (row: string, label: string) =>
  screen.getByRole("rowheader", { name: new RegExp(`^${row}`) }).parentElement?.querySelector(`[data-label="${label}"]`)?.textContent;

afterEach(() => { cleanup(); vi.unstubAllGlobals(); tokenStore.set(undefined); });

describe("a node's settings window", () => {
  it("shows what is suggested and why, the viewer's value, what runs, and the node's facts", async () => {
    serve(view());
    await open();
    expect(screen.getByRole("dialog", { name: "build-2" })).toBeTruthy();
    expect(cell("Slots", "Suggested")).toContain("4from 16 cores and 32 GB");
    expect(cell("Slots", "Runs with")).toBe("2 now");
    expect(cell("Priority", "Runs with")).toBe("Normal nowas suggested");
    expect(screen.getByRole("radio", { name: "Normal" }).getAttribute("aria-checked")).toBe("true");
    expect(screen.getByText("Offers").parentElement?.textContent).toBe("Offersdocker");
    expect((screen.getByRole("button", { name: "Save changes" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("calls an edit unsaved until Save, and pending only once it was sent", async () => {
    const posts = serve(view(), view({ pending: { slots: 3 }, pending_since: 1 }));
    await open();
    fireEvent.click(screen.getByRole("button", { name: "One slot more" }));
    expect(cell("Slots", "Runs with")).toBe("2 now3 unsavedsent to the node when you save");
    expect(posts).toEqual([]);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save changes" })); });
    expect(posts).toEqual([{ body: { slots: 3 }, token: "token" }]);
    expect(cell("Slots", "Runs with")).toBe("2 now3 pendingDrop itthe node takes it on its next check-in");
    expect((screen.getByRole("textbox", { name: "Slots" }) as HTMLInputElement).value).toBe("3");
    expect((screen.getByRole("button", { name: "Save changes" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("sends both settings in one Save, and a taken suggestion as a fixed value", async () => {
    const posts = serve(view({ current: { slots: 2, priority: "preferred" } }));
    await open();
    fireEvent.click(screen.getByRole("button", { name: "All as suggested" }));
    expect(cell("Slots", "Runs with")).toContain("4 unsaved");
    expect(cell("Priority", "Runs with")).toContain("Normal unsaved");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save changes" })); });
    expect(posts[0].body).toEqual({ slots: 4, priority: "normal" });
  });

  it("moves the priority with the arrow keys and says what each level means", async () => {
    const posts = serve(view());
    await open();
    fireEvent.keyDown(screen.getByRole("radio", { name: "Normal" }), { key: "ArrowRight" });
    const fallback = screen.getByRole("radio", { name: "Fallback" });
    expect(fallback.getAttribute("aria-checked")).toBe("true");
    expect(document.activeElement).toBe(fallback);
    expect(screen.getByText("Takes a job only when better nodes cannot within 30 s.")).toBeTruthy();
    fireEvent.keyDown(fallback, { key: "ArrowRight" });
    expect(screen.getByRole("radio", { name: "Preferred" }).getAttribute("aria-checked")).toBe("true");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save changes" })); });
    expect(posts[0].body).toEqual({ priority: "preferred" });
  });

  it("refuses a typed value out of range and says the range", async () => {
    serve(view());
    await open();
    const field = screen.getByRole("textbox", { name: "Slots" });
    fireEvent.change(field, { target: { value: "65" } });
    expect(screen.getByRole("alert").textContent).toBe("Not taken. From 1 to 64.");
    expect(cell("Slots", "Runs with")).toBe("2 now");
    fireEvent.change(field, { target: { value: "6" } });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(cell("Slots", "Runs with")).toContain("6 unsaved");
  });

  it("says a node on an older mulebox must be upgraded first, with nothing to change", async () => {
    serve(view({ applies: false, current: null, version: "1.14.0" }));
    await open();
    expect(screen.getByText(/runs an older mulebox \(1.14.0\)/).closest("[role=status]")?.textContent).toContain("mulebox setup build-2");
    expect((screen.getByRole("textbox", { name: "Slots" }) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole("radio", { name: "Normal" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
  });

  it("is read only with the dashboard's controls off", async () => {
    serve(view({ editable: false, pending: { slots: 3 } }));
    await open();
    expect(screen.getByText(/this dashboard's controls are off/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "One slot more" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Drop it" })).toBeNull();
    expect(cell("Slots", "Runs with")).toContain("3 pending");
  });

  it("shows why the node could not take a change, and drops it", async () => {
    const posts = serve(view({ pending: { slots: 3 }, error: "node.toml is a symlink" }), view());
    await open();
    expect(screen.getByRole("alert").textContent).toContain("build-2 could not take the change. node.toml is a symlink.");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Drop the change" })); });
    expect(posts[0].body).toEqual({ cancel: true });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("takes one pending setting back by asking for what the node has", async () => {
    const posts = serve(view({ pending: { slots: 3 } }), view());
    await open();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Drop it" })); });
    expect(posts[0].body).toEqual({ slots: 2 });
    expect(cell("Slots", "Runs with")).toBe("2 now");
  });

  it("shows the server's words when a save is refused, and keeps the edit", async () => {
    serve(view(), [409, "build-2 has not reported its settings\n"]);
    await open();
    fireEvent.click(screen.getByRole("button", { name: "One slot more" }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save changes" })); });
    expect(screen.getByRole("alert").textContent).toBe("Not saved. build-2 has not reported its settings");
    expect(cell("Slots", "Runs with")).toContain("3 unsaved");
  });

  it("takes the focus on open, closes on Escape and gives the focus back", async () => {
    serve(view());
    await open();
    const dialog = screen.getByRole("dialog");
    expect(document.activeElement).toBe(dialog);
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(screen.getAllByRole("button", { name: "Close" })[0]);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(dialog.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Settings of build-2" }));
  });

  it("reads again when the row says the node took the change", async () => {
    serve(view({ pending: { slots: 3 } }));
    const shown = await open(machine({ settings_pending: true }));
    expect(screen.getByRole("img", { name: "Settings change pending" })).toBeTruthy();
    serve(view({ current: { slots: 3, priority: "normal" } }));
    shown.rerender(<TipProvider><NodeSettingsButton machine={machine({ slots: 3 })} /></TipProvider>);
    await waitFor(() => expect(cell("Slots", "Runs with")).toBe("3 now"));
    expect(screen.queryByRole("img", { name: "Settings change pending" })).toBeNull();
  });
});
