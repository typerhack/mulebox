// The levels of the order rules: one per project, per branch name or pattern, per GitHub
// workflow, and one for every GitHub run. High, Normal or Low as a segmented choice; a level
// stored as another number (the CLI takes -3 to 3) shows as that number and stays choosable.
//
// Every project the node has seen can be given a level. Those with a job or a GitHub run in the
// last seven days come first; the rest follow, the latest run first, and a long rest shows its
// first few with a control that opens the others in place. It starts open when a level is set
// among the others, so no set level is ever out of sight.
//
// Both groups are one list, each under its heading: a project whose use changes while the panel
// is open (a job of it starts to wait, its last run turns eight days old) moves within that one
// list, so its row stays the same row and the focus stays on the choice it was on.

import { ChevronDown, ChevronUp, Plus } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { repository } from "../../lib/format";
import { OTHER_SHOWN, levelChoices, levelOf, nameProblem, projectGroups, projectNote, signed, type LevelMap, type ProjectRow } from "../../lib/order";
import type { Rules, RulesBody } from "../../lib/types";
import { useQueue } from "../../state/live";
import { Button } from "../../ui/Button";
import { cx } from "../../ui/cx";
import { Segmented } from "../../ui/Segmented";

// `readOnly`: this page cannot change the rules; `busy`: a save is on its way, nothing takes an edit.
interface Props { body: RulesBody; draft: Rules; edit: (change: (rules: Rules) => Rules) => void; readOnly: boolean; busy?: boolean }

const HEAD = "mt-4 text-sm font-semibold text-ink-2";
const NOTE = "text-sm text-ink-2";
const GROUP = "mt-3 text-sm text-ink-2";

// `lead`: the first row under a group's heading, which takes no hairline above it.
interface RowProps { name: string; note?: string; mono?: boolean; lead?: boolean; value: number; saved: number; words: Record<string, number>;
                     onChange: (level: number) => void; readOnly: boolean }

// The choice keeps to the row's right edge, also when it wraps under a long name: the rings of
// stacked rows stay in columns.
function LevelRow({ name, note, mono, lead, value, saved, words, onChange, readOnly }: RowProps) {
  const id = useId();
  return (
    <li className={cx("flex flex-wrap items-center justify-end gap-x-3 py-2", !lead && "border-t border-line first:border-t-0")}>
      <span id={id} className="mr-auto min-w-0 font-medium break-words">
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
  const waiting = new Map<string, number>();
  for (const job of snapshot?.queued ?? []) if (job.project) waiting.set(job.project, (waiting.get(job.project) ?? 0) + 1);
  const { flat, active, other } = projectGroups(body, draft, waiting);
  const now = body.now ?? Date.now() / 1000;
  const hasLevel = (row: ProjectRow) => Boolean(levelOf(body.rules.projects, row.name) || levelOf(draft.projects, row.name));
  // The rest past its first few: open once a level is set there, and from then as the viewer left it.
  const long = other.length > OTHER_SHOWN + 1;
  const levelBelow = long && other.slice(OTHER_SHOWN).some(hasLevel);
  const [opened, setOpened] = useState(levelBelow);
  const [chosen, setChosen] = useState<boolean | null>(null);
  if (levelBelow && !opened) setOpened(true);
  const all = !long || (chosen ?? opened);
  // A row's key is its project alone, whichever group it is in, so a move keeps the row.
  const rows = (group: ProjectRow[]) => group.map((row, index) => (
    <LevelRow key={`project ${row.name}`} lead={index === 0} name={repository({ project: row.name })} note={projectNote(row, now, flat)}
      value={levelOf(draft.projects, row.name)} saved={levelOf(body.rules.projects, row.name)} words={words} readOnly={locked}
      onChange={setLevel("projects", row.name)} />
  ));
  const heading = (key: string, text: string) => <li key={key}><h5 className={GROUP}>{text}</h5></li>;
  const projects: ReactNode[] = flat ? rows(active) : [
    heading("active", "Active in the last 7 days"),
    ...(active.length ? rows(active) : [<li key="none active" className={NOTE}>No project has run a job in the last 7 days.</li>]),
    ...(other.length ? [heading("other", "Other projects"), ...rows(all ? other : other.slice(0, OTHER_SHOWN))] : []),
  ];
  const Chevron = all ? ChevronUp : ChevronDown;
  const named = (map: "branches" | "workflows") => [...new Set([...Object.keys(body.rules[map]), ...Object.keys(draft[map])])];
  const list = (map: LevelMap, names: string[]) => (
    <ul>
      {names.map((name) => (
        <LevelRow key={name} name={name} mono
          value={levelOf(draft[map], name)} saved={levelOf(body.rules[map], name)} words={words} readOnly={locked}
          onChange={setLevel(map, name)} />
      ))}
    </ul>
  );
  return (
    <section aria-label="Levels" className="grid">
      <h4 id={`${id}-projects`} className={HEAD}>Project levels</h4>
      {projects.length
        ? <ul id={`${id}-project-list`} aria-labelledby={`${id}-projects`}>{projects}</ul>
        : <p className={NOTE}>No project has sent a job yet.</p>}
      {!flat && long && (
        <Button aria-expanded={all} aria-controls={`${id}-project-list`} className="mt-1 justify-self-start"
          onClick={() => setChosen(!all)}>
          <Chevron aria-hidden className="size-icon" />
          {all ? `Show the latest ${OTHER_SHOWN}` : `Show ${other.length - OTHER_SHOWN} more`}
        </Button>
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
        <li className="flex flex-wrap items-center justify-end gap-x-3 py-2">
          <span id={`${id}-github`} className="mr-auto min-w-0 font-medium">Every GitHub run</span>
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
