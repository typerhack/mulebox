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

Before a project's first job, or after changing its toolchain, `needs` or compose files, run
`mulebox doctor`.
It uploads nothing, and finds what a job would fail on.

This skill was written for contract schema 4. `mulebox contract` prints the current schema on
its first line. If that number is higher, this skill is behind: tell the user that
`mulebox skill update` fixes it, and go on following the contract. Never update this skill
yourself.

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
Cancel a detached job you no longer want: nothing else will.

A job goes through stages, and `mulebox status <job-id>` shows `steps` and `usual`: what each
stage took and what passed runs usually take. `usual` is a length from the past, not progress,
so never turn it into a percentage. Image pull progress is summarised, so a quiet log during a
pull is normal. Logs expire after 30 days by default; the job and its stages remain.

## Package caches and services

`needs: [cache-pnpm, cache-composer]` turns the caches on. Commands on the machine use them by
themselves. A container sees a cache only if the compose file mounts `${MULEBOX_CACHE_PNPM}` or
`${MULEBOX_CACHE_COMPOSER}`.

- To replace an external cache volume, mount the cache on the same container path in a CI-only
  compose file. The refusal of external volumes stands.
- Mount the pnpm store at the same path as on the machine, or pnpm may recreate `node_modules`
  and install again.
- A service with a cache runs as root or `${UID}:${GID}`.
- Every branch of a project on a machine shares its cache. Clearing it is a person's job on the
  build machine: ask, and do not ssh in.
- The build machine's `job_env` reaches services, and the service's own value wins.
- Services get 65536 open files unless they set `ulimits.nofile`.

The coordinator and the workers must be upgraded together. If `mulebox doctor` reports
different versions, tell the user.

## When something goes wrong

- A job failed: that is a normal result. Read the short failure summary at the end of its
  output first, the full log only if that is not enough, and fix the code.
- A toolchain is missing: the error lists the versions the machine has. Use one only if it
  matches the project; otherwise ask the user to install the version it needs.
- A job waits in the queue: that is normal too. Other projects and CI share it. If `check`
  suggests detaching, cancel nothing: the suggestion is for the next run.
- mulebox itself could not do what you needed: tell the user what happened, with the
  command, the exit code and the job id. If they want it reported, make a draft with
  `mulebox feedback draft <job-id> --summary "<what happened>"`. It sends nothing. Show
  them the draft; post it with `mulebox feedback post <file>` only once they approve.
