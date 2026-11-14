import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../../lib/api";
import { reply } from "../../lib/heldServer.testing";
import type { StorageBody } from "../../lib/storage";
import { body, low, report } from "../../lib/storage.testing";
import { goneStore, storageStore } from "../../state/storage";
import { TipProvider } from "../../ui/Tip";
import { OutOfStepStrip } from "../header/OutOfStep";
import { StoragePage } from "./StoragePage";

// The server: every POST is kept; a removal is done at once; a keep answers the new marks.
function serve(keeps: StorageBody["keeps"] = []) {
  const posts: { url: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (url === "/api/session") return reply({ action_token: "token" });
    if (url === "/api/storage") return reply(storageStore.get().body);
    if (init?.method !== "POST") return reply({ group: "grp-1", done: true, answers: [] });
    posts.push({ url, body: JSON.parse(String(init.body)) });
    return reply(url.endsWith("/keep") ? { keeps } : { group: "grp-1", nodes: ["build-1"], done: true });
  }));
  return posts;
}
const show = (shown: StorageBody) => {
  storageStore.set({ body: shown, problem: null });
  return render(<TipProvider><OutOfStepStrip /><StoragePage /></TipProvider>);
};
const rowOf = (text: string) => screen.getAllByText(text)[0].closest(".keep-row") as HTMLElement;
const openProject = (name: string) => fireEvent.click(within(rowOf(name)).getByRole("button", { expanded: false }));

afterEach(() => {
  cleanup(); vi.unstubAllGlobals(); tokenStore.set(undefined);
  storageStore.set({ body: null, problem: null }); goneStore.set([]);
});

describe("the Storage page", () => {
  it("shows the disk, the last sweep, each project, and Docker as not mulebox's to clean", () => {
    show(body());
    const page = screen.getByRole("region", { name: "Storage" });
    expect(page.textContent).toContain("build-1 holds 13.0 GB, measured");
    expect(page.textContent).toContain("80.0 GB free of 490.0 GB");
    expect(page.textContent).toContain("31.0 GB above the reserve of 49.0 GB (10%)");
    expect(page.textContent).toContain("removed 13 branch folders and freed 4.3 GB.");
    expect(rowOf("example-app").textContent).toContain("2.7 GB");  // its folders and repository; caches have their own row
    expect(rowOf("example-app").textContent).toContain("1 folder goes within a day");
    expect(rowOf("example-docs").textContent).toContain("No job for 16 days. Clean it?");
    expect(page.textContent).toContain("all of Docker on this node, not only mulebox's");
    expect(page.textContent).toContain("Shown, never cleaned by mulebox");
    expect(rowOf("Images").querySelector("button[aria-label^=Clean]")).toBeNull();
  });

  it("opens a project to its branch folders, by branch name, with what happens to each", () => {
    show(body());
    openProject("example-app");
    expect(rowOf("fix/login").textContent).toContain("500.0 MB");
    expect(rowOf("fix/login").textContent).toContain("Removed within a day");
    expect(rowOf("feature/checkout").textContent).toContain("Kept: the project's latest");
    expect(within(rowOf("main")).getByRole("button", { name: "Stop keeping main" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(rowOf("fix/login")).getByRole("button", { name: "Copy the path of fix/login" })).toBeTruthy();
  });

  it("keeps a branch on a press and shows the mark the server answers", async () => {
    const posts = serve([{ project: "example-app", branch: "main" }, { project: "example-app", branch: "fix/login" }]);
    show(body());
    openProject("example-app");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Keep fix/login" })); });
    expect(posts).toEqual([{ url: "/api/storage/keep", body: { project: "example-app", branch: "fix/login", keep: true } }]);
    await waitFor(() => expect(screen.getByRole("button", { name: "Stop keeping fix/login" })).toBeTruthy());
  });

  it("cleans a project's folders that would go anyway, one request each, and leaves the latest and kept", async () => {
    const posts = serve();
    show(body());
    fireEvent.click(screen.getByRole("button", { name: "Clean example-app" }));
    const ask = screen.getByRole("group", { name: "Clean example-app" });
    expect(ask.textContent).toContain("removes 2 branch folders on every node that has them and frees 900.0 MB here.");
    expect(ask.textContent).toContain("Stays: feature/checkout (the latest)");
    expect(ask.textContent).toContain("Stays: main (kept by you)");
    expect(posts).toEqual([]);
    await act(async () => { fireEvent.click(within(ask).getByRole("button", { name: "Remove 2 folders" })); });
    expect(posts).toEqual([{ url: "/api/storage/remove", body: { project: "example-app", branch: "fix/login" } },
                           { url: "/api/storage/remove", body: { project: "example-app", branch: "chore/deps" } }]);
    openProject("example-app");  // the project is still there, with what stayed
    expect(screen.queryByText("fix/login")).toBeNull();
    expect(rowOf("feature/checkout")).toBeTruthy();
    expect(screen.getAllByRole("status").some((line) => line.textContent?.includes("Removed."))).toBe(true);
  });

  it("leaves a folder whose branch it does not know, and says so", async () => {
    const posts = serve();
    const known = body();
    delete known.branches["example-app"]["chore-deps-44444444"];
    show(known);
    fireEvent.click(screen.getByRole("button", { name: "Clean example-app" }));
    const ask = screen.getByRole("group", { name: "Clean example-app" });
    expect(ask.textContent).toContain("removes 1 branch folder on every node");
    expect(ask.textContent).toContain("Stays: 1 folder of a branch mulebox does not know, which cannot be removed from here");
    await act(async () => { fireEvent.click(within(ask).getByRole("button", { name: "Remove 1 folder" })); });
    expect(posts).toEqual([{ url: "/api/storage/remove", body: { project: "example-app", branch: "fix/login" } }]);
  });

  it("removes a whole project only from an idle project's suggestion, and says what goes with it", async () => {
    const posts = serve();
    show(body());
    fireEvent.click(within(rowOf("example-docs")).getByRole("button", { name: "Clean it" }));
    const ask = screen.getByRole("group", { name: "Clean example-docs" });
    expect(ask.textContent).toContain("Clean all of example-docs: removes its 1 branch folder, the latest and any kept one too, and its repository, on every node.");
    expect(ask.textContent).toContain("That frees 800.0 MB here.");
    expect(posts).toEqual([]);
    await act(async () => { fireEvent.click(within(ask).getByRole("button", { name: "Remove the whole project" })); });
    expect(posts).toEqual([{ url: "/api/storage/remove", body: { project: "example-docs" } }]);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Clean example-docs" })).toBeNull());
  });

  it("has nothing to clean on the row of a project whose only folder is its latest", () => {
    serve();
    show(body());
    fireEvent.click(screen.getByRole("button", { name: "Clean example-docs" }));
    const ask = screen.getByRole("group", { name: "Clean example-docs" });
    expect(ask.textContent).toContain("Nothing to clean in example-docs.");
    expect((within(ask).getByRole("button", { name: "Remove 0 folders" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("only shows, with the controls off", () => {
    show(body({ editable: false }));
    expect(screen.getByText("Read only: this dashboard's controls are off.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Clean example-app" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Keep example-app" })).toBeNull();
    expect(screen.getByRole("button", { name: "Copy the path of example-app" })).toBeTruthy();
  });

  it("says why a node has no report", () => {
    show(body({}, null));
    expect(screen.getByRole("region", { name: "Storage" }).textContent).toContain("build-1 has sent no report yet");
  });

  it("lists what goes next on its own, soonest first", () => {
    show(body());
    fireEvent.click(screen.getByRole("button", { name: "Show what goes next" }));
    const names = [...screen.getByRole("dialog", { name: "build-1" }).querySelectorAll("code")].map((code) => code.textContent);
    expect(names).toEqual(["fix/login", "chore/deps"]);
  });
});

describe("a node under its reserve", () => {
  it("says so in the strip and lets the owner decide what goes", async () => {
    const posts = serve();
    show(body({}, low()));
    const strip = screen.getByRole("status", { name: "Low disk space" });
    expect(strip.textContent).toContain("build-1 has 44.0 GB free, 5.0 GB under its reserve of 49.0 GB.");
    fireEvent.click(within(strip).getByRole("button", { name: "Review what goes" }));
    const review = screen.getByRole("dialog", { name: "build-1" });
    const ticks = within(review).getAllByRole("checkbox") as HTMLInputElement[];
    // The latest is offered but not ticked, what goes by itself is ticked until it covers the gap, a kept one cannot go.
    expect(ticks.map((tick) => [tick.checked, tick.disabled])).toEqual([[false, false], [true, false], [true, false], [false, true]]);
    expect(review.textContent).toContain("2 of 4 ticked: frees 5.5 GB here.");
    fireEvent.click(ticks[2]);
    expect(review.textContent).toContain("1 of 4 ticked: frees 3.0 GB here.");
    expect(posts).toEqual([]);
    await act(async () => { fireEvent.click(within(review).getByRole("button", { name: "Remove 3.0 GB" })); });
    expect(posts).toEqual([{ url: "/api/storage/remove", body: { project: "example-app", branch: "fix/login" } }]);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("says nothing while every node is above its reserve", () => {
    show(body({}, report()));
    expect(screen.queryByRole("status", { name: "Low disk space" })).toBeNull();
  });
});
