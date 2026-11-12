import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CopyText } from "./Copy";
import { TipProvider } from "./Tip";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("a line that may be longer than its box", () => {
  it("is cut with an ellipsis and copies the whole text", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const step = "Run actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065";
    render(<TipProvider><CopyText text={step} title="GitHub step" /></TipProvider>);
    expect(screen.getByText(step).className).toContain("truncate");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Copy GitHub step" })); });
    expect(writeText).toHaveBeenCalledWith(step);
    expect(screen.getByRole("button", { name: "Copied" })).toBeTruthy();
  });
});
