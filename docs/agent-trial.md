# Trying mulebox on a real project

This file is for an AI coding agent. A user may say: "read mulebox's docs/agent-trial.md and test
it on this project". No skill is needed: `docs/agents.md` and `mulebox contract` hold the rules.

The goal is to find out whether mulebox beats running the same work directly on the build machine,
and what gets in the way. Report what happened, good or bad. A rough report of a real failure is
worth more than a clean one.

## Ground rules

- Do this project's normal work through mulebox. Do not fall back to running heavy commands on the
  laptop. If the build machine cannot be reached, stop and tell the user.
- Change nothing in this project's CI, runners or deployment.
- Do not work around a mulebox problem without saying so: note it, then go on if you can.
- `.mulebox.yml` and small changes for the test stay uncommitted unless the user says otherwise.
  Use a throwaway branch for anything else.
- Never put secrets in `.mulebox.yml` or in a report.
- Do not cancel a job you did not start. Do not change anything on the build machine by hand.
- Do not post anything anywhere. The report goes to the user.
- Do not start long jobs just to prove a point. A real gate takes what it takes, once or twice.

## The test

Note the wall-clock time of each step.

1. **Start.** Run `mulebox --version`, `mulebox queue`, then `mulebox contract`.
2. **Set up.** If the project has no `.mulebox.yml`, follow `docs/agents.md`, section 2. `mulebox init`
   may write a first version. If there is one, read it against the current docs: dependency installs
   belong in `install:`, also in a compose project. Run `mulebox doctor` until it is clean.
3. **First gate.** Run `mulebox check` on the project's real gate, the same work as its CI.
4. **Repeat.** Run `mulebox check` again with nothing changed. It should say "already tested" in about
   a second.
5. **A small change.** Change one comment or a small file, and run `mulebox check` again. Note how
   much was sent, and whether `install` was skipped and how long the job took.
6. **Break it.** Add a real failure, such as a failing test or a type error, and run the check. Is
   the failure summary enough to fix it without reading the full log? Note the exit code. Undo the
   change, and check that the result comes back as "already tested".
7. **Do other work meanwhile.** Run `mulebox check --detach`, keep working, and collect the result
   with `mulebox wait <job-id>`. Try `mulebox events --job <job-id> --json` once. Which way of waiting
   suited you?
8. **Two branches.** With a second branch in another worktree, start a check on both. They should run
   at the same time. Two checks on one branch should wait in line and say why.
9. **Ahead of time.** After a lockfile change, run `mulebox warm`, then `mulebox check`.
10. **The usual work.** Use mulebox for one real task from this project, such as a single test file,
    a build or a browser test.

If a step does not apply, say why and skip it.

## The report

Give the user this, in plain words:

- **Verdict:** would you use this for this project instead of running on the build machine directly?
- **Times:** each step above, and the same gate without mulebox if that is known.
- **What failed:** the exact command, exit code and job id. Say whether it was mulebox or the project.
- **What was slow or confusing:** anything that made you stop and think, or that the docs got wrong.
- **What you worked around.**
- **What you missed.**

Job ids let the user look a job up. `mulebox feedback draft <job-id> --summary "what happened"` makes
a redacted report of a failed job; show it to the user, who decides whether it goes further.
