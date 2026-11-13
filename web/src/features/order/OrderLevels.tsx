// The levels of the order rules: one per project, per branch name or pattern, per GitHub
// workflow, and one for every GitHub run. High, Normal or Low as a segmented choice; a level
// stored as another number (the CLI takes -3 to 3) shows as that number and stays choosable.
//
// Every project the node has seen can be given a level. Those with a job or a GitHub run in the
// last seven days come first; the rest follow, the latest run first, and a long rest shows its
// first few with a control that opens the others in place. It starts open when a level is set
// among the others, so no set level is ever out of sight.

import { ChevronDown, ChevronUp, Plus } from "lucide-react";
import { useId, useState } from "react";

import { repository } from "../../lib/format";
import { OTHER_SHOWN, levelChoices, nameProblem, projectGroups, projectNote, signed, type LevelMap, type ProjectRow } from "../../lib/order";
import type { Rules, RulesBody } from "../../lib/types";
import { useQueue } from "../../state/live";
import { Button } from "../../ui/Button";
import { Segmented } from "../../ui/Segmented";

// `readOnly`: this page cannot change the rules; `busy`: a save is on its way, nothing takes an edit.
interface Props { body: RulesBody; draft: Rules; edit: (change: (rules: Rules) => Rules) => void; readOnly: boolean; busy?: boolean }

const HEAD = "mt-4 text-sm font-semibold text-ink-2";
const NOTE = "text-sm text-ink-2";
const GROUP = "mt-3 text-sm text-ink-2";

interface RowProps { name: string; note?: string; mono?: boolean; value: number; saved: number; words: Record<string, number>;
                     onChange: (level: number) => void; readOnly: boolean }

function LevelRow({ name, note, mono, value, saved, words, onChange, readOnly }: RowProps) {
  const id = useId();
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-line py-2 first:border-t-0">
      <span id={id} className="min-w-0 font-medium break-words">
        <span className={mono ? "font-mono text-sm" : undefined}>{name}</span>
        {note && <small className="num ml-2 text-sm font-normal text-ink-2">{note}</small>}
      </span>
      <Segmented small choices={levelChoices(saved, words)} value={value} labelledBy={id} disabled={readOnly} onChange={onChange} />
    </li>
  );
}

interface AddProps { label: string; placeholder: string; taken: Record<string, number>; disabled?: boolean; onAdd: (name: string) => void }

// A new entry starts at High: a Normal one is no rule at all.
function AddRow({ label, placeholder, taken, disabled, onAdd }: AddProps) {
  const [typed, setTyped] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const add = () => {
    if (disabled) return;
    const name = typed.trim(), refusal = nameProblem(name, taken);
    setProblem(refusal);
    if (refusal) return;
    onAdd(name);
    setTyped("");
  };
  return (
    <div className="flex flex-wrap items-center gap-2 pt-1">
      <input type="text" value={typed} aria-label={label} placeholder={placeholder} autoComplete="off" spellCheck={false}
        onChange={(event) => { setTyped(event.target.value); setProblem(null); }}
        onKeyDown={(event) => { if (event.key === "Enter") add(); }}
        className="h-ctl touch:h-ctl-touch min-w-0 flex-1 basis-col-s rounded-m border border-line-strong bg-surface-1 px-2 font-mono text-sm text-ink-1 placeholder:text-ink-3" />
      <Button disabled={disabled} onClick={add}><Plus aria-hidden className="size-icon-s" />Add</Button>
      {problem && <p role="alert" className="basis-full text-sm font-medium">{problem}</p>}
    </div>
  );
}

export function OrderLevels({ body, draft, edit, readOnly, busy = false }: Props) {
  const locked = readOnly || busy;
  const snapshot = useQueue();
  const id = useId();
  const words = body.levels.words;
  const setLevel = (map: LevelMap, name: string) => (level: number) =>
    edit((rules) => ({ ...rules, [map]: { ...rules[map], [name]: level } }));
  const waiting: Record<string, number> = {};
  for (const job of snapshot?.queued ?? []) if (job.project) waiting[job.project] = (waiting[job.project] ?? 0) + 1;
  const { flat, active, other } = projectGroups(body, draft, waiting);
  const now = body.now ?? Date.now() / 1000;
  const hasLevel = (row: ProjectRow) => Boolean(body.rules.projects[row.name] || draft.projects[row.name]);
  // The rest past its first few: open once a level is set there, and from then as the viewer left it.
  const long = other.length > OTHER_SHOWN + 1;
  const levelBelow = long && other.slice(OTHER_SHOWN).some(hasLevel);
  const [opened, setOpened] = useState(levelBelow);
  const [chosen, setChosen] = useState<boolean | null>(null);
  if (levelBelow && !opened) setOpened(true);
  const all = !long || (chosen ?? opened);
  const projects = (rows: ProjectRow[], heading?: string) => (
    <ul id={heading && `${heading}-list`} aria-labelledby={heading}>
      {rows.map((row) => (
        <LevelRow key={row.name} name={repository({ project: row.name })} note={projectNote(row, now, flat)}
          value={draft.projects[row.name] ?? 0} saved={body.rules.projects[row.name] ?? 0} words={words} readOnly={locked}
          onChange={setLevel("projects", row.name)} />
      ))}
    </ul>
  );
  const Chevron = all ? ChevronUp : ChevronDown;
  const named = (map: "branches" | "workflows") => [...new Set([...Object.keys(body.rules[map]), ...Object.keys(draft[map])])];
  const list = (map: LevelMap, names: string[]) => (
    <ul>
      {names.map((name) => (
        <LevelRow key={name} name={name} mono
          value={draft[map][name] ?? 0} saved={body.rules[map][name] ?? 0} words={words} readOnly={locked}
          onChange={setLevel(map, name)} />
      ))}
    </ul>
  );
  return (
    <section aria-label="Levels" className="grid">
      <h4 className={HEAD}>Project levels</h4>
      {flat ? (active.length ? projects(active) : <p className={NOTE}>No project has sent a job yet.</p>) : (
        <>
          <h5 id={`${id}-active`} className={GROUP}>Active in the last 7 days</h5>
          {active.length ? projects(active, `${id}-active`) : <p className={NOTE}>No project has run a job in the last 7 days.</p>}
          {other.length > 0 && (
            <>
              <h5 id={`${id}-other`} className={GROUP}>Other projects</h5>
              {projects(all ? other : other.slice(0, OTHER_SHOWN), `${id}-other`)}
              {long && (
                <Button aria-expanded={all} aria-controls={`${id}-other-list`} className="mt-1 justify-self-start"
                  onClick={() => setChosen(!all)}>
                  <Chevron aria-hidden className="size-icon" />
                  {all ? `Show the latest ${OTHER_SHOWN}` : `Show ${other.length - OTHER_SHOWN} more`}
                </Button>
              )}
            </>
          )}
        </>
      )}

      <h4 className={HEAD}>Branch levels</h4>
      <p className={NOTE}>A branch name or a pattern such as <code>release/*</code>. The exact name wins, else the longest pattern.</p>
      {list("branches", named("branches"))}
      {!readOnly && <AddRow label="Branch name or pattern" placeholder="release/*" taken={draft.branches} disabled={busy} onAdd={(name) => setLevel("branches", name)(1)} />}

      <h4 className={HEAD}>Workflow levels</h4>
      <p className={NOTE}>A GitHub workflow by its <code>name:</code>, exactly as GitHub shows it.</p>
      {list("workflows", named("workflows"))}
      {!readOnly && <AddRow label="Workflow name" placeholder="Nightly build" taken={draft.workflows} disabled={busy} onAdd={(name) => setLevel("workflows", name)(1)} />}

      <h4 className={HEAD}>GitHub runs</h4>
      <p className={NOTE}>Every GitHub run, against the jobs sent from dev machines.</p>
      <ul>
        <li className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2">
          <span id={`${id}-github`} className="min-w-0 font-medium">Every GitHub run</span>
          <Segmented small choices={levelChoices(body.rules.github, words)} value={draft.github} labelledBy={`${id}-github`} disabled={locked}
            onChange={(level) => edit((rules) => ({ ...rules, github: level }))} />
        </li>
      </ul>
      {(body.levels.min < -1 || body.levels.max > 1) && (
        <p className={`${NOTE} mt-2`}>
          Levels from {signed(body.levels.min)} to {signed(body.levels.max)} can be set with <code>mulebox queue rules</code>; one set there shows here as its number.
        </p>
      )}
    </section>
  );
}
