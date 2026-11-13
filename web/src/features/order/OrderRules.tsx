// The rules of the line as a ladder, strongest first, so which rule wins is on the page: each
// step only breaks the ties of the one above (docs/design.md, Order of the line). The two
// steps that are always on carry a lock; the others their switch, at the place they hold.

import { Clock, Flag, Hand, Hourglass, Lock, Repeat, Timer, type LucideIcon } from "lucide-react";
import { useId, type ReactNode } from "react";

import { MAX_AGING_MIN, levelsSet } from "../../lib/order";
import type { Rules, RulesBody } from "../../lib/types";
import { Stepper, Switch } from "../../ui/Controls";

interface Props { body: RulesBody; draft: Rules; edit: (change: (rules: Rules) => Rules) => void; readOnly: boolean }

const Always = () => (
  <span title="Always on" className="inline-flex items-center gap-1 text-sm whitespace-nowrap text-ink-2">
    <Lock aria-hidden className="size-icon-s" />Always
  </span>
);

interface StepProps { rank: number; Icon: LucideIcon; name: string; nameId?: string; hint: ReactNode; control?: ReactNode; children?: ReactNode }

const Step = ({ rank, Icon, name, nameId, hint, control, children }: StepProps) => (
  <li>
    <span aria-hidden className="rank num text-right font-mono text-sm text-ink-2">{rank}</span>
    <Icon aria-hidden className="size-icon" />
    <span className="grid min-w-0">
      <b id={nameId} className="font-semibold">{name}</b>
      <small className="text-sm text-ink-2">{hint}</small>
    </span>
    {control ?? <span />}
    {children && <div className="under">{children}</div>}
  </li>
);

export function OrderRules({ body, draft, edit, readOnly }: Props) {
  const id = useId();
  const aging = draft.aging_min > 0;
  const set = levelsSet(draft);
  const usualAging = body.rules.aging_min || body.defaults.aging_min || 30;
  return (
    <section aria-labelledby={`${id}-h`} className="grid gap-2">
      <div className="grid gap-1">
        <h4 id={`${id}-h`} className="text-sm font-semibold text-ink-2">Rules, strongest first</h4>
        <p className="text-sm text-ink-2">Each rule only breaks the ties of the one above it.</p>
      </div>
      <ol aria-labelledby={`${id}-h`} className="ladder">
        <Step rank={1} Icon={Hand} name="By hand" control={<Always />}
          hint="A job you move with the arrows stays where you put it." />
        <Step rank={2} Icon={Flag} name="Levels"
          control={<span className="num text-sm text-ink-2">{set ? `${set} set` : "none set"}</span>}
          hint="A job's levels add up: its project, branch, workflow, GitHub runs, then time waited. The higher sum goes first.">
          <div className="rule-row border-t border-line pt-2">
            <Hourglass aria-hidden className="mt-hair size-icon self-start" />
            <span className="grid min-w-0">
              <b id={`${id}-aging`} className="font-semibold">Aging</b>
              <small className="text-sm text-ink-2">
                {aging ? `Every ${draft.aging_min} min in line adds one level, so nothing waits forever. It counts once another rule is on.`
                       : "Off: time waited adds no level, so a low job can wait for as long as others come."}
              </small>
            </span>
            <Switch checked={aging} labelledBy={`${id}-aging`} disabled={readOnly}
              onChange={(on) => edit((rules) => ({ ...rules, aging_min: on ? usualAging : 0 }))} />
            {aging && (
              <span className="wide">
                <Stepper value={draft.aging_min} min={1} max={MAX_AGING_MIN} step={5} disabled={readOnly}
                  label="Minutes in line for one level" unit="minutes"
                  onChange={(minutes) => edit((rules) => ({ ...rules, aging_min: minutes }))} />
              </span>
            )}
          </div>
        </Step>
        <Step rank={3} Icon={Repeat} name="Fair turns" nameId={`${id}-fair`}
          control={<Switch checked={draft.fair_turns} labelledBy={`${id}-fair`} disabled={readOnly}
            onChange={(on) => edit((rules) => ({ ...rules, fair_turns: on }))} />}
          hint="Among jobs of one level, projects take turns, so one project's burst does not hold up the rest." />
        <Step rank={4} Icon={Timer} name="Shortest first" nameId={`${id}-short`}
          control={<Switch checked={draft.shortest_first} labelledBy={`${id}-short`} disabled={readOnly}
            onChange={(on) => edit((rules) => ({ ...rules, shortest_first: on }))} />}
          hint="Among jobs of one level and turn, the one that usually takes less time goes first." />
        <Step rank={5} Icon={Clock} name="Arrival" control={<Always />}
          hint="First come, first served. With nothing set above, this alone orders the line." />
      </ol>
    </section>
  );
}
