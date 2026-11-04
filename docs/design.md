# mulebox design

Status: design reviewed, not implemented. Version: see [../VERSION](../VERSION).

## Problem

AI coding agents work in many git worktrees at once. Each runs builds, type checks, lint
and test suites on the laptop it lives on. Several at once overheat the laptop, stall video
and the browser, and can crash applications. Hosted CI is slow and has minute quotas.
Most people have, or can cheaply get, an idle Linux machine on the same network.

## Goals

- Agents keep editing locally; every heavy job runs on build machines on the LAN.
- One queue for all projects and all sources (agents, the user, GitHub Actions).
- Results identical in meaning to running locally: same command, exit code, output.
- Safe by default: jobs never touch anything outside mulebox's own folders.
- Easy to grow: add or replace build machines without changing agents or projects.
- Simple to operate for one person; no cloud services, no inbound internet access.

Non-goals (for now): multi-tenant use, internet-facing access, automatic failover,
scheduling by speed or job weight, an MCP server (a thin wrapper may come later).

## Roles

| Role | Runs on | Does |
| --- | --- | --- |
| client | the laptop | `mulebox check`, `mulebox queue`, terminal live view, snapshot upload |
| coordinator | one always-on machine | queue, leases, history, staging of inputs, web dashboard |
| worker | each build machine | claims jobs, prepares workspaces, runs and supervises jobs, cleanup |

Phase 1 runs coordinator and worker on the same machine, as separate components that talk
through the worker protocol, so more workers later are configuration, not a rewrite.

## Connections

- Client to coordinator, and worker to coordinator: SSH to a fixed executable, structured
  JSON on stdin (`ssh -T build-1 ~/.mulebox/bin/mulebox rpc`). No shell-built commands, no
  interpolated paths. One transport for everything.
- Coordinator internals: a local Unix socket between the CLI and the daemon.
- Dashboard: HTTP(S) served on the coordinator machine (see Dashboard).
- GitHub runners connect outbound to GitHub; nothing needs inbound internet access.
- SQLite stays local to the coordinator and is never shared over the network.

## Job lifecycle

States: `uploading -> queued -> starting -> running -> cleaning -> finished`
(`finished` carries `passed | failed | cancelled | timed_out | interrupted`).

1. **Snapshot**: the client copies the worktree to coordinator staging: tracked and
   untracked files plus a deletion list, never following symlinks, always excluding
   `.secret/`, `.env*` (but not a template tracked in git, such as `.env.example`), `secrets/`,
   `.npmrc`, keys, and anything the project config adds.
   The job is queued only when the upload is complete and fingerprinted.
2. **Queue**: one FIFO line. Assignment is atomic: the oldest job a free worker can run.
   Cluster-wide and per-worker slot limits, both default 1.
3. **Workspace**: the worker fetches and verifies the snapshot, then builds a private
   checkout `jobs/<project>/<job-id>/` from its own clone of the project (a worktree's
   `.git` points at the laptop and is useless remotely). Inputs never change during a job.
4. **Run**: as a transient systemd unit with a runtime limit, `KillMode=control-group`,
   CPU and IO weights. A `compose:` project starts first, in that unit, under a Compose
   project name and labels unique to the job (see Docker Compose projects).
5. **Clean**: stop the unit, remove the job's labelled Docker resources, remove the job
   folder through the path-safety module. The slot is free only after cleanup succeeded.
6. **Report**: job id, content fingerprint, base commit, command, toolchain versions, exit
   code, duration, log. If local files changed since submission, the client marks the
   result stale.

## Leases and failure handling

- Client lease: renewed by the waiting client every 20 s, measured on the coordinator's
  clock; expires after 300 s (agent killed, laptop asleep, Wi-Fi gone) and cancels the job.
  Long enough to ride out a few minutes of Wi-Fi loss; the client keeps reconnecting.
- Worker lease: renewed by the worker while it executes; separate from the client lease.
- Idempotent submit (client-chosen key): a lost reply never creates a duplicate job.
- Restart: the coordinator reconciles stored jobs; the worker, before it claims anything,
  stops orphan units and removes leftover job folders and Docker resources found by label.
  Interrupted jobs are marked, never replayed automatically.
- Coordinator down: no new submissions or assignments; running jobs continue until their
  worker lease expires, then stop and clean. A job is never reassigned just because its
  worker vanished.
- Client disconnected after submit: the outcome is "unknown"; reconnect by job id.
- Build machine unreachable: the client fails fast with a clear message and never falls
  back to running locally on its own.

## Agent contract

`mulebox contract` tells an agent how a project builds, tests and uses git through mulebox.
It is generated from `.mulebox.yml` and from the tables the code itself uses, so there is
no file to keep in step, and it needs no network, so its rules are readable when the build
machine is down. Text by default; `--json` has stable keys and a `schema` number, raised
only when a key is removed or changes meaning. Exit 0 outside a project; a broken
`.mulebox.yml` exits 2 rather than hiding the mistake.

## Agent feedback

`mulebox feedback draft` turns what mulebox could not handle into a GitHub issue draft, and
`mulebox feedback post <file>` sends it. mulebox will be public, and the projects using it
may be private, so:

- **Two steps.** `draft` only prints; nothing leaves the machine. An agent shows the draft
  to its user and posts only with their approval. `post` is off until `feedback_repo` is set.
- **Little to leak.** A draft holds the summary, the mulebox version, the operating system
  and the job's result. Never a project, branch, machine or command.
- **Scrubbed.** Secrets, then every name known locally and from the coordinator, including
  other projects', then home folders, email and IP addresses and URLs
  (`common/anonymize.py`).
- **Checked again.** `post` refuses a file the scrub would still change, so what was
  reviewed is what is sent, and details added by hand are caught when they match a rule.
- **Logs on request only.** The scrub cannot recognise a private file name or line of code
  it has no name for, so `--log` is a choice, and reading the draft is a real step.
- **No screenshots.** They cannot be scrubbed, and `gh issue create` cannot attach them.

## Projects

There is no project registry. What a project needs lives in its `.mulebox.yml`, and which
projects exist is already in the job history, so a registry would be a second copy of both.
`mulebox projects` lists what the coordinator has seen, worked out from its jobs. The cost:
a project appears only after its first job, and nothing can be stored about one. Add a
table only when real adoption shows something that belongs in neither place.

## Project config: `.mulebox.yml`

```yaml
project: example-app
needs: [node]            # capabilities a worker must have (e.g. docker)
toolchain:
  node: 22.22.3
  pnpm: 11.22.0
setup: pnpm install --frozen-lockfile
compose: [docker-compose.yml, docker-compose.ci.yml]  # containers for the job; implies docker
jobs:
  check: pnpm check
  test: pnpm exec vitest run
timeout_min: 20
exclude: [reports/]      # added to the built-in secret excludes
```

Toolchains are pinned per project with explicit paths; workers keep package caches,
container images and browsers warm between jobs.

## Docker Compose projects

`compose:` must run the project's real files, written for a throwaway CI runner, on a
machine that also does other work. So the worker does not run them as they are:

- **One file per job.** `docker compose config` merges the project's files, every published
  port is moved, and the result is written beside the checkout. The job sees only that
  file, through `COMPOSE_FILE` and `COMPOSE_PROJECT_NAME`, so plain
  `docker compose exec -T api ...` works from any folder and reaches only this job.
- **Ports always move**, even when the wanted one is free: to 127.0.0.1, on a port from a
  private range checked for its own protocol (tcp or udp; `sctp` is refused), named by `MULEBOX_PORT_<SERVICE>_<PORT>`. Keeping a free port would pass on a
  quiet day and fail on a busy one. Project code must read the variable.
- **Containers start first**, before `setup`, inside the job's unit, with `up --wait`. Setup
  can then use them, as CI does, and the timeout, cancel and log redaction need no special
  case. The cost: `setup` cannot produce something an image build needs.
- **Teardown is the worker's**, after the unit ends and outside `timeout_min`, by label, on
  every outcome, beside the worker's loop, so a stuck Docker daemon cannot cost another
  job its lease. Containers are not in the unit's control group, so nothing else stops
  them. Pulled images stay; build layers stay in Docker's build cache. A built image gets
  a tag of this job only, and only that tag is removed, by name and without force.
- **Refused, not repaired:** what would reach past the job (see `worker/compose_policy.py`).
  `up` is the first thing a job runs, and environment names that would put project code or
  other files before it are refused (`common/env_rules.py`), on the worker too.
- **The boundary.** That policy stops a CI file's assumptions from reaching past the job. It
  does not contain a hostile project. A job can run any command, including `docker run
  --privileged` in a job line, and Docker access is root-equivalent. Run only projects you
  trust on a build machine.

## Browser tests

Browsers run on the worker, not in a container: that is how a project's own Playwright
setup works, and it reaches `compose:` containers through their loopback ports. A worker
offers `playwright` once a person has installed the system libraries, which takes root, so
mulebox cannot do it. `needs: [playwright]` sets `PLAYWRIGHT_BROWSERS_PATH` to one folder in
the cache root, shared by all jobs, so a version is fetched once. The job asks for its
browser itself, which keeps it matched to the project's lockfile, and mulebox has no list
of browser versions to maintain. mulebox never deletes from that folder.

## Client commands

```text
mulebox doctor               check the project and the machine; uploads nothing
mulebox check [job]          run a job from .mulebox.yml (default: check)
mulebox run -- <cmd...>      run an ad-hoc command (for example one test file)
mulebox queue [--watch]      list running/waiting/recent jobs; full-screen live view
mulebox logs <id>            show a job's log
mulebox cancel <id>          cancel a job
```

While waiting, `check` shows queue position and an estimate; while running, the live log
plus a status line (elapsed time, build machine CPU and memory). Ctrl-C cancels.

Recommended agent rule for each project: run builds, type checks, lint and tests with
`mulebox check` / `mulebox run`; keep only git, search, reading and diffs local.

## Dashboard

- A separate read-only process beside the coordinator: aiohttp, plain HTML and JS, canvas
  graphs. One Server-Sent Events stream for queue changes and metrics, one per open job
  log; both resume by event id after drops. Contract: [interfaces-m2.md](interfaces-m2.md).
- Shows: running and waiting jobs (project, branch, source), live log, history, every
  machine with whether it is online and its free slots, and CPU per core, memory, disk and
  Docker containers for the machine the dashboard runs on.
- Layout: a live monitor in boxes that fills the window, machine load first and the jobs
  list below, one theme over the whole page, and a light or dark switch that is remembered
  per browser. Before a choice it follows the system; the sign-in page always does.
- Low overhead: metrics sampled once and shared (CPU/memory every 2 s, Docker every 5 s,
  disk space every 30 s), bounded buffers, slow viewers dropped rather than slowing jobs.
- Access modes: `local` (bound to 127.0.0.1, opened through an SSH tunnel by
  `mulebox dashboard open`) or `lan`, which keeps that and adds a direct address (password
  login, firewall limited to the configured LAN range). `lan` is plain HTTP by default:
  on a trusted home network a browser warning about a self-signed certificate costs more
  than encryption gives. `lan_tls` turns on HTTPS for networks that need it, and
  `lan_password = false` turns off the password for those who want no sign-in. Never
  internet-facing: `lan_range` must be a private network.
- Logs are redacted before they are stored or streamed, rendered as text, never HTML; no
  environment variables or full container inspect output.

## Multiple machines

- Workers declare capabilities (`slots`, `docker`, `arch`, toolchains) and claim the
  oldest compatible job. No speed scores or weights yet.
- A job whose `needs` no known worker offers is refused at submit, with what to change. A
  queued job whose capable workers are all offline stays queued and says so.
- Add a machine: run the worker setup on it; it registers and warms caches.
- Replace a machine: mark the worker `draining` (finishes current work, takes no new
  jobs), then remove it. Moving the coordinator is a documented manual step.

## GitHub Actions

- Register a repository's runner on every eligible worker with shared labels
  (`self-hosted, Linux, X64, mulebox`); GitHub picks the machine.
- The runner's job-started hook reserves a slot pinned to that worker and blocks until it
  is granted; the job-completed hook releases it. Hooks get their own timeout and the
  worker supervises runner jobs, because a completion hook is skipped on crashes.
- One admission queue shared with agent jobs; no custom GitHub scheduler.

## Safety

- Configured roots per worker (`jobs/`, `cache/`, `runners/`); the path-safety module
  resolves paths, rejects anything outside the roots, mount points and symlink escapes, and
  deletes with directory-descriptor-anchored operations (no check-then-delete race).
- No secrets leave the laptop (excludes above); CI values in configs are throwaway.
- Test databases are per job; jobs must not use existing databases on the machine.
- Container ports of `compose:` projects bind to 127.0.0.1, whatever the compose file says.
- Docker access is root-equivalent: running jobs as the machine's normal user is fine for
  a single trusted owner; a dedicated user is optional hygiene, not isolation. mulebox is not
  a sandbox: its checks stop mistakes and a CI file's assumptions, not a hostile project.
- Docker cleanup removes only what a listing filtered on one job's exact labels returned.
  `prune` and `system` cannot be run through mulebox at all. Containers, networks and
  volumes of the job go; images stay as cache.
- Root-owned files never need sudo: a throwaway container with no network, a read-only root
  file system and only the capabilities `chown` needs takes one job folder, proven by the
  path-safety module to be inside the jobs root, and gives it back. Deleting stays in
  the path-safety module.

## Code layout

```text
mulebox/
  common/       config.py  protocol.py  ssh.py  ids.py  log.py  safepath.py  redact.py
  client/       snapshot.py  submit.py  tui.py  commands.py
  coordinator/  store.py  queue.py  leases.py  recovery.py  api.py  staging.py
  dashboard/    server.py  streams.py  hub.py  events.py  metrics.py  data.py  static/
  worker/       agent.py  workspace.py  executor.py  cleaner.py  docker.py
                docker_cleanup.py  reclaim.py  compose_file.py  compose_job.py  ports.py
                toolchains.py
                runner_hooks.py
  cli.py        single entry point: `mulebox <command>`
tests/          mirrors the package layout
```

Rules: one responsibility per module, shared logic only in `common/`, files under ~300
lines (see [../AGENTS.md](../AGENTS.md)).

## Prior measurements (anonymised)

M4 Pro laptop vs a 2014 4-core/8-thread i7 with 16 GB on 2.4 GHz Wi-Fi, two real projects:

| Workload | Laptop | Old i7 | GitHub-hosted |
| --- | --- | --- | --- |
| Next.js + pnpm gate (lint, types, build, 5k tests) | 60 s | 208 s | 9-10 min job |
| Laravel + Docker + Playwright CI job | ~2.5 min | 4.5 min | ~10 min job |

Single-threaded tools were 2.2-2.6x slower on the old machine; first runs were dominated by
downloads over Wi-Fi, so warm caches matter more than CPU.
