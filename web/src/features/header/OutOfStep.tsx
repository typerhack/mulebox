// The strip above the panels: what is out of step between the node, its workers and
// the dev machines that send jobs (dashboard/notices.py), each with the command that fixes it.
// Two levels: `danger` (a worker, jobs can fail) in red, `warning` (a dev machine, its jobs still
// run) in amber; the strip takes its worst line's colour. A mark in the header, with the
// count, stays in sight when the page scrolls and brings the strip back into view. Both are
// absent while everything is in step, the usual case.
//
// The strip also says when a node is under its free-space reserve and the cleanup rules have
// nothing left to remove (the user's pick for that warning): its line opens the review
// window, where the owner decides what goes (features/storage/ReviewWindow.tsx). And it holds
// agents' requests for more space, amber until answered (features/asks/AskLines.tsx); the mark
// counts them. What was answered or allowed is a grey strip of its own (CalmStrip.tsx).

import { CircleQuestionMark, OctagonAlert, TriangleAlert } from "lucide-react";
import { useRef, useState } from "react";

import type { Notice } from "../../lib/types";
import { bytes } from "../../lib/format";
import { lowNodes } from "../../lib/storage";
import { tickStore, useMachines } from "../../state/live";
import { useStore } from "../../lib/store";
import { useStorage } from "../../state/storage";
import { useWaiting } from "../../state/asks";
import { AskLines } from "../asks/AskLines";
import { Button } from "../../ui/Button";
import { WithCode } from "../../ui/Code";
import { cx } from "../../ui/cx";
import { Tip } from "../../ui/Tip";
import { ReviewWindow } from "../storage/ReviewWindow";

const STRIP_ID = "out-of-step";
const worst = (items: Notice[]) => (items.some((item) => item.level === "danger") ? "danger" : "warning");
const iconOf = (level: string) => (level === "danger" ? OctagonAlert : TriangleAlert);
const toneOf = (level: string) => (level === "danger" ? "text-danger" : "text-warning");

export function OutOfStepMark() {
  const items = useMachines()?.notices ?? [];
  const asks = useWaiting().reduce((n, group) => n + group.asks.length, 0);
  const low = lowNodes(useStorage().body).length, count = items.length + low + asks;
  if (!count) return null;
  const level = worst(items), Icon = items.length || low ? iconOf(level) : CircleQuestionMark;
  const word = asks && count === asks ? `${count} to answer` : low || asks ? `${count} to look at` : `${count} out of step`;
  const show = () => {
    const strip = document.getElementById(STRIP_ID);
    strip?.scrollIntoView({ block: "start" });
    strip?.focus({ preventScroll: true });
  };
  return (
    <Tip text={word}>
      <button type="button" aria-label={`${word}: show`} onClick={show}
        className="inline-flex h-ctl-icon touch:h-ctl-touch items-center gap-1 rounded-m border border-line-strong bg-surface-1 px-2 text-sm font-semibold hover:border-ink-1 hover:bg-surface-3">
        <Icon aria-hidden className={cx("status-icon size-icon", toneOf(level))} />
        <span className="num">{count}</span>
      </button>
    </Tip>
  );
}

export function OutOfStepStrip() {
  const items = useMachines()?.notices ?? [];
  const { body } = useStorage();
  const low = lowNodes(body);
  const asks = useWaiting().length;
  const [reviewing, setReviewing] = useState<string | null>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  useStore(tickStore);
  const reviewed = low.find((node) => node.node === reviewing);
  if (!items.length && !low.length && !asks) return null;
  const level = worst(items);
  return (
    <section id={STRIP_ID} role="status" aria-label={items.length ? "Out of step" : low.length ? "Low disk space" : "Requests from agents"} tabIndex={-1}
      className={cx("scroll-mt-8 rounded-m border px-3 py-2",
                    level === "danger" ? "border-danger bg-failed-soft" : "border-warning bg-warning-soft")}>
      <ul className="grid gap-1">
        {items.map((item, index) => {
          const Icon = iconOf(item.level);
          return (
            <li key={index} className="flex items-start gap-3">
              <Icon aria-hidden className={cx("status-icon mt-px size-icon", toneOf(item.level))} />
              <p className="min-w-0">
                <strong className="font-semibold"><WithCode text={item.text} /></strong>{" "}
                <span className="text-ink-2"><WithCode text={item.fix} /></span>
              </p>
            </li>
          );
        })}
        {low.map(({ node, report }) => report?.short && (
          <li key={node} className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <TriangleAlert aria-hidden className="status-icon size-icon flex-none self-start mt-px text-warning" />
            <p className="min-w-0 flex-1 basis-col-l">
              <strong className="font-semibold">
                {node} has {bytes(report.disk.free)} free, {bytes(report.short.need)} under its reserve of {bytes(report.disk.reserve)}.
              </strong>{" "}
              <span className="text-ink-2">
                The cleanup has nothing left to remove on its own.{" "}
                {report.short.folders.length ? `mulebox can free up to ${bytes(report.short.could_free)} if you say so; jobs keep running meanwhile.`
                  : "No branch folder is left to offer: free space some other way, or lower the reserve in the node's settings."}
              </span>
            </p>
            {report.short.folders.length > 0 && (
              <Button aria-haspopup="dialog" onClick={(event) => { opener.current = event.currentTarget; setReviewing(node); }}>Review what goes</Button>
            )}
          </li>
        ))}
        <AskLines />
      </ul>
      {reviewed?.report && body && (
        <ReviewWindow node={reviewed.node} body={body} report={reviewed.report} now={Date.now() / 1000} opener={opener}
          onClose={() => setReviewing(null)} />
      )}
    </section>
  );
}
