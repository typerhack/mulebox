import { describe, expect, it } from "vitest";

import { shownState, slotsText, usedSlots } from "./parts";
import { machine } from "./testing";

describe("a node in dev mode", () => {
  const dev = machine({ state: "dev", slots: 3, free_slots: 0, jobs: [] });

  it("shows no slot used by others' jobs, and what it takes", () => {
    expect(usedSlots(dev)).toBe(0);
    expect(slotsText(dev)).toBe("takes only jobs sent with --on, 0 running");
    expect(shownState(dev).word).toBe("Dev");
  });
});
