import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { NOW } from "../../lib/storage.testing";
import { TipProvider } from "../../ui/Tip";
import { AgentsButton } from "./Agents";
import { SettingsHistory } from "./SettingsHistory";
import { asksBody, change, lay, page, request, reset, serve } from "./testing";

afterEach(() => { cleanup(); reset(); });
const review = () => {
  fireEvent.click(within(screen.getByRole("status", { name: "Requests from agents" })).getByRole("button", { name: "Review" }));
  return screen.getByRole("dialog", { name: "Request for more space" });
};

describe("the review window", () => {
  it("shows the question, the agent's reason, who asked and the space bar with what the value does", () => {
    lay([request()]);
    page();
    const dialog = review();
    expect(dialog.textContent).toContain("build-1, asked 12 min ago");
    expect(within(dialog).getByRole("heading", { level: 3 }).textContent).toBe("Raise the space for mulebox on build-1 from 20.0 GB to 30.0 GB?");
    expect(dialog.textContent).toContain("Written by the agent that asked");
    expect(dialog.textContent).toContain("job-01JCX4M7Q2");
    expect(within(dialog).getByRole("img", { name: /^mulebox holds 16.4 GB of a limit of 20.0 GB; the limit would be 30.0 GB$/ })).toBeTruthy();
    // 30 GB filled leaves 61 - 13.6 = 47.4 GB, under the 49 GB floor; 28 GB is the most that stays clear of it.
    expect(dialog.textContent).toContain("At 30.0 GB mulebox is at 55% of its limit, and agents are told again from 24.0 GB. "
      + "Filled to the limit, the disk is left with 47.4 GB free, 1.6 GB under its floor");
    expect(dialog.textContent).toContain("28 GB is the most that stays clear of it.");
  });

  it("approves at another value: the stepper sets the number Approve sends, and the strip says so", async () => {
    const posts = serve();
    lay([request()]);
    page();
    const dialog = review();
    fireEvent.click(within(dialog).getByRole("button", { name: "Another value" }));
    for (let i = 0; i < 5; i += 1) fireEvent.click(within(dialog).getByRole("button", { name: "One GB fewer" }));
    expect(dialog.textContent).toContain("asked: 30.0 GB");
    expect(dialog.textContent).toContain("Even filled to the limit, the disk keeps 52.4 GB free, above its floor of 49.0 GB.");
    await act(async () => { fireEvent.click(within(dialog).getByRole("button", { name: "Approve 25.0 GB" })); });
    expect(posts).toEqual([{ action: "answer", approve: true, node: "build-1", value: "25GB" }]);
    expect(screen.getByRole("status", { name: "Answered and allowed" }).textContent).toContain(
      "Approved at 25.0 GB, not the 30.0 GB asked. build-1 takes it with its next check-in; the agent reads the answer in its next command.");
    expect(within(dialog).getByRole("status").textContent).toContain("Approved at 25.0 GB");
  });

  it("declines with a short note for the agent", async () => {
    const posts = serve();
    lay([request()]);
    page();
    const dialog = review();
    fireEvent.click(within(dialog).getByRole("button", { name: "Decline" }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: "A note for the agent, optional" }), { target: { value: "Clean first" } });
    await act(async () => { fireEvent.click(within(dialog).getByRole("button", { name: "Decline with the note" })); });
    expect(posts).toEqual([{ action: "answer", approve: false, node: "build-1", note: "Clean first" }]);
    expect(within(dialog).getByRole("status").textContent).toContain("Declined: the limit stays 20.0 GB.");
  });
});

describe("the Agents window", () => {
  it("shows the option and its sentence, saves a change, and is read only with the controls off", async () => {
    const posts = serve(asksBody({ agents: "allow" }));
    render(<TipProvider><AgentsButton /></TipProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Agents: what agents may do" }));
    const dialog = screen.getByRole("dialog", { name: "Agents" });
    expect(dialog.textContent).toContain("What agents may do on every node. Saved on the coordinator.");
    await waitFor(() => expect(within(dialog).getByRole("radio", { name: "Ask me first" }).getAttribute("aria-checked")).toBe("true"));
    expect(dialog.textContent).toContain("Nothing changes until you answer.");
    fireEvent.click(within(dialog).getByRole("radio", { name: "Allow, and record it" }));
    expect(dialog.textContent).toContain("Unsaved");
    expect(dialog.textContent).toContain("The change is made at once and recorded with who asked and why.");
    await act(async () => { fireEvent.click(within(dialog).getByRole("button", { name: "Save" })); });
    expect(posts).toEqual([{ action: "agents", option: "allow" }]);
    expect(dialog.textContent).toContain("Saved.");
    cleanup();
    reset();
    serve(asksBody(), asksBody({ editable: false }));
    render(<TipProvider><AgentsButton /></TipProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Agents: what agents may do" }));
    await waitFor(() => expect(screen.getByRole("dialog").textContent).toContain("Read only"));
    expect((screen.getByRole("radio", { name: "Allow, and record it" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("the settings history", () => {
  it("words each change as the mockups do, with Undo on the undoable one", async () => {
    const asked = (value: string, note: string | null = null) => ({ value, note, asks: change().asked!.asks.map((a) => ({ ...a, value })) });
    serve(asksBody(), asksBody({ changes: [
      change({ id: "c1", by: "the dashboard, from 192.168.1.50", how: "approved_other", new: "25GB", in_force_at: NOW - 92, at: NOW - 100 }),
      change({ id: "c2", node: "build-mac", new: "20GB", how: "declined", asked: asked("40GB", "Clean the old schemes first."),
               by: "the dashboard, from 192.168.1.50", in_force_at: null, undoable: false }),
      change({ id: "c3", how: "allowed", undoable: false }),
      change({ id: "c4", how: "approved", old: "15GB", new: "20GB", asked: asked("20GB"), by: "`mulebox storage approve` on alice-laptop", undoable: false }),
      change({ id: "c5", how: "owner", old: "20GB", new: "15GB", asked: null, by: "mulebox machine config", undoable: false }),
      change({ id: "c6", node: null, setting: "agents", how: "agents", old: "ask", new: "allow", asked: null, by: "the dashboard, from 192.168.1.50", undoable: false }),
    ] }));
    render(<TipProvider><SettingsHistory now={NOW} /></TipProvider>);
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(6));
    const rows = screen.getAllByRole("listitem").map((row) => row.textContent);
    expect(rows[0]).toContain("build-1, space for mulebox: 20.0 GB to 25.0 GB. Asked 30.0 GB; approved at another value.");
    expect(rows[0]).toContain("Asked by an agent working on example-app from alice-laptop, job-01JCX4M7Q2: The release branch builds three images.");
    expect(rows[0]).toContain("Confirmed on the dashboard, from 192.168.1.50. In force 8 s later.");
    expect(rows[1]).toContain("build-mac, space for mulebox: stays 20.0 GB. Asked 40.0 GB; declined.");
    expect(rows[1]).toContain("Declined on the dashboard, from 192.168.1.50, with the note Clean the old schemes first.");
    expect(rows[2]).toContain("Asked 30.0 GB; applied without asking, as you allowed.");
    expect(rows[2]).toContain("Nobody confirmed. In force 6 s later.");
    expect(rows[3]).toContain("15.0 GB to 20.0 GB. Asked 20.0 GB; approved as asked.");
    expect(rows[3]).toContain("Confirmed with mulebox storage approve on alice-laptop.");
    expect(rows[4]).toContain("build-1, space for mulebox: 20.0 GB to 15.0 GB. Nobody asked.Changed with mulebox machine config.");
    expect(rows[5]).toContain("Agents, when an agent asks for a setting change: Ask me first to Allow, and record it. Nobody asked.");
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Undo: back to 20.0 GB"]);
  });
});
