import { describe, expect, it } from "vitest";

import { checkRows, checkedText, headline, heldWords, lowDisk, sentence } from "./health";
import type { Health } from "./health";
import type { Job, Machine } from "./types";

const DISK = { check: "disk", message: "1.2 GB free on the disk of its cache folder, under its min_free of 5.0 GB",
               fix: "free space on build-1: `mulebox storage clean`", since: 100 };
const DOCKER = { check: "docker", message: "Docker does not answer", fix: "start Docker", since: 100 };
const health = (more: Partial<Health>): Health => ({ resting: false, problems: [], withheld: [], ...more });
const node = (name: string, more: Partial<Machine>): Machine =>
  ({ name, state: "available", slots: 2, free_slots: 2, capabilities: [], jobs: [], ...more });

describe("a node's health on the page", () => {
  it("says a resting node and one that holds back Docker in the node's own words", () => {
    const resting = node("build-1", { state: "resting", health: health({ resting: true, problems: [DISK] }) });
    const docker = node("build-2", { health: health({ problems: [DOCKER], withheld: ["docker"] }) });
    expect(headline(resting)).toBe("build-1 is resting and takes no job");
    expect(headline(docker)).toBe("build-2 takes no Docker jobs");
    expect(sentence(DISK.fix)).toBe("Free space on build-1: `mulebox storage clean`.");
    const job: Job = { job_id: "a", state: "queued", kind: "job", held_by: ["build-1"] };
    expect(heldWords(job, [resting, docker])).toBe("build-1 is resting: low disk");
    expect(heldWords({ ...job, held_by: ["build-2"] }, [resting, docker])).toBe("build-2 takes no Docker jobs");
    expect(heldWords({ job_id: "b", state: "queued", kind: "job" } as Job, [resting])).toBeNull();
  });

  it("an offline node says nothing of its last health", () => {
    const gone = node("build-1", { state: "offline", health: health({ resting: true, problems: [DISK] }) });
    expect(heldWords({ job_id: "a", state: "queued", kind: "job", held_by: ["build-1"] } as Job, [gone])).toBeNull();
  });

  it("tells when it checked and checks again", () => {
    expect(checkedText(health({ checked_at: 80, next_at: 140 }), 100)).toBe("checked 20 s ago, again in 40 s");
    expect(checkedText(health({ checked_at: 95 }), 100)).toBe("checked just now");
    expect(checkedText(health({}), 100)).toBe("");
  });

  it("warns under 10% free or 10 GB, but not twice for a node resting on its disk", () => {
    expect(lowDisk(node("a", { disk_free: 21e9, disk_total: 250e9 }))).toEqual({ free: 21e9, total: 250e9 });
    expect(lowDisk(node("a", { disk_free: 30e9, disk_total: 250e9 }))).toBeNull();
    expect(lowDisk(node("a", { disk_free: 9e9, disk_total: null }))).not.toBeNull();
    expect(lowDisk(node("a", { state: "resting", disk_free: 1e9, disk_total: 250e9,
                               health: health({ resting: true, problems: [DISK] }) }))).toBeNull();
  });

  it("lists every check the node runs, the failing one with its problem", () => {
    const rows = checkRows(health({ problems: [DISK], ran: ["disk", "roots", "git", "docker"] }));
    expect(rows.map((row) => row.check)).toEqual(["disk", "roots", "git", "docker", "streak"]);
    expect(rows[0].problem).toBe(DISK);
    expect(rows[1].problem).toBeUndefined();
  });
});
