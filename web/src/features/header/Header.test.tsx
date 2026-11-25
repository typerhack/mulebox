import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { body, report } from "../../lib/storage.testing";
import { storageStore } from "../../state/storage";
import { TipProvider } from "../../ui/Tip";
import { Header } from "./Header";

afterEach(() => { cleanup(); storageStore.set({ body: null, problem: null }); });
const show = () => render(<TipProvider><Header page="storage" /></TipProvider>);

describe("the header's views", () => {
  it("has Storage after Machines, each with its icon", () => {
    show();
    const links = [...screen.getByRole("navigation", { name: "Views" }).querySelectorAll("a")];
    expect(links.map((link) => link.textContent)).toEqual(["Queue", "Machines", "Storage", "History", "Statistics", "Usage"]);
    expect(links.every((link) => link.querySelector("svg"))).toBe(true);
    expect(links[2].getAttribute("href")).toBe("#/storage");
    expect(links[2].getAttribute("aria-current")).toBe("page");
    expect(links[5].getAttribute("href")).toBe("#/usage");
  });

  it("counts the idle projects that wait for a word on Storage, and nothing when none does", () => {
    storageStore.set({ body: body(), problem: null });
    show();
    expect(screen.getByRole("img", { name: "1 to decide" }).textContent).toBe("1");
    cleanup();
    storageStore.set({ body: body({}, report({ idle: [] })), problem: null });
    show();
    expect(screen.queryByRole("img", { name: /to decide/ })).toBeNull();
  });
});
