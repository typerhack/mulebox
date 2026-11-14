// What the storage tests share: a node's report as a worker's sweep sends it, and the reply
// around it. Every name is an example.

import type { Folder, Report, StorageBody, Sweep } from "./storage";

export const GB = 1e9, NOW = Math.floor(Date.now() / 1000), DAY = 86400;  // the page reads the real clock
export const folder = (name: string, gb: number, daysAgo: number, fate: Folder["fate"], removedIn: number | null = null): Folder =>
  ({ folder: name, size: gb * GB, last_used: NOW - daysAgo * DAY, fate, removed_in: removedIn });

export const report = (more: Partial<Report> = {}): Report => ({
  at: NOW - 600, disk: { total: 490 * GB, free: 80 * GB, reserve: 49 * GB },
  policy: { keep_free: "10%", unused_days: 7, keep_latest: true, idle_days: 14 },
  projects: [
    { project: "example-app", home: 0.5 * GB, caches: 2 * GB, folders: [
      folder("feature-checkout-11111111", 0.7, 0.1, "latest"), folder("main-22222222", 0.6, 2, "kept"),
      folder("fix-login-33333333", 0.5, 6.5, "stays", 0.5), folder("chore-deps-44444444", 0.4, 3, "stays", 4)] },
    { project: "example-docs", home: 0.1 * GB, caches: 0, folders: [folder("main-55555555", 0.7, 16, "latest")] },
  ],
  shared: { toolchains: 2 * GB, browsers: 1 * GB, caches_other: 0, runners: 4 * GB, staging: 0.4 * GB, jobs: 0.1 * GB },
  paths: { projects: "/home/alice/.mulebox/projects", packages: "/home/alice/.mulebox/cache/packages",
           toolchains: "/home/alice/.mulebox/cache/toolchains", browsers: "/home/alice/.mulebox/cache/playwright",
           caches_other: "/home/alice/.mulebox/cache", runners: "/home/alice/.mulebox/runners",
           staging: "/home/alice/.mulebox/staging", jobs: "/home/alice/.mulebox/jobs" },
  docker: { images: { size: 9.8 * GB, reclaimable: 3.6 * GB, count: 23 } },
  idle: [{ project: "example-docs", days: 16, size: 0.7 * GB, kept: false }],
  short: null, removed: { count: 13, bytes: 4.3 * GB }, ...more,
});

export const body = (more: Partial<StorageBody> = {}, made: Report | null = report()): StorageBody => ({
  nodes: [{ node: "build-1", online: true, version: "1.25.0", report: made }],
  keeps: [{ project: "example-app", branch: "main" }],
  branches: { "example-app": { "feature-checkout-11111111": "feature/checkout", "main-22222222": "main",
                               "fix-login-33333333": "fix/login", "chore-deps-44444444": "chore/deps" },
              "example-docs": { "main-55555555": "main" } },
  editable: true, ...more,
});

// A node 5 GB under its reserve, with what it says could go next, oldest first.
export const low = (): Report => report({
  disk: { total: 490 * GB, free: 44 * GB, reserve: 49 * GB },
  short: { need: 5 * GB, could_free: 5.5 * GB, folders: [
    { ...folder("main-55555555", 0.7, 16, "latest"), project: "example-docs" },
    { ...folder("fix-login-33333333", 3, 6.5, "stays", 0.5), project: "example-app" },
    { ...folder("chore-deps-44444444", 2.5, 3, "stays", 4), project: "example-app" },
    { ...folder("main-22222222", 0.6, 2, "kept"), project: "example-app" }] },
});

// A node on 1.26: its cleanup settings, what it holds, its last cleanup, and the history.
export const sweep = (hoursAgo: number, more: Partial<Sweep> = {}): Sweep => ({
  started: NOW - hoursAgo * 3600, seconds: 4.2, trigger: "hourly", auto: true, would_remove: 0, removed: [], count: 0, bytes: 0,
  docker: { build_cache: 0, images: 0, removed: [], error: null }, free_before: 80 * GB, free_after: 80 * GB, errors: [], ...more,
});
export const cleaned = (): Sweep => sweep(0.2, {
  removed: [{ project: "example-app", folder: "old-pricing-66666666", size: 0.8 * GB, why: "gone" },
            { project: "example-app", folder: "fix-typo-77777777", size: 0.4 * GB, why: "unused" },
            { project: "example-app", folder: "big-88888888", size: 1.1 * GB, why: "size" }],
  count: 3, bytes: 2.3 * GB, docker: { build_cache: 1.2 * GB, images: 0.4 * GB, removed: ["node:20-bookworm"], error: null },
  free_before: 76.1 * GB, free_after: 80 * GB,
});
export const modern = (more: Partial<Report> = {}): Report => report({
  policy: { keep_free: "10%", unused_days: 7, keep_latest: true, idle_days: 14, auto_clean: true, docker_clean: true,
            warn_size: "50GB", max_size: "OFF" },
  held: 13 * GB, over: 0, sweep: cleaned(), ...more,
});
export const withHistory = (made: Report = modern(), history: Sweep[] = [cleaned(), sweep(1.2)]): StorageBody => {
  const base = body({}, made);
  base.branches["example-app"]["old-pricing-66666666"] = "feature/old-pricing";
  return { ...base, history: history.map((one) => ({ node: "build-1", ...one })) };
};
