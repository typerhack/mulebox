// The header: the name and version, the views, the out-of-step mark, Queue actions, whether
// the page is live, and the two switches each viewer sets for themselves.

import { ChartColumn, History, List, LogOut, Radio, Server, type LucideIcon } from "lucide-react";

import type { Route } from "../../lib/router";
import { useStore } from "../../lib/store";
import { connStore, healthStore, signOut } from "../../state/live";
import { Button } from "../../ui/Button";
import { cx } from "../../ui/cx";
import { Tip } from "../../ui/Tip";
import { QueueActions } from "../jobs/QueueActions";
import { MeterSwitch, ThemeSwitch } from "./Switches";
import { OutOfStepMark } from "./OutOfStep";

const VIEWS: [Route["page"], string, string, LucideIcon][] = [
  ["queue", "#/", "Queue", List], ["machines", "#/machines", "Machines", Server],
  ["history", "#/history", "History", History], ["stats", "#/stats", "Statistics", ChartColumn],
];

function Live() {
  const conn = useStore(connStore);
  const live = conn.state === "live";
  return (
    <Tip text={live ? "Connected, updating live" : "Not connected; the page shows what it last heard"}>
      <span role="status" className="inline-flex items-center gap-2 px-1 text-sm font-medium whitespace-nowrap text-ink-2">
        <Radio aria-hidden className={cx("status-icon size-icon", live ? "text-passed" : "text-warning")} />
        <span className="max-touch:sr-only">{conn.text}</span>
      </span>
    </Tip>
  );
}

export function Header({ page }: { page: Route["page"] }) {
  const health = useStore(healthStore);
  const current = page === "job" ? "queue" : page;
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-surface-0">
      <div className="flex min-h-head flex-wrap items-center gap-x-3 px-gutter max-md:gap-x-2">
        <a href="#/" className="text-lg font-semibold tracking-tight no-underline">mulebox</a>
        <span className="font-mono text-xs text-ink-3">{health.version ?? ""}</span>
        <nav aria-label="Views"
          className="ml-4 flex gap-5 self-stretch max-md:order-3 max-md:ml-0 max-md:basis-full max-md:border-t max-md:border-line">
          {VIEWS.map(([id, href, name, Icon]) => (
            <a key={id} href={href} aria-current={id === current ? "page" : undefined}
              className="inline-flex min-h-head items-center gap-2 border-y-2 border-transparent font-medium whitespace-nowrap text-ink-2 no-underline hover:text-ink-1 on:border-b-accent on:font-semibold on:text-ink-1 max-md:min-h-ctl-touch">
              <Icon aria-hidden className="size-icon max-touch:hidden" /><span>{name}</span>
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <OutOfStepMark />
          <QueueActions />
          <Live />
          <MeterSwitch />
          <ThemeSwitch />
          {health.sign_in && (
            <Button tone="ghost" onClick={() => void signOut()}>
              <LogOut aria-hidden className="size-icon-s" /><span className="max-md:sr-only">Sign out</span>
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}
