import { describe, expect, it } from "vitest";

import { changeOf, isDirty, levelChoices, levelName, levelsSet, nameProblem, ordering, placeOf } from "./order";
import type { Job, Rules } from "./types";

const rules = (more: Partial<Rules> = {}): Rules =>
  ({ projects: {}, branches: {}, workflows: {}, github: 0, aging_min: 30, shortest_first: false, fair_turns: false, ...more });
const job = (more: Partial<Job>): Job => ({ job_id: "job-1", state: "queued", kind: "job", position: 2, ...more });

describe("the order rules", () => {
  it("names a level by its word, and any other by its number", () => {
    expect([1, 0, -1, 2, -3].map((level) => levelName(level))).toEqual(["high", "normal", "low", "+2", "-3"]);
    expect(levelChoices(0).map(([, text]) => text)).toEqual(["High", "Normal", "Low"]);
    expect(levelChoices(-2)).toEqual([[1, "High"], [0, "Normal"], [-1, "Low"], [-2, "-2"]]);
  });

  it("sends only what differs, and 0 for an entry that goes", () => {
    const saved = rules({ projects: { "example-app": 1, "docs-site": -1 }, branches: { main: 1 } });
    const draft = rules({ projects: { "example-app": 1, "docs-site": 0, "example-api": 2 }, branches: {}, fair_turns: true, aging_min: 0 });
    expect(changeOf(saved, draft)).toEqual(
      { projects: { "docs-site": 0, "example-api": 2 }, branches: { main: 0 }, fair_turns: true, aging_min: 0 });
    expect(isDirty(saved, saved)).toBe(false);
    // An entry added and set back to normal before Save is no change.
    expect(isDirty(rules(), rules({ workflows: { CI: 0 } }))).toBe(false);
  });

  it("counts the levels that are set, and knows aging alone orders nothing", () => {
    expect(levelsSet(rules({ projects: { a: 1, b: 0 }, github: -1 }))).toBe(2);
    expect(ordering(rules({ aging_min: 10 }))).toBe(false);
    expect(ordering(rules({ shortest_first: true }))).toBe(true);
  });

  it("refuses an empty, long or repeated name", () => {
    expect(nameProblem("", {})).toContain("Type");
    expect(nameProblem("x".repeat(101), {})).toContain("100");
    expect(nameProblem("main", { main: 1 })).toContain("already");
    expect(nameProblem("release/*", { main: 1 })).toBeNull();
  });
});

describe("the reason on a waiting row", () => {
  it("is absent with the defaults and nothing moved", () => {
    expect(placeOf(job({}))).toBeNull();
  });

  it("puts a move by hand first, naming the job it stands beside", () => {
    expect(placeOf(job({ moved: "front", order: { by_hand: true, moved: { side: "front" } } }))?.text).toBe("moved to the front by hand");
    expect(placeOf(job({ order: { by_hand: true, moved: { side: "before", job_id: "job-01abcxfzpmd", in_line: true } } }))?.text)
      .toBe("moved by hand, just ahead of xfzpmd");
    expect(placeOf(job({ order: { by_hand: true, moved: { side: "after", job_id: "job-01abcxfzpmd", in_line: false } } }))?.text)
      .toContain("which has left the line");
    expect(placeOf(job({ kind: "upgrade", order: { by_hand: true, moved: { side: "front" } } }))?.text).toBe("an upgrade, sent to go first");
  });

  it("says the levels in words, then the turn and the usual length", () => {
    const order = { level: 1, levels: [{ rule: "project", name: "example-app", level: 1 }], turn: 2, usual_s: 240 };
    expect(placeOf(job({ order }))?.text).toBe("ahead: project high; fair turn 2; usually 4m");
    expect(placeOf(job({ order: { level: -2, levels: [{ rule: "workflow", name: "Nightly build", level: -2 }] } }))?.text)
      .toBe("behind: workflow Nightly build -2");
    expect(placeOf(job({ order: { level: 0, levels: [{ rule: "project", name: "a", level: -1 }, { rule: "waited", over: 90, level: 1 }] } }))?.text)
      .toBe("level 0: project low, waited 1h 30m or more");
    expect(placeOf(job({ order: { level: 0, levels: [], usual_s: null, counted_as_s: 180 } }))?.text)
      .toBe("no usual length yet, counted as 3m");
    expect(placeOf(job({ order: { level: 0, levels: [] } }))?.text).toBe("in order of arrival");
  });
});
