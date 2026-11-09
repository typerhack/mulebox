---
name: mulebox
description: Run a project's builds, type checks, lint and tests on a build machine through mulebox instead of on this laptop. Use when working in a repository that has a .mulebox.yml, when about to run a build or test command there, when a project's rules mention mulebox, or when asked to set a project up for mulebox.
---

# mulebox

mulebox runs heavy commands on a Linux build machine through one shared queue. You keep
editing, searching and using git here; builds and tests go through `mulebox`.

## Start here

Run this first, in the project:

    mulebox contract

It prints this project's jobs and commands, what stays local, how git fits in, what is never
uploaded, the exit codes and the rules. It is generated from the project's `.mulebox.yml` and
needs no network. Follow it. It is the source of truth; this skill does not repeat it.

Use `mulebox contract --json` if you want to read it with a tool.

If a project has no `.mulebox.yml`, `mulebox init` writes a first version from its files. Read
what it prints, and correct the file.

Before a project's first job, or after changing its toolchain, `needs` or compose files, run
`mulebox doctor`.
It uploads nothing, and finds what a job would fail on.

This skill was written for contract schema 15. Keep it current, in every session, before
anything else: if `mulebox contract` says on stderr that the mulebox skill is out of date, or
its first line gives a schema higher than 15, run `mulebox skill update`, then read the
SKILL.md it names again, as this session loaded the old text. Tell the user it was updated.

## What to do with it

- **The project has jobs:** run them with the commands the contract lists, instead of the
  project's own build and test commands. Read the job's output as if it ran here; the exit
  code is the job's, or one of the codes the contract explains. One of those means the job
  never started: that is not a failed check, so do not go looking for a bug in the code.
- **It says the project is not set up:** do not set it up unless the user asked. If they
  did, follow section 2 of mulebox's `docs/agents.md`.
- **`mulebox` is not found, or a command exits 3:** stop and tell the user. Never fall back
  to running heavy commands on this machine. That rule matters most: it is what keeps the
  laptop free.

## Long jobs

Do not sit blocked on a job that takes minutes. Start it detached, and go on working:

    mulebox check --detach

It prints the job id once the job is queued; the job then runs without this session. Follow
it without its log:

    mulebox events --job <job-id> --json

That prints one JSON line per state change and exits when the job ends, with the job's exit
code. In Claude Code, the Monitor tool can follow this command, so each line reaches you as
it happens and you can do other work meanwhile. `mulebox status <job-id>` is a one-time look.

When it has ended, `mulebox logs <job-id> --summary` says why it failed, and `mulebox wait
<job-id>` gives what an attached `mulebox check` would have: the log and the exit code. Old
logs expire on the build machine; `mulebox logs` says so when one has, and `mulebox status
<job-id>` still has the result.
Cancel a detached job you no longer want. Three ways to wait: follow it (`mulebox events --job
<job-id> --json`), be pinged (`mulebox wait <job-id>` as a background command), or check later
(`mulebox status <job-id>`). A job finishes either way.

A job goes through stages, and `mulebox status <job-id>` shows `steps` and `usual`: what each
stage took and what passed runs usually take. `usual` is a length from the past, not progress,
so never turn it into a percentage. Image pull progress is summarised, so a quiet log during a
pull is normal. Logs expire after 30 days by default; the job and its stages remain.

## Time limits

No job has a hard time limit while someone watches it. You decide what is stuck.

- Every `timeout_min` of a running job, a `check_in` event in `mulebox events`, and a warning in
  an attached `check` or `wait`, give the elapsed time, the stage, the seconds since its last
  output and that line, the job's CPU, and the machine's CPU and network. `mulebox status <job-id>` shows the same at any
  time. Look at them and decide: let it run, or stop it with `mulebox cancel <job-id>`. A job can
  be busy and silent for minutes, so a quiet log alone proves nothing.
- A job that is working always finishes, whether you are there or not. If you went away, your
  next `mulebox` command in the project prints the result: do not retest.
- Every `timeout_min` a running job asks if all is well. Look at the activity, then answer:
  `mulebox ok <job-id>`, or `mulebox cancel <job-id>`.
- Only a stuck job stops: its question unanswered for one more `timeout_min`, and no activity
  for that long, or 15 minutes if that is shorter. It then shows `stopped: stuck`, with an exit code of its own, which is not a failed
  check: it says nothing about the code.
- `mulebox check` does not repeat itself. On the same files and settings it gives the result of
  the last 24 hours, or joins the same job if it is running. `--again` forces a run.

## Package caches and services

`needs: [cache-pnpm, cache-composer, cache-npm, cache-pip]` turns the caches on. Commands on the
machine use them by themselves. A container sees a cache only if the compose file mounts
`${MULEBOX_CACHE_PNPM}`, `${MULEBOX_CACHE_COMPOSER}`, `${MULEBOX_CACHE_NPM}` or
`${MULEBOX_CACHE_PIP}`.

- To replace an external cache volume, mount the cache on the same container path in a CI-only
  compose file. The refusal of external volumes stands.
- Mount the pnpm store at the same path as on the machine, or pnpm may recreate `node_modules`
  and install again.
- A service with a cache runs as root or `${UID}:${GID}`.
- Every branch of a project on a machine shares its cache. Clearing it is a person's job on the
  build machine: ask, and do not ssh in.
- The build machine's `job_env` reaches services, and the service's own value wins.
- Services get 65536 open files unless they set `ulimits.nofile`.

`install:` holds a project's dependency install: it runs in the project's image with `docker compose
exec`, is skipped until a lockfile, the compose files or the toolchain change, and if it fails the job
counts as never started, as its code did not run. `mulebox warm [job]` runs a job up to its command, ahead of time.

A job in `.mulebox.yml` can be a mapping with `run`, its own `setup` (or `setup: false`) and
`compose: false`, so a quick job skips containers it does not use, and `ports: [vite]`, which gives
it a free port in `MULEBOX_PORT_VITE` for a process of its own, such as a dev server: never a
fixed number. `mulebox contract` shows these as job settings.

The coordinator and the workers must be upgraded together. If `mulebox doctor` reports
different versions, tell the user.

## When something goes wrong

- A job failed: that is a normal result. Read the short failure summary at the end of its
  output first, the full log only if that is not enough, and fix the code.
- A toolchain will not install: a pinned version installs itself on first use, and if that fails
  the error lists the versions the machine has. Use one only if it matches the project; otherwise
  tell the user why it failed.
- A job waits in the queue: that is normal too. Other projects and CI share it. If `check`
  suggests detaching, cancel nothing: the suggestion is for the next run.
- mulebox itself did something wrong (a wrong result, a job that could not start with no clear
  reason, a confusing message): tell the user what happened, with the command, the exit code
  and every job id involved. Copy what mulebox printed now: some notices are in no log. If they
  want it reported, run `mulebox feedback guide` and follow it: it says what evidence to gather,
  how to draft with `mulebox feedback draft`, how to take out private data the scrub cannot
  see, and to post only once the user approves the final file.
