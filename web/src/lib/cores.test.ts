import { describe, expect, it } from "vitest";

import { busiest, rest } from "./cores";

describe("the busiest cores of the compact CPU view", () => {
  const loads = [5, 90, 3, 60, 2, 75, 1, 40];

  it("names the busiest, in core order", () => {
    expect(busiest(loads, 3)).toEqual([1, 3, 5]);
  });

  it("keeps a shown core until another is clearly busier", () => {
    const held = [1, 3, 7]; // core 7 at 40 against core 5 at 75: a clear difference
    expect(busiest(loads, 3, held)).toEqual([1, 3, 5]);
    const close = [5, 90, 3, 60, 2, 45, 1, 40]; // core 5 at 45 is only 5 points above core 7
    expect(busiest(close, 3, held)).toEqual([1, 3, 7]);
  });

  it("drops held cores a machine no longer has", () => {
    expect(busiest([10, 20], 2, [0, 9])).toEqual([0, 1]);
  });

  it("sums up the rest", () => {
    expect(rest(loads, [1, 3, 5])).toEqual({ count: 5, average: 10.2, highest: 40 });
    expect(rest([1, 2], [0, 1])).toBeNull();
  });
});
