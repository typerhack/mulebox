import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../../lib/api";
import { reply } from "../../lib/heldServer.testing";
import { fateText, policyLines, sizeState, type StorageBody } from "../../lib/storage";
import { GB, cleaned, modern, sweep, withHistory } from "../../lib/storage.testing";
import { goneStore, storageStore } from "../../state/storage";
import { TipProvider } from "../../ui/Tip";
import { StoragePage } from "./StoragePage";

const show = (shown: StorageBody) => {
  storageStore.set({ body: shown, problem: null });
  return render(<TipProvider><StoragePage /></TipProvider>);
};
const line = () => screen.getByRole("region", { name: "Automatic cleanup" });
const history = () => screen.getByRole("region", { name: "Cleanup history" });

afterEach(() => {
  cleanup(); vi.unstubAllGlobals(); tokenStore.set(undefined);
  storageStore.set({ body: null, problem: null }); goneStore.set([]);
});

describe("the automatic cleanup line", () => {
  it("says it is on and what it does, as the node's settings stand", () => {
    show(withHistory());
    expect(line().textContent).toContain(
      "Automatic cleanup: on. Removes a branch folder when its branch is gone from your dev machines, or after 7 days with no job; "
      + "keeps each project's latest folder; keeps 10% of the disk free; cleans Docker's unused build cache and images.");
    expect(line().textContent).toContain("(hourly), removed 3 branch folders, 2.3 GB and freed 1.6 GB in Docker.");
  });

  it("says what is off when it is off", () => {
    const off = modern({ policy: { ...modern().policy, auto_clean: false, docker_clean: false, keep_latest: false, max_size: "60GB" } });
    expect(policyLines(off.policy)).toEqual({ on: false, rules: [
      "Would remove a branch folder when its branch is gone from your dev machines, or after 7 days with no job",
      "a project's latest folder goes like the rest", "keeps 10% of the disk free", "holds at most 60.0 GB", "Docker cleanup is off"] });
    show(withHistory(off));
    expect(line().textContent).toContain("Automatic cleanup: off. mulebox only measures and removes nothing by itself.");
  });

  it("runs the cleanup now on the shown node, Docker too, and shows the node's own answer", async () => {
    const asked: string[] = [];
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if (url === "/api/session") return reply({ action_token: "token" });
      if (url === "/api/storage") return reply(storageStore.get().body);
      asked.push(`${init?.method ?? "GET"} ${url} ${init?.body ?? ""}`.trim());
      if (init?.method === "POST") return reply({ group: "grp-9", nodes: ["build-1"], offline: [], done: false });
      return reply({ group: "grp-9", done: true, action: "sweep", answers: [
        { node: "build-1", output: "removed 2 branch folder(s), 1.2 GB\ndocker: build cache 1.2 GB, images 400.0 MB freed\n", exit_code: 0, answered: true, lost: false }] });
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    show(withHistory());
    fireEvent.click(within(line()).getByRole("button", { name: "Run now" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    vi.useRealTimers();
    await waitFor(() => expect(screen.getByRole("status", { name: "The cleanup's answers" }).textContent).toContain(
      "build-1 removed 2 branch folder(s), 1.2 GB\ndocker: build cache 1.2 GB, images 400.0 MB freed"));
    expect(asked).toEqual(['POST /api/storage/sweep {"node":"build-1","docker":true}', "GET /api/storage/remove/grp-9"]);
  });

  it("has no Settings and no Run now with the controls off", () => {
    show({ ...withHistory(), editable: false });
    expect(within(line()).queryByRole("button", { name: "Run now" })).toBeNull();
    expect(within(line()).queryByRole("button", { name: "Settings" })).toBeNull();
  });

  it("says what mulebox holds against the size at which it warns, and what still blocks the limit", () => {
    show(withHistory(modern({ held: 56.8 * GB })));
    expect(line().textContent).toContain("mulebox holds 56.8 GB on this node; warns agents over 20.0 GB. That is 36.8 GB over the size at which agents are warned.");
    cleanup();
    const over = modern({ held: 62 * GB, over: 2 * GB, policy: { ...modern().policy, max_size: "60GB" } });
    expect(sizeState(over)).toMatchObject({ warned: true, over: 2 * GB, blocks: ["latest", "kept"] });
    show(withHistory(over));
    expect(line().textContent).toContain("Still 2.0 GB over the limit: what is left are latest and kept folders, which the cleanup never removes.");
    cleanup();
    show(withHistory(modern({ held: 13 * GB })));
    expect(line().textContent).toContain("mulebox holds 13.0 GB on this node; warns agents over 20.0 GB.");
    expect(line().textContent).not.toContain("over the size");
  });
});

describe("the cleanup history", () => {
  it("lists each cleanup newest first, with why it ran, what it removed, Docker and the free space", () => {
    show(withHistory());
    const rows = within(history()).getAllByRole("button", { expanded: false });
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("Hourly3 folders removed, 2.3 GBDocker 1.6 GB freedfree 76.1 GB to 80.0 GB");
    expect(rows[1].textContent).toContain("no folder removedDocker 0 B freedfree 80.0 GB to 80.0 GB");
  });

  it("opens a cleanup to each folder with its reason in words, the images removed, and every error", () => {
    const failed = sweep(2, { trigger: "low", docker: null, errors: ["example-app/main-22222222: [Errno 13] Permission denied"] });
    show(withHistory(modern(), [cleaned(), failed]));
    const rows = within(history()).getAllByRole("button", { expanded: false });
    fireEvent.click(rows[0]);
    const text = history().textContent ?? "";
    expect(text).toContain("Ran for 4.2 s with the automatic cleanup on.");
    expect(text).toContain("feature/old-pricing of example-app: its branch is gone from your dev machines800.0 MB");
    expect(text).toContain("fix-typo-77777777 of example-app: no job for 7 days400.0 MB");
    expect(text).toContain("big-88888888 of example-app: over the size limit1.1 GB");
    expect(text).toContain("Docker: build cache 1.2 GB, images 400.0 MB freed. Images removed: node:20-bookworm.");
    expect(rows[1].textContent).toContain("Free space fell under the reserve");
    expect(rows[1].textContent).toContain("Docker not cleaned");
    expect(rows[1].textContent).toContain("1 error");
    fireEvent.click(rows[1]);
    expect(history().textContent).toContain("example-app/main-22222222: [Errno 13] Permission denied");
    expect(history().textContent).toContain("Docker was not cleaned in this run.");
  });

  it("says when a run only measured, shows the last 20 and more on demand", () => {
    const many = [sweep(0.5, { auto: false, would_remove: 3, docker: null }), ...Array.from({ length: 24 }, (_, i) => sweep(1.5 + i))];
    show(withHistory(modern(), many));
    expect(within(history()).getAllByRole("button", { expanded: false })).toHaveLength(20);
    expect(history().textContent).toContain("none removed; 3 would go");
    fireEvent.click(within(history()).getByRole("button", { name: "5 earlier cleanups" }));
    expect(within(history()).getAllByRole("button", { expanded: false })).toHaveLength(25);
  });

  it("says so when nothing is recorded yet", () => {
    show({ ...withHistory(), history: [] });
    expect(history().textContent).toContain("No cleanup recorded yet.");
  });
});

describe("what the page says of Docker and of a folder that goes", () => {
  it("says what mulebox cleans of Docker, what it never touches, and what the last cleanup freed", () => {
    show(withHistory());
    const page = screen.getByRole("region", { name: "Storage" }).textContent ?? "";
    expect(page).toContain("Cleaned with each cleanup: mulebox removes Docker's unused build cache and dangling images, and the images its own jobs pulled and no longer use. It never touches volumes, or images mulebox never used.");
    expect(page).toContain("The last cleanup freed 1.2 GB of build cache and 400.0 MB of images (node:20-bookworm).");
    expect(page).not.toContain("never cleaned by mulebox");
  });

  it("gives a folder's reason, and says it only would go with the automatic cleanup off", () => {
    const policy = modern().policy;
    expect(fateText({ fate: "remove", removed_in: null, why: "gone" }, policy))
      .toBe("Goes at the next cleanup: its branch is gone from your dev machines");
    expect(fateText({ fate: "remove", removed_in: null, why: "unused" }, policy)).toBe("Goes at the next cleanup: no job for 7 days");
    expect(fateText({ fate: "remove", removed_in: null, why: "size" }, { ...policy, auto_clean: false }))
      .toBe("Would go (automatic cleanup is off): over the size limit");
  });
});
