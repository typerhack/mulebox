import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Segmented } from "./Segmented";

afterEach(cleanup);

const CHOICES = [{ value: 1, label: "High" }, { value: 0, label: "Normal" }, { value: -1, label: "Low" }];
const part = (name: string) => screen.getByRole("radio", { name });
const ring = (name: string) => part(name).querySelector(".seg-ring") as HTMLElement;

describe("Segmented", () => {
  it("marks the chosen part's ring and no other", () => {
    render(<Segmented choices={CHOICES} value={0} label="Level" onChange={() => {}} />);
    expect(part("Normal").getAttribute("aria-checked")).toBe("true");
    expect(ring("Normal").hasAttribute("data-on")).toBe(true);
    expect(ring("High").hasAttribute("data-on")).toBe(false);
    expect(ring("Low").hasAttribute("data-on")).toBe(false);
    expect(ring("Normal").getAttribute("aria-hidden")).toBe("true");
  });

  it("keeps a part's width when chosen: every word holds its heavier copy", () => {
    const { rerender } = render(<Segmented choices={CHOICES} value={0} label="Level" onChange={() => {}} />);
    const words = () => CHOICES.map((choice) => part(choice.label).querySelector(".seg-word") as HTMLElement);
    const before = words().map((word) => [word.className, word.dataset.word]);
    expect(before).toEqual(CHOICES.map((choice) => ["seg-word", choice.label]));
    rerender(<Segmented choices={CHOICES} value={1} label="Level" onChange={() => {}} />);
    expect(words().map((word) => [word.className, word.dataset.word])).toEqual(before);
    expect(part("High").className).toBe(part("Normal").className);
  });

  it("is a radio group: one tab stop, arrows wrap, Home and End take the ends", () => {
    const onChange = vi.fn();
    render(<Segmented choices={CHOICES} value={-1} label="Level" onChange={onChange} />);
    expect(screen.getByRole("radiogroup", { name: "Level" }).className).toBe("seg");
    expect(CHOICES.map((choice) => part(choice.label).tabIndex)).toEqual([-1, -1, 0]);
    fireEvent.keyDown(part("Low"), { key: "ArrowRight" });
    fireEvent.keyDown(part("Low"), { key: "ArrowLeft" });
    fireEvent.keyDown(part("Low"), { key: "Home" });
    fireEvent.keyDown(part("High"), { key: "End" });
    expect(onChange.mock.calls.map(([next]) => next)).toEqual([1, 0, 1, -1]);
  });

  it("takes no change when off, and still marks what is chosen", () => {
    const onChange = vi.fn();
    render(<Segmented small disabled choices={CHOICES} value={1} label="Level" onChange={onChange} />);
    fireEvent.click(part("Low"));
    fireEvent.keyDown(part("High"), { key: "ArrowRight" });
    expect(onChange).not.toHaveBeenCalled();
    expect(ring("High").hasAttribute("data-on")).toBe(true);
    expect(screen.getByRole("radiogroup").className).toBe("seg seg-small");
  });
});
