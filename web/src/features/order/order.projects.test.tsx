// The Order panel's project levels: every project stays, the ones in use first.

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../../lib/api";
import { day } from "../../lib/format";
import type { Job, ProjectActivity, Rules, RulesBody } from "../../lib/types";
import { queueStore } from "../../state/live";
import { EMPTY_ORDER, orderStore } from "../../state/order";
import { OrderHarness } from "./testing";

const NOW = Date.UTC(2026, 10, 13, 12) / 1000, HOUR = 3600, DAY = 24 * HOUR;
const rules = (more: Partial<Rules> = {}): Rules =>
  ({ projects: {}, branches: {}, workflows: {}, github: 0, aging_min: 30, shortest_first: false, fair_turns: false, ...more });
const used = (name: string, runs_7d: number, age: number): ProjectActivity => ({ name, last_run: NOW - age, runs_7d });
const drills = (count: number) => Array.from({ length: count }, (_, i) => used(`drill-${i + 1}`, 0, (30 + i) * DAY));

function serve(stored: Rules, activity: ProjectActivity[] | undefined) {
  const body = (now: Rules): RulesBody =>
    ({ rules: now, defaults: rules(), levels: { min: -3, max: 3, words: { low: -1, normal: 0, high: 1 } },
       projects: (activity ?? [used("docs-site", 0, 0), used("example-app", 0, 0)]).map(({ name }) => name).sort(),
       ...(activity ? { project_activity: activity, now: NOW } : {}) });
  const fetched = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/session") return new Response(JSON.stringify({ action_token: "tok" }));
    if (init?.method === "POST") return new Response(JSON.stringify(body({ ...stored, ...JSON.parse(String(init.body)).rules })));
    return new Response(JSON.stringify(body(stored)));
  });
  vi.stubGlobal("fetch", fetched);
  return fetched;
}

async function openPanel() {
  tokenStore.set("tok");
  render(<OrderHarness />);
  fireEvent.click(screen.getByRole("button", { name: "Order" }));
  const panel = await screen.findByRole("dialog", { name: "Order of the line" });
  await within(panel).findByRole("switch", { name: "Fair turns" });
  return panel;
}
const rowsOf = (panel: HTMLElement, name: string) =>
  within(within(panel).getByRole("list", { name })).getAllByRole("listitem").map((row) => row.querySelector("span")?.textContent);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  tokenStore.set(undefined);
  queueStore.set({ snapshot: null, at: 0 });
  orderStore.set(EMPTY_ORDER);
});

describe("the Order panel's project levels", () => {
  it("lists the projects of the last 7 days first, then every other by its latest run", async () => {
    serve(rules({ projects: { "never-ran": 1 } }), [
      used("old-drill", 0, 41 * DAY), used("example-app", 12, 2 * HOUR), used("set-aside", 0, 400 * DAY),
      used("example-org__example-api", 1, 30), used("docs-site", 0, 9 * DAY)]);
    const panel = await openPanel();
    expect(rowsOf(panel, "Active in the last 7 days")).toEqual(["example-app12 runs, last 2 h ago", "example-org/example-api1 run, last 30 s ago"]);
    expect(rowsOf(panel, "Other projects")).toEqual([
      `docs-sitelast run ${day(NOW - 9 * DAY, NOW)}`, `old-drilllast run ${day(NOW - 41 * DAY, NOW)}`,
      `set-asidelast run ${day(NOW - 400 * DAY, NOW)}`, "never-ranno run yet"]);
    expect(day(NOW - 400 * DAY, NOW)).toContain("2025");
    expect(within(panel).queryByRole("button", { name: /^Show/ })).toBeNull();  // four others: all shown
    // The level of a project that never ran shows as set; one long unused can still be given one.
    expect(within(panel).getByRole("radio", { name: "High", checked: true })).toBeTruthy();
    expect(within(panel).getByRole("radiogroup", { name: /^never-ran/ })).toBeTruthy();
  });

  it("gives a level to a project last used long ago", async () => {
    const fetched = serve(rules(), [used("example-app", 3, HOUR), used("old-drill", 0, 41 * DAY)]);
    const panel = await openPanel();
    fireEvent.click(within(within(panel).getByRole("radiogroup", { name: /^old-drill/ })).getByRole("radio", { name: "Low" }));
    fireEvent.click(within(panel).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetched.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const post = fetched.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ rules: { projects: { "old-drill": -1 } } });
    await waitFor(() => expect(within(panel).getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(true));
    expect(rowsOf(panel, "Other projects")).toHaveLength(1);  // it stays where its use puts it
  });

  it("shows a long rest by its latest three, and opens the others in place from the keyboard's button", async () => {
    serve(rules(), [used("example-app", 3, HOUR), ...drills(18)]);
    const panel = await openPanel();
    expect(rowsOf(panel, "Other projects")).toHaveLength(3);
    const more = within(panel).getByRole("button", { name: "Show 15 more" });
    expect(more.getAttribute("aria-expanded")).toBe("false");
    expect(more.getAttribute("aria-controls")).toBe(within(panel).getByRole("list", { name: "Other projects" }).id);
    more.focus();
    fireEvent.click(more);
    expect(rowsOf(panel, "Other projects")).toHaveLength(18);
    const fewer = within(panel).getByRole("button", { name: "Show the latest 3" });
    expect(fewer.getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement).toBe(fewer);
    fireEvent.click(within(within(panel).getByRole("radiogroup", { name: /^drill-18/ })).getByRole("radio", { name: "High" }));
    fireEvent.click(fewer);
    expect(rowsOf(panel, "Other projects")).toHaveLength(3);  // the viewer's choice holds
  });

  it("starts with the rest open when a level is set past its first three", async () => {
    serve(rules({ projects: { "drill-12": -1 } }), [used("example-app", 3, HOUR), ...drills(18)]);
    const panel = await openPanel();
    expect(rowsOf(panel, "Other projects")).toHaveLength(18);
    expect(within(within(panel).getByRole("radiogroup", { name: /^drill-12/ })).getByRole("radio", { name: "Low", checked: true })).toBeTruthy();
    expect(within(panel).getByRole("button", { name: "Show the latest 3" })).toBeTruthy();
  });

  it("counts a project with a job waiting as active, and says so when none is", async () => {
    serve(rules(), [used("old-drill", 0, 41 * DAY)]);
    const panel = await openPanel();
    expect(within(panel).getByText("No project has run a job in the last 7 days.")).toBeTruthy();
    const waiting: Job = { job_id: "job-1", state: "queued", kind: "job", project: "old-drill", position: 1 };
    queueStore.set({ snapshot: { now: NOW, running: [], queued: [waiting], recent: [] }, at: 0 });
    await waitFor(() => expect(rowsOf(panel, "Active in the last 7 days")).toEqual(["old-drill1 waiting"]));
    expect(within(panel).queryByRole("list", { name: "Other projects" })).toBeNull();
  });

  it("keeps one list when the answer does not say how the projects were used", async () => {
    serve(rules({ projects: { "example-app": 1 } }), undefined);
    const panel = await openPanel();
    expect(within(panel).queryByText("Active in the last 7 days")).toBeNull();
    expect(within(panel).queryByText("Other projects")).toBeNull();
    expect(within(panel).getByRole("radiogroup", { name: "docs-site" })).toBeTruthy();
    expect(within(panel).getByRole("radiogroup", { name: "example-app" })).toBeTruthy();
  });
});
