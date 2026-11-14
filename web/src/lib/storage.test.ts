import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "./api";
import { reply } from "./heldServer.testing";
import { fateText, goingNext, headroom, held, lowNodes, nextLine, parseKeepFree, parts, preview, previewText, reserveOf,
         sendRemove, suggestionCount } from "./storage";
import { GB, NOW, body, low, report } from "./storage.testing";
import { without } from "../state/storage";

afterEach(() => { vi.unstubAllGlobals(); tokenStore.set(undefined); });

describe("a node's storage report", () => {
  it("adds up what mulebox holds by kind, Docker left out", () => {
    const sizes = Object.fromEntries(parts(report()).map((part) => [part.key, part.size / GB]));
    expect(sizes.folders).toBeCloseTo(3.5);  // the folders and each project's repository
    expect(sizes).toMatchObject({ caches: 2, tools: 3, runners: 4, other: 0.5 });
    expect(held(report()) / GB).toBeCloseTo(13);
    expect(headroom(report()) / GB).toBe(31);
    expect(headroom(low()) / GB).toBe(-5);
  });

  it("says what happens to a folder in the report's own words", () => {
    expect(fateText({ fate: "remove", removed_in: null })).toBe("Goes at the next sweep");
    expect(fateText({ fate: "stays", removed_in: 0.5 })).toBe("Removed within a day");
    expect(fateText({ fate: "stays", removed_in: 3.2 })).toBe("Removed in 4 days");
    expect(fateText({ fate: "latest", removed_in: null })).toBe("Kept: the project's latest");
    expect(fateText({ fate: "running", removed_in: null })).toBe("A job runs in it now");
  });

  it("lists what goes next soonest first, and never a kept or latest folder", () => {
    expect(goingNext(report()).map((f) => f.folder)).toEqual(["fix-login-33333333", "chore-deps-44444444"]);
    expect(nextLine(report())).toBe("1 branch folder goes within a day, 500.0 MB.");
    expect(nextLine(report({ projects: [] }))).toBe("Nothing is due to go on its own.");
  });

  it("counts idle projects that wait for a word, and nodes under their reserve", () => {
    expect(suggestionCount(body())).toBe(1);
    expect(suggestionCount(body({}, report({ idle: [{ project: "example-docs", days: 16, size: 1, kept: true }] })))).toBe(0);
    expect(lowNodes(body())).toEqual([]);
    expect(lowNodes(body({}, low())).map((node) => node.node)).toEqual(["build-1"]);
  });

  it("leaves out what the viewer removed since the report was measured", () => {
    const gone = [{ project: "example-app", folder: "fix-login-33333333", at: NOW }, { project: "example-docs", folder: null, at: NOW }];
    const left = without(report(), gone);
    expect(left.projects.map((p) => [p.project, p.folders.length])).toEqual([["example-app", 3]]);
    expect(left.idle).toEqual([]);
    expect(without(report({ at: NOW + 1 }), gone).projects).toHaveLength(2);  // a newer report says it itself
  });
});

describe("the free space to keep", () => {
  it("reads a share or a size, and says it in bytes for a disk", () => {
    expect(parseKeepFree("10%")).toEqual({ amount: 10, unit: "%" });
    expect(parseKeepFree("50GB")).toEqual({ amount: 50, unit: "GB" });
    expect(parseKeepFree("1TB")).toEqual({ amount: 1000, unit: "GB" });
    expect(parseKeepFree("a lot")).toBeNull();
    expect(reserveOf("20%", 490 * GB)).toBe(98 * GB);
    expect(reserveOf("50GB", 490 * GB)).toBe(50 * GB);
  });

  it("says what other values would do at the next sweep", () => {
    const made = report();
    const same = preview(made, made.policy, NOW)!;
    expect(same).toMatchObject({ goes: 0, shortBy: 0 });
    expect(previewText(same, made)).toBe("With these values the reserve is 49.0 GB and the next sweep removes nothing. The disk stays 31.0 GB above the reserve.");
    const strict = preview(made, { keep_free: "20%", unused_days: 3, keep_latest: false, idle_days: 14 }, NOW)!;
    expect(strict.goes).toBe(3);  // fix/login and chore/deps past 3 days, and example-docs's latest
    expect(strict.frees / GB).toBeCloseTo(1.6);
    expect(previewText(strict, made)).toContain("so mulebox would ask you what else may go");
  });
});

describe("a removal", () => {
  it("asks once, then reads the group until every node answered", async () => {
    const asked: string[] = [];
    let reads = 0;
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      asked.push(`${init?.method ?? "GET"} ${url}`);
      if (url === "/api/session") return reply({ action_token: "token" });
      if (init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({ project: "example-app", branch: "fix/login" });
        return reply({ group: "grp-1", nodes: ["build-1"], done: false });
      }
      reads += 1;
      return reply({ group: "grp-1", done: reads > 1,
                     answers: [{ node: "build-1", output: "refused: a job runs\n", exit_code: reads > 1 ? 1 : null, answered: reads > 1, lost: false }] });
    }));
    expect(await sendRemove("example-app", "fix/login", () => Promise.resolve())).toEqual(["build-1: refused: a job runs"]);
    expect(asked.filter((line) => line.includes("storage"))).toEqual(
      ["POST /api/storage/remove", "GET /api/storage/remove/grp-1", "GET /api/storage/remove/grp-1"]);
  });
});
