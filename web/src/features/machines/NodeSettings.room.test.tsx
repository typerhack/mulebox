import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../../lib/api";
import { memoryGb, type NodeSettings } from "../../lib/nodeSettings";
import { cell, open, reply, view } from "./testing";

const ROOM = { choices: { slots: { min: 1, max: 64 }, keep_cores: { min: 0, max: 16 }, keep_memory: { max_gb: 34 } } };
const roomView = (current: object, more: Partial<NodeSettings> = {}) =>
  view({ current: { slots: 2, priority: "normal", keep_cores: 0, keep_memory: "0GB", ...current }, ...ROOM, ...more });

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

afterEach(() => { cleanup(); vi.unstubAllGlobals(); tokenStore.set(undefined); });

describe("room kept for the node's owner", () => {
  it("is not shown for a node older than 1.38", async () => {
    serve(view());
    await open();
    expect(screen.queryByRole("region", { name: "Room for you" })).toBeNull();
  });

  it("shows nothing kept as suggested, and what jobs with a size share", async () => {
    serve(roomView({}));
    await open();
    expect(screen.getByRole("region", { name: "Room for you" })).toBeTruthy();
    expect(cell("Cores kept", "Yours")).toContain("Jobs with a size share all 16 cores");
    expect(cell("Cores kept", "Runs with")).toBe("0 cores nowas suggested");
    expect(cell("Memory kept", "Yours")).toContain("Jobs with a size share all 34 GB");
  });

  it("sends whole cores and whole GB, and shows a saved change as pending", async () => {
    const posts = serve(roomView({}), roomView({}, { pending: { keep_cores: 2, keep_memory: "4GB" }, pending_since: 1 }));
    await open();
    for (let i = 0; i < 2; i++) fireEvent.click(screen.getByRole("button", { name: "One core more" }));
    for (let i = 0; i < 4; i++) fireEvent.click(screen.getByRole("button", { name: "One GB more" }));
    expect(cell("Cores kept", "Yours")).toContain("Jobs with a size share 14 of 16 cores");
    expect(cell("Cores kept", "Runs with")).toContain("2 cores unsaved");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(posts).toEqual([{ keep_cores: 2, keep_memory: "4GB" }]));
    await waitFor(() => expect(cell("Memory kept", "Runs with")).toContain("4 GB pending"));
  });

  it("reads memory as node.toml writes it", () => {
    expect([memoryGb("4GB"), memoryGb("0GB"), memoryGb("512MB"), memoryGb("1TB"), memoryGb("lots")])
      .toEqual([4, 0, 1, 1000, null]);
  });
});
