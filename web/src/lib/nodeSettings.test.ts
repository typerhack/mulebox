import { describe, expect, it } from "vitest";

import { asSuggested, changes, rowOf, type NodeSettings } from "./nodeSettings";

const view = (more: Partial<NodeSettings> = {}): NodeSettings => ({
  worker: "build-2", online: true, applies: true, editable: true, error: null,
  current: { slots: 2, priority: "normal" }, pending: null,
  suggested: { slots: 4, reason: "16 cores and 32 GB of memory" }, ...more,
});

describe("a node's settings", () => {
  it("call an edit unsaved, and only a saved change pending", () => {
    expect(rowOf(view(), {}, "slots")).toEqual({ now: 2, yours: 2, mark: null });
    expect(rowOf(view(), { slots: 3 }, "slots")).toEqual({ now: 2, yours: 3, mark: "unsaved" });
    const waiting = view({ pending: { slots: 3 } });
    expect(rowOf(waiting, {}, "slots")).toEqual({ now: 2, yours: 3, mark: "pending" });
    expect(rowOf(waiting, { slots: 3 }, "slots").mark).toBe("pending");
    expect(rowOf(waiting, { slots: 5 }, "slots")).toEqual({ now: 2, yours: 5, mark: "unsaved" });
    expect(rowOf(waiting, {}, "priority")).toEqual({ now: "normal", yours: "normal", mark: null });
  });

  it("send only what differs from what was last sent", () => {
    expect(changes(view(), {})).toEqual({});
    expect(changes(view(), { slots: 2, priority: "fallback" })).toEqual({ priority: "fallback" });
    expect(changes(view({ pending: { slots: 3 } }), { slots: 2 })).toEqual({ slots: 2 });
    expect(changes(view({ pending: { slots: 3 } }), { slots: 3 })).toEqual({});
  });

  it("take the suggestion as fixed values, with no slots before the node reported", () => {
    expect(asSuggested(view())).toEqual({ slots: 4, priority: "normal" });
    expect(asSuggested(view({ suggested: null }))).toEqual({ priority: "normal" });
  });

  it("show nothing to run with for a node that has not reported", () => {
    expect(rowOf(view({ applies: false, current: null }), {}, "slots")).toEqual({ now: null, yours: null, mark: null });
  });
});
