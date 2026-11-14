import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../../lib/api";
import type { NodeSettings } from "../../lib/nodeSettings";
import { body, report } from "../../lib/storage.testing";
import { storageStore } from "../../state/storage";
import { cell, open, reply, view } from "./testing";

const DISK = { keep_free: "10%", unused_days: 7, keep_latest: true, idle_days: 14 };
const MORE = { auto_clean: true, docker_clean: true, max_size: "OFF", warn_size: "50GB" };
const with126 = (more: Partial<NodeSettings> = {}) => withDisk({
  current: { slots: 2, priority: "normal", dev: false, ...DISK, ...MORE }, defaults: { ...DISK, ...MORE }, ...more });
const LIMITS = ["Most mulebox may use", "Clean up on its own", "Clean Docker too", "Warn agents over"];
const withDisk = (more: Partial<NodeSettings> = {}) => view({
  current: { slots: 2, priority: "normal", dev: false, ...DISK }, defaults: DISK,
  choices: { slots: { min: 1, max: 64 }, priority: ["preferred", "normal", "fallback"], keep_free: { max_share: 90 },
             unused_days: { min: 1, max: 365 }, idle_days: { min: 1, max: 365 } }, ...more });

function serve(first: NodeSettings, after: NodeSettings = first) {
  const posts: unknown[] = [];
  let has = first;
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (url === "/api/session") return reply({ action_token: "token" });
    if (init?.method !== "POST") return reply(has);
    posts.push(JSON.parse(String(init.body)));
    has = after;
    return reply(after);
  }));
  return posts;
}
async function openStorage(first: NodeSettings, after?: NodeSettings) {
  const posts = serve(first, after);
  storageStore.set({ body: { ...body(), nodes: [{ node: "build-2", online: true, report: report() }] }, problem: null });
  await open();
  fireEvent.click(screen.getByRole("tab", { name: "Storage" }));
  return posts;
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); tokenStore.set(undefined); storageStore.set({ body: null, problem: null }); });

describe("the Storage tab of a node's settings window", () => {
  it("shows each disk setting as suggested, yours and what runs, with the node's own sizes", async () => {
    await openStorage(withDisk());
    expect(cell("Free space to keep", "Suggested")).toBe("10%49.0 GB of this node's 490.0 GB disk");
    expect(cell("Free space to keep", "Runs with")).toBe("10% nowas suggested");
    expect(cell("Unused branch folders", "Runs with")).toBe("7 days nowas suggested");
    expect(cell("Latest folder", "Runs with")).toBe("Keep nowas suggested");
    expect(cell("Idle projects", "Suggested")).toBe("14 daysthe default for every node");
    expect(screen.getByRole("status").textContent).toBe(
      "With these values the reserve is 49.0 GB and the next cleanup removes nothing. The disk stays 31.0 GB above the reserve.");
  });

  it("says what an edit would do before it is saved, and sends only what changed", async () => {
    const posts = await openStorage(withDisk(), withDisk({ pending: { keep_free: "20%", unused_days: 6 }, pending_since: 1 }));
    fireEvent.change(screen.getByRole("textbox", { name: "Free space to keep" }), { target: { value: "20" } });
    fireEvent.click(within(screen.getByRole("region", { name: "Unused branch folders" })).getByRole("button", { name: "One day fewer" }));
    expect(cell("Free space to keep", "Yours")).toContain("98.0 GB; the disk has 80.0 GB free, less than that");
    expect(cell("Free space to keep", "Runs with")).toBe("10% now20% unsavedsent to the node when you save");
    expect(screen.getByRole("status").textContent).toContain("the reserve is 98.0 GB and the next cleanup removes 1 folder and frees 500.0 MB");
    expect(screen.getByRole("status").textContent).toContain("17.5 GB under the reserve, so mulebox would ask you what else may go");
    expect(posts).toEqual([]);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save changes" })); });
    expect(posts).toEqual([{ keep_free: "20%", unused_days: 6 }]);
    expect(cell("Unused branch folders", "Runs with")).toBe("7 days now6 days pendingDrop itthe node takes it on its next check-in");
  });

  it("turns a share into a size of this node's disk, and back", async () => {
    await openStorage(withDisk());
    fireEvent.click(screen.getByRole("radio", { name: "GB" }));
    expect((screen.getByRole("textbox", { name: "Free space to keep" }) as HTMLInputElement).value).toBe("49");
    expect(cell("Free space to keep", "Runs with")).toBe("10% now49GB unsavedsent to the node when you save");
  });

  it("hides the settings of 1.26 from a node that does not report them", async () => {
    await openStorage(withDisk());
    for (const name of LIMITS) expect(screen.queryByRole("region", { name })).toBeNull();
  });

  it("lays its panels two to a row, in order, so a row's panels line up", async () => {
    await openStorage(with126());
    const panels = [...document.querySelectorAll(".setting-panels > section")].map((panel) => panel.getAttribute("aria-label"));
    expect(panels).toEqual(["Free space to keep", "Most mulebox may use", "Unused branch folders", "Latest folder",
                            ...LIMITS.slice(1, 3), "Idle projects", "Warn agents over"]);
    expect([...document.querySelectorAll(".setting-panels > section")].every((panel) => panel.classList.contains("setting-panel"))).toBe(true);
  });

  it("shows the settings of 1.26 as suggested, yours and what runs", async () => {
    await openStorage(with126());
    expect(cell("Most mulebox may use", "Suggested")).toBe("Offno limit: the free space to keep guards the disk");
    expect(cell("Most mulebox may use", "Yours")).toContain("No limit; mulebox holds 13.0 GB now");
    expect(cell("Most mulebox may use", "Runs with")).toBe("Off nowas suggested");
    expect(cell("Warn agents over", "Suggested")).toBe("50 GBthe default for every node");
    expect(cell("Warn agents over", "Yours")).toContain("mulebox holds 13.0 GB now");
    expect(cell("Clean up on its own", "Runs with")).toBe("On nowas suggested");
    expect(cell("Clean Docker too", "Yours")).toContain("Each cleanup also removes Docker build cache");
    expect(cell("Clean Docker too", "Yours")).toContain("Never volumes, or images mulebox never used.");
  });

  it("sends a size limit, a warning turned off and cleanup on its own off, and says what they would do", async () => {
    const posts = await openStorage(with126());
    const region = (name: string) => within(screen.getByRole("region", { name }));
    fireEvent.click(region("Most mulebox may use").getByRole("radio", { name: "On" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Most mulebox may use" }), { target: { value: "12" } });
    fireEvent.click(region("Warn agents over").getByRole("radio", { name: "Off" }));
    fireEvent.click(region("Clean up on its own").getByRole("radio", { name: "Off" }));
    expect(cell("Most mulebox may use", "Runs with")).toBe("Off now12 GB unsavedsent to the node when you save");
    expect(cell("Warn agents over", "Yours")).toContain("No warning");
    expect(cell("Clean Docker too", "Yours")).toContain("A cleanup you start also removes");
    expect(screen.getByRole("status").textContent).toContain("cleanup on its own is off, so the next cleanup removes nothing");
    expect(screen.getByRole("status").textContent).toContain("mulebox holds 13.0 GB, over its 12.0 GB limit.");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save changes" })); });
    expect(posts).toEqual([{ auto_clean: false, max_size: "12GB", warn_size: "OFF" }]);
  });

  it("says a node before 1.24 has no disk settings, and offers none", async () => {
    await openStorage(view());
    expect(screen.getByText(/runs a mulebox older than 1.24/)).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Free space to keep" }) as HTMLInputElement).disabled).toBe(true);
  });
});
