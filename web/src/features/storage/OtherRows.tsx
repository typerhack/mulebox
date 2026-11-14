// What a node holds beside its branch folders: package caches, toolchains and browsers,
// GitHub runners, uploads and job folders, each with its size and its path to copy. Then
// Docker's own totals: all of Docker on the node, not only mulebox's, shown and never cleaned.

import { Layers, Package, Workflow, Wrench, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { bytes, plural } from "../../lib/format";
import type { Report } from "../../lib/storage";
import { RowActs } from "./ProjectRows";

export function Head({ icon: Icon, title, note, columns }: { icon: LucideIcon; title: string; note?: string; columns?: string[] }) {
  return (
    <div className="keep-head text-sm">
      <h3 className="flex min-w-0 flex-wrap items-center gap-x-2 font-semibold">
        <Icon aria-hidden className="size-icon-s flex-none" />{title}
        {note && <span className="font-normal text-ink-2">{note}</span>}
      </h3>
      {columns && <div className="keep-meta font-semibold text-ink-2">{columns.map((name) => <span key={name}>{name}</span>)}</div>}
    </div>
  );
}

function Row({ name, note, size, says, path, what }: { name: string; note?: string; size: number | null; says: ReactNode; path?: string | null; what?: string }) {
  return (
    <div className="keep-row">
      <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
        <strong className="font-semibold wrap-anywhere">{name}</strong>
        {note && <span className="text-sm text-ink-2">{note}</span>}
      </span>
      <span className="keep-meta text-sm">
        <strong className="num font-semibold">{bytes(size)}</strong><span />
        <span className="text-ink-2">{says}</span>
      </span>
      <RowActs path={path ?? null} what={what ?? name} />
    </div>
  );
}

const DOCKER: [string, string, string][] = [
  ["images", "Images", "image"], ["containers", "Containers", "container"],
  ["volumes", "Volumes", "volume"], ["build_cache", "Build cache", "entry"],
];

export function OtherRows({ report }: { report: Report }) {
  const at = report.paths, shared = (name: string) => report.shared[name] ?? 0;
  const caches = report.projects.filter((p) => p.caches > 0).sort((a, b) => b.caches - a.caches);
  const cacheTotal = caches.reduce((a, p) => a + p.caches, 0) + shared("caches_other");
  return (
    <>
      <Head icon={Package} title="Package caches" note={bytes(cacheTotal)} />
      {caches.map((p) => (
        <Row key={p.project} name={p.project} size={p.caches} says="Kept: a job's packages come from it"
          path={at && `${at.packages}/${p.project}`} what={`the package caches of ${p.project}`} />
      ))}
      {shared("caches_other") > 0 && <Row name="Other caches" size={shared("caches_other")} says="Kept" path={at?.caches_other} />}
      {!cacheTotal && <p className="py-2 text-sm text-ink-2">No package caches on this node.</p>}

      <Head icon={Wrench} title="Toolchains and browsers" note={bytes(shared("toolchains") + shared("browsers"))} />
      <Row name="Toolchains" note="pinned Node.js, pnpm and the like" size={shared("toolchains")} says="Kept: installed once per version" path={at?.toolchains} />
      <Row name="Browsers" note="Playwright's" size={shared("browsers")} says="Kept: shared by every job" path={at?.browsers} />

      <Head icon={Workflow} title="Runners and jobs" note={bytes(shared("runners") + shared("staging") + shared("jobs"))} />
      <Row name="GitHub runners" size={shared("runners")} says="Kept while a runner is registered" path={at?.runners} />
      <Row name="Uploads" note="what dev machines sent" size={shared("staging")} says="One snapshot per project stays" path={at?.staging} />
      <Row name="Job folders" size={shared("jobs")} says="Each goes when its job ends" path={at?.jobs} />

      <Head icon={Layers} title="Docker" note="all of Docker on this node, not only mulebox's" />
      <p className="py-2 text-sm text-ink-2">
        Shown, never cleaned by mulebox: a job's own containers and images go with the job, and the rest cannot be told from yours.
      </p>
      {report.docker ? DOCKER.filter(([key]) => report.docker?.[key]).map(([key, name, one]) => {
        const part = report.docker![key];
        return (
          <Row key={key} name={name} note={part.count === null ? undefined : plural(part.count, one).replace("entrys", "entries")}
            size={part.size} says={part.reclaimable ? `${bytes(part.reclaimable)} unused, by Docker's count` : "In use"} />
        );
      }) : <p className="py-2 text-sm text-ink-2">Docker did not answer on this node, or is not installed.</p>}
    </>
  );
}
