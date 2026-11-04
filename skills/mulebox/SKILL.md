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

Before a project's first job, or after changing its toolchain or `needs`, run `mulebox doctor`.
It uploads nothing, and finds what a job would fail on.

## What to do with it

- **The project has jobs:** run them with the commands the contract lists, instead of the
  project's own build and test commands. Read the job's output as if it ran here; the exit
  code is the job's, or one of the codes the contract explains.
- **It says the project is not set up:** do not set it up unless the user asked. If they
  did, follow section 2 of mulebox's `docs/agents.md`.
- **`mulebox` is not found, or a command exits 3:** stop and tell the user. Never fall back
  to running heavy commands on this machine. That rule matters most: it is what keeps the
  laptop free.

## When something goes wrong

- A job failed: that is a normal result. Read the short failure summary at the end of its
  output first, the full log only if that is not enough, and fix the code.
- A toolchain is missing: the error lists the versions the machine has. Use one only if it
  matches the project; otherwise ask the user to install the version it needs.
- A job waits in the queue: that is normal too. Other projects and CI share it.
- mulebox itself could not do what you needed: tell the user what happened, with the
  command, the exit code and the job id. If they want it reported, make a draft with
  `mulebox feedback draft <job-id> --summary "<what happened>"`. It sends nothing. Show
  them the draft; post it with `mulebox feedback post <file>` only once they approve.
