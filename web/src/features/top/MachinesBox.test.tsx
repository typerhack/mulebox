import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { MachinesPanel } from "../../lib/types";
import type { Shown } from "../../state/picked";
import { TipProvider } from "../../ui/Tip";
import { machine } from "../machines/testing";
import { MachinesBox } from "./MachinesBox";

afterEach(cleanup);

const host = machine({ name: "build-1", host: true });
const other = machine({ name: "build-2" });
const panel = (rows = [host, other]): MachinesPanel =>
  ({ machines: rows, total: rows.length, online: rows.length, free_slots: 4, notices: [] } as unknown as MachinesPanel);
const shown = (m = host): Shown => ({ machine: m, isHost: m === host, samples: [], detailed: false, lastSeen: null });
const pressed = (name: string) => screen.getByRole("button", { name }).getAttribute("aria-pressed");

function draw(p: MachinesPanel, s: Shown) {
  render(<TipProvider><MachinesBox panel={p} shown={s} now={0} /></TipProvider>);
}

describe("which machine the panels show", () => {
  it("marks the host when it is the default", () => {
    draw(panel(), shown());
    expect(pressed("build-1")).toBe("true");
    expect(pressed("build-2")).toBe("false");
  });

  it("marks a picked machine and not the host", () => {
    draw(panel(), shown(other));
    expect(pressed("build-2")).toBe("true");
    expect(pressed("build-1")).toBe("false");
  });

  it("marks nothing with one machine alone", () => {
    draw(panel([host]), shown());
    expect(pressed("build-1")).toBe("false");
  });
});
