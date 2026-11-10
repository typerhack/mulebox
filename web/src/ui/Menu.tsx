// An actions menu: each item has an icon, a bold name and one plain hint (design-system.md,
// Components). An item that loses work asks twice: the first choice arms it, the second
// sends. A refusal stays in the menu, in the server's own words.

import * as Dropdown from "@radix-ui/react-dropdown-menu";
import type { LucideIcon } from "lucide-react";
import { Fragment, useState, type ReactElement } from "react";

import { problemText } from "../lib/api";
import { cx } from "./cx";

export interface MenuItem {
  id: string;
  Icon: LucideIcon;
  label: string;
  hint: string;
  danger?: boolean;
  sure?: string;                       // the armed label of a danger item
  run: () => void | Promise<unknown>;
}
export type MenuGroups = MenuItem[][];

interface Props { groups: MenuGroups; label: string; children: ReactElement }

export function ActionMenu({ groups, label, children }: Props) {
  const [open, setOpen] = useState(false);
  const [armed, setArmed] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const shown = groups.filter((group) => group.length);

  const change = (next: boolean) => {
    setOpen(next);
    setArmed(null);
    setProblem(null);
  };
  const choose = async (item: MenuItem) => {
    if (item.danger && armed !== item.id) { setArmed(item.id); return; }
    try {
      await item.run();
      change(false);
    } catch (failure) {
      setProblem(problemText(failure));
    }
  };

  return (
    <Dropdown.Root open={open} onOpenChange={change} modal={false}>
      <Dropdown.Trigger asChild>{children}</Dropdown.Trigger>
      <Dropdown.Portal>
        <Dropdown.Content align="end" sideOffset={4} collisionPadding={8} aria-label={label}
          className="z-20 w-menu max-w-full rounded-l border border-line-strong bg-surface-1 p-1 shadow-menu dark:bg-surface-2">
          {shown.map((group, index) => (
            <Fragment key={group[0].id}>
              {index > 0 && <Dropdown.Separator className="my-1 border-t border-line" />}
              {group.map((item) => {
                const isArmed = armed === item.id;
                return (
                  <Dropdown.Item key={item.id} onSelect={(event) => { event.preventDefault(); void choose(item); }}
                    className="flex cursor-pointer items-start gap-3 rounded-s px-3 py-2 outline-none lit:bg-surface-3 touch:min-h-ctl-touch">
                    <item.Icon aria-hidden className={cx("mt-px size-icon", item.danger && "text-danger")} />
                    <span className="grid min-w-0">
                      <b className="font-semibold">
                        {isArmed ? (item.sure ?? `Yes, ${item.label.toLowerCase()}`) : item.label}
                      </b>
                      <small className="text-sm text-ink-2">{isArmed ? "Choose again to confirm" : item.hint}</small>
                    </span>
                  </Dropdown.Item>
                );
              })}
            </Fragment>
          ))}
          {!shown.length && <p className="px-3 py-2 text-sm text-ink-2">Nothing to change right now.</p>}
          {problem && <p role="alert" className="px-3 py-2 text-sm font-medium">Not changed. {problem}</p>}
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}
