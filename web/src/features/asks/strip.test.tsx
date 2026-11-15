import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { NOW } from "../../lib/storage.testing";
import { asksBody, change, lay, page, request, reset, serve } from "./testing";
import { ARM_MS } from "./UndoButton";

afterEach(() => { cleanup(); reset(); });
const strip = () => screen.getByRole("status", { name: "Requests from agents" });
const calm = () => screen.getByRole("status", { name: "Answered and allowed" });
// Undo takes no click for its first moment (UndoButton): it starts disabled, then works.
async function clickUndo() {
  const button = within(calm()).getByRole("button", { name: "Undo" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  await act(async () => { await new Promise((done) => setTimeout(done, ARM_MS + 50)); });
  await act(async () => { fireEvent.click(within(calm()).getByRole("button", { name: "Undo" })); });
}

describe("requests in the strip", () => {
  it("is one amber line per request, naming the node, the value, what mulebox holds and who asked", () => {
    lay([request()]);
    page();
    expect(within(strip()).getByRole("listitem").textContent).toContain(
      "An agent asks for 30.0 GB of space on build-1, up from 20.0 GB. mulebox holds 16.4 GB there. Asked for example-app from alice-laptop, 12 min ago.");
    for (const name of ["Approve 30.0 GB", "Review", "Decline"]) expect(within(strip()).getByRole("button", { name })).toBeTruthy();
    expect(screen.getByRole("button", { name: "1 to answer: show" }).textContent).toBe("1");
  });

  it("gives two requests for one node one answer, at the larger value", () => {
    lay([request(), request({ id: "ask-2", value: "24GB", project: "example-shop", asked_at: NOW - 3 * 60 })]);
    page();
    const lines = within(strip()).getAllByRole("listitem");
    expect(lines).toHaveLength(1);
    expect(lines[0].textContent).toContain("2 agents ask for up to 30.0 GB of space on build-1, up from 20.0 GB.");
    expect(lines[0].textContent).toContain("Asked for example-app and example-shop from alice-laptop, 12 min ago and 3 min ago.");
  });

  it("folds from three requests into one line with the count per node and the oldest age", () => {
    lay([request(), request({ id: "ask-2", value: "24GB", project: "example-shop", asked_at: NOW - 3 * 60 }),
         request({ id: "ask-3", node: "build-mac", value: "40GB", project: "example-ios", client: "bob-desktop", asked_at: NOW - 3600 })]);
    page();
    const lines = within(strip()).getAllByRole("listitem");
    expect(lines).toHaveLength(1);
    expect(lines[0].textContent).toContain("3 requests for more space wait for your answer. "
      + "1 for build-mac (example-ios), 2 for build-1 (example-app, example-shop). The oldest was asked 60 min ago.");
    expect(within(strip()).getByRole("button", { name: "Review all 3" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "3 to answer: show" })).toBeTruthy();
    fireEvent.click(within(strip()).getByRole("button", { name: "Review all 3" }));
    const dialog = screen.getByRole("dialog", { name: "Requests for more space" });
    expect(dialog.textContent).toContain("3 waiting on 2 nodes");
    expect(within(dialog).getByText("2 requests for its space, one answer")).toBeTruthy();
  });

  it("says what was decided after Approve, with Undo, and leaves the mark", async () => {
    const posts = serve();
    lay([request()]);
    page();
    await act(async () => { fireEvent.click(within(strip()).getByRole("button", { name: "Approve 30.0 GB" })); });
    expect(posts).toEqual([{ action: "answer", approve: true, node: "build-1" }]);
    expect(screen.queryByRole("status", { name: "Requests from agents" })).toBeNull();
    expect(screen.queryByRole("button", { name: /to answer/ })).toBeNull();
    expect(calm().textContent).toContain("Approved: 30.0 GB. build-1 takes it with its next check-in; the agent reads the answer in its next command.");
    await clickUndo();
    expect(posts[1]).toEqual({ action: "undo", change: "chg-9" });
  });
});

describe("a change applied without asking", () => {
  it("is a grey line with Undo and Got it, not counted by the mark, and Got it hides it in this browser", async () => {
    const posts = serve(asksBody({ change_id: "chg-2" }));
    lay([], [change()]);
    page();
    expect(calm().textContent).toContain("build-1 now has 30.0 GB of space for mulebox, up from 20.0 GB. "
      + "Applied without asking, as you allowed. Asked for example-app from alice-laptop, 2 min ago.");
    expect(screen.queryByRole("button", { name: /show$/ })).toBeNull();
    await clickUndo();
    expect(posts).toEqual([{ action: "undo", change: "chg-1" }]);
    expect(calm().textContent).toContain("Undone: build-1 is back to 20.0 GB.");
    fireEvent.click(within(calm()).getByRole("button", { name: "Got it" }));
    expect(screen.queryByRole("status", { name: "Answered and allowed" })).toBeNull();
    expect(JSON.parse(localStorage.getItem("mulebox.asks.got-it") ?? "[]")).toEqual(["chg-1"]);
  });
});
