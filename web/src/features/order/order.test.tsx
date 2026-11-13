import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../../lib/api";
import type { Job, Rules, RulesBody } from "../../lib/types";
import { machinesStore, queueStore } from "../../state/live";
import { orderStore } from "../../state/order";
import { TipProvider } from "../../ui/Tip";
import { JobsBox } from "../jobs/JobsBox";
import { OrderButton } from "./OrderButton";

const rules = (more: Partial<Rules> = {}): Rules =>
  ({ projects: {}, branches: {}, workflows: {}, github: 0, aging_min: 30, shortest_first: false, fair_turns: false, ...more });
const reply = (stored: Rules): RulesBody =>
  ({ rules: stored, defaults: rules(), levels: { min: -3, max: 3, words: { low: -1, normal: 0, high: 1 } },
     projects: ["docs-site", "example-app"] });

// The dashboard's answers: the stored rules to a read, `after` to a change.
function serve(stored: Rules, after: Rules = rules(), status = 200) {
  const fetched = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/session") return new Response(JSON.stringify({ action_token: "tok" }));
    if (init?.method === "POST") return new Response(status === 200 ? JSON.stringify(reply(after)) : "level must be low, normal or high", { status });
    return new Response(JSON.stringify(reply(stored)));
  });
  vi.stubGlobal("fetch", fetched);
  return fetched;
}
const sent = (fetched: ReturnType<typeof serve>) => {
  const call = fetched.mock.calls.find(([, init]) => init?.method === "POST");
  return call ? { url: call[0], body: JSON.parse(String(call[1]?.body)), token: (call[1]?.headers as Record<string, string>)["X-Mulebox-Token"] } : null;
};

async function openPanel() {
  render(<TipProvider><div className="pop-host"><OrderButton /></div></TipProvider>);
  fireEvent.click(screen.getByRole("button", { name: "Order" }));
  const panel = await screen.findByRole("dialog", { name: "Order of the line" });
  await within(panel).findByRole("switch", { name: "Fair turns" });
  return panel;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  tokenStore.set(undefined);
  queueStore.set({ snapshot: null, at: 0 });
  machinesStore.set(null);
  orderStore.set({ body: null, draft: null, busy: null, said: null, problem: null, closed: false });
});

describe("the Order panel", () => {
  it("shows which rule wins: by hand, levels, fair turns, shortest first, arrival", async () => {
    serve(rules());
    tokenStore.set("tok");
    const panel = await openPanel();
    const steps = within(within(panel).getByRole("list", { name: "Rules, strongest first" })).getAllByRole("listitem");
    expect(steps.map((step) => step.querySelector("b")?.textContent)).toEqual(["By hand", "Levels", "Fair turns", "Shortest first", "Arrival"]);
    expect(steps[1].textContent).toContain("project, branch, workflow, GitHub runs, then time waited");
    expect(within(steps[1]).getByRole("switch", { name: "Aging" }).getAttribute("aria-checked")).toBe("true");
    expect(panel.textContent).toContain("Defaults: first come, first served");
    expect(within(panel).getByRole("button", { name: "Reset to defaults" }).hasAttribute("disabled")).toBe(true);
    expect(within(panel).getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(true);
  });

  it("keeps a change unsaved until Save, then posts only what changed", async () => {
    const fetched = serve(rules({ projects: { "docs-site": -1 } }), rules({ projects: { "example-app": 1 }, fair_turns: true }));
    tokenStore.set("tok");
    const panel = await openPanel();
    fireEvent.click(within(panel).getByRole("switch", { name: "Fair turns" }));
    fireEvent.click(within(within(panel).getByRole("radiogroup", { name: /example-app/ })).getByRole("radio", { name: "High" }));
    fireEvent.click(within(within(panel).getByRole("radiogroup", { name: /docs-site/ })).getByRole("radio", { name: "Normal" }));
    expect(within(panel).getByText("Unsaved changes")).toBeTruthy();
    expect(sent(fetched)).toBeNull();
    fireEvent.click(within(panel).getByRole("button", { name: "Save" }));
    await within(panel).findByText("Saved. The line follows these rules now.");
    expect(sent(fetched)).toEqual({ url: "/api/queue/rules", token: "tok",
                                    body: { rules: { projects: { "example-app": 1, "docs-site": 0 }, fair_turns: true } } });
    expect(within(panel).getByRole("switch", { name: "Fair turns" }).getAttribute("aria-checked")).toBe("true");
  });

  it("says the server's words when a change is refused, and keeps the edit", async () => {
    serve(rules(), rules(), 409);
    tokenStore.set("tok");
    const panel = await openPanel();
    fireEvent.click(within(panel).getByRole("switch", { name: "Shortest first" }));
    fireEvent.click(within(panel).getByRole("button", { name: "Save" }));
    expect((await within(panel).findByRole("alert")).textContent).toBe("Not saved. level must be low, normal or high");
    expect(within(panel).getByRole("switch", { name: "Shortest first" }).getAttribute("aria-checked")).toBe("true");
  });

  it("resets to the defaults only after asking twice", async () => {
    const fetched = serve(rules({ shortest_first: true, branches: { main: 1 } }));
    tokenStore.set("tok");
    const panel = await openPanel();
    expect(panel.textContent).toContain("Rules are on");
    fireEvent.click(within(panel).getByRole("button", { name: "Reset to defaults" }));
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Keep rules"));
    expect(sent(fetched)).toBeNull();
    fireEvent.click(within(panel).getByRole("button", { name: "Yes, reset" }));
    await within(panel).findByText("Reset. The line is first come, first served again.");
    expect(sent(fetched)?.body).toEqual({ reset: true });
    expect(within(panel).getByRole("switch", { name: "Shortest first" }).getAttribute("aria-checked")).toBe("false");
  });

  it("is read-only where the dashboard's controls are off", async () => {
    serve(rules({ fair_turns: true, workflows: { "Nightly build": -2 } }));
    tokenStore.set(null);
    const panel = await openPanel();
    expect(within(panel).getAllByRole("switch").every((one) => one.hasAttribute("disabled"))).toBe(true);
    expect(within(panel).getAllByRole("radio").every((one) => one.hasAttribute("disabled"))).toBe(true);
    expect(within(panel).queryByRole("button", { name: "Save" })).toBeNull();
    expect(within(panel).queryByRole("textbox", { name: "Branch name or pattern" })).toBeNull();
    expect(panel.textContent).toContain("controls are off");
    // A level the CLI set outside low, normal and high shows as its number.
    expect(within(within(panel).getByRole("radiogroup", { name: "Nightly build" })).getByRole("radio", { name: "-2" }).getAttribute("aria-checked")).toBe("true");
  });

  it("adds a branch pattern at High, moves a choice with the arrow keys, and steps the aging minutes", async () => {
    const fetched = serve(rules());
    tokenStore.set("tok");
    const panel = await openPanel();
    const box = within(panel).getByRole("textbox", { name: "Branch name or pattern" });
    fireEvent.change(box, { target: { value: "release/*" } });
    fireEvent.keyDown(box, { key: "Enter" });
    const group = within(panel).getByRole("radiogroup", { name: "release/*" });
    const high = within(group).getByRole("radio", { name: "High" });
    expect(high.getAttribute("aria-checked")).toBe("true");
    high.focus();
    fireEvent.keyDown(high, { key: "ArrowRight" });
    fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" });
    expect(document.activeElement?.textContent).toBe("Low");
    expect(within(group).getByRole("radio", { name: "Low" }).getAttribute("aria-checked")).toBe("true");
    fireEvent.click(within(panel).getByRole("button", { name: "More: Minutes in line for one level" }));
    const minutes = within(panel).getByRole("textbox", { name: "Minutes in line for one level" });
    fireEvent.change(minutes, { target: { value: "5000" } });
    fireEvent.blur(minutes);
    expect(within(panel).getByRole("alert").textContent).toBe("From 1 to 1440 minutes.");
    fireEvent.click(within(panel).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(sent(fetched)?.body).toEqual({ rules: { branches: { "release/*": -1 }, aging_min: 35 } }));
  });

  it("closes on Escape and gives the focus back to its button", async () => {
    serve(rules());
    tokenStore.set("tok");
    const panel = await openPanel();
    expect(document.activeElement?.getAttribute("aria-label")).toBe("Close");
    fireEvent.keyDown(panel, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    const opener = screen.getByRole("button", { name: "Order" });
    expect(document.activeElement).toBe(opener);
    expect(opener.getAttribute("aria-expanded")).toBe("false");
  });
});

describe("a waiting row under the order rules", () => {
  const job = (id: string, more: Partial<Job>): Job =>
    ({ job_id: `job-${id}`, project: "example-app", job: "check", state: "queued", kind: "job", section: "queued", ...more });

  it("says why it stands where it does, beside its arrows, and its line carries Order", () => {
    serve(rules());
    tokenStore.set("tok");
    queueStore.set({ at: performance.now(), snapshot: { now: 0, running: [], recent: [], queued: [
      job("a", { position: 1, can_run_on: ["build-1", "build-2"], moved: "front", place_reason: "moved to the front by hand",
                 order: { by_hand: true, moved: { side: "front" } } }),
      job("b", { position: 2, can_run_on: ["build-1", "build-2"], place_reason: "project example-app +1; usually 4m; then by arrival",
                 order: { level: 1, levels: [{ rule: "project", name: "example-app", level: 1 }], usual_s: 240 } }),
      job("c", { position: 3, can_run_on: ["build-1", "build-2"] }),
    ] } });
    machinesStore.set({ machines: ["build-1", "build-2"].map((name) => ({ name, state: "available", slots: 1, free_slots: 1, capabilities: [], jobs: [] })),
                        total: 2, online: 2, free_slots: 2 });
    render(<TipProvider><JobsBox /></TipProvider>);
    const line = screen.getByRole("region", { name: "Next free machine" });
    const rows = within(line).getAllByRole("listitem");
    expect(rows[0].querySelector(".place")?.textContent).toBe("moved to the front by hand");
    expect(rows[1].querySelector(".place")?.textContent).toBe("ahead: project high; usually 4m");
    expect(rows[1].querySelector(".place")?.getAttribute("title")).toContain("then by arrival");
    expect(within(rows[1]).getByRole("group", { name: /Move example-app/ })).toBeTruthy();
    expect(rows[2].querySelector(".place")).toBeNull();
    expect(within(line).getByRole("button", { name: "Order" }).getAttribute("aria-haspopup")).toBe("dialog");
  });
});
