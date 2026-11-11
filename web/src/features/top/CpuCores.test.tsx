import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TipProvider } from "../../ui/Tip";
import { CpuCores } from "./CpuCores";

const wide = (matches: boolean) => vi.stubGlobal("matchMedia", () => ({
  matches, addEventListener() {}, removeEventListener() {},
}));
beforeEach(() => wide(true));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const loads = Array.from({ length: 32 }, (_, i) => (i === 12 ? 98 : i === 27 ? 86 : i % 7 === 1 ? 60 : 4));
const meters = () => screen.getAllByRole("meter").map((m) => m.getAttribute("aria-label"));
const show = (view: "details" | "compact") =>
  render(<TipProvider><CpuCores cores={loads} view={view} machine="build-1" /></TipProvider>);

describe("the CPU box's views", () => {
  it("details: a meter for every core", () => {
    show("details");
    expect(meters()).toHaveLength(32);
  });

  it("compact on a wide screen: all, the six busiest and one line for the other 26", () => {
    show("compact");
    const shown = meters();
    expect(shown).toHaveLength(8);
    expect(shown[0]).toMatch(/^CPU, all 32 cores/);
    expect(shown).toContain("Core 12: 98%");
    expect(shown).toContain("Core 27: 86%");
    expect(screen.getByText("26 others")).toBeTruthy();
    expect(shown.at(-1)).toMatch(/The other 26 cores: .* on average, 60% at most/);
  });

  it("compact on a narrow screen names four cores", () => {
    wide(false);
    show("compact");
    expect(meters()).toHaveLength(6);
    expect(screen.getByText("28 others")).toBeTruthy();
  });

  it("compact with no more cores than it would name is the details view", () => {
    render(<TipProvider><CpuCores cores={[10, 20, 30, 40]} view="compact" machine="build-1" /></TipProvider>);
    expect(meters()).toHaveLength(4);
  });
});
