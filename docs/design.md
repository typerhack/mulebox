# mulebox design

Status: implemented up to the open tasks in [phases.md](phases.md). Version: see [../VERSION](../VERSION).

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
   Over 1 MiB, only what changed goes: the client sends a list of file hashes, the coordinator
   compares it with the project's last snapshot and asks for the difference, rebuilds the whole
   snapshot, and queues the job only if the result matches the list. Any trouble sends the whole
   snapshot, so a saving never fails a job. One snapshot per project stays in `<staging>/bases`.
2. **Queue**: one FIFO line. Assignment is atomic: the oldest job a free worker can run.
   Cluster-wide and per-worker slot limits, both default 1 and 2 in the installed `node.toml`.
   Jobs of different branches run at once; a job whose branch is busy waits for it, and younger
   jobs of other branches may pass it (`branch_busy` says so).
3. **Project folder**: the worker fetches and verifies the snapshot, then makes the branch's
   git worktree hold it: `projects/<project>/trees/<branch>/`, one repository per project.
   Only files that differ are written, so timestamps stay and build tools stay incremental.
   Ignored files (`node_modules`, `vendor`, `.venv`, build output) stay, so an install has
   nothing to do; anything else a job left goes, so a job sees what a clean checkout would.
   `setup` is skipped when its text, the toolchain, the env and the lockfiles are unchanged and
   nothing it may have made was lost. A compose job always runs it: its containers are new.
   One job at a time per project and branch; a second one waits, even with a free slot.
   Inputs never change during a job. `jobs/<project>/<job-id>/` holds only the job's own
   scratch files (its log, generated compose file).
4. **Run**: as a transient systemd unit with a runtime limit, `KillMode=control-group`,
   CPU and IO weights. A `compose:` project starts first, in that unit, under a Compose
   project name and labels unique to the job (see Docker Compose projects).
5. **Clean**: stop the unit, remove the job's labelled Docker resources, hand back files
   containers left as root in the project folder, remove the job folder through the path-safety
   module. The slot is free only after cleanup succeeded.
6. **Report**: job id, content fingerprint, base commit, command, toolchain versions, exit
   code, duration, log. If local files changed since submission, the client marks the
   result stale.

## Leases and failure handling

- Client lease: renewed by a client following a job every 20 s, on the coordinator's clock. It
  says a client is there and stops nothing: a job goes on when its client goes away (agent killed,
  laptop asleep, Wi-Fi gone), and its result waits. Ctrl-C and `mulebox cancel` stop a job.
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

## Time limits

No job has a time limit, and a job never stops because nobody is watching it. mulebox asks, and
the agent decides. The rules are in `coordinator/attendance.py`; agents read them in
[agents.md](agents.md), 1a.

- **A check-in is a question.** Every `timeout_min` a running job asks if all is well. The agent
  answers `mulebox ok` or `mulebox cancel`.
- **A job that is working finishes**, answered or not, however long it takes, with its agent gone
  or not. Its result waits for the agent (`coordinator/reuse.py`), so it need not retest.
- **A stuck job stops.** That takes both a question unanswered for one more `timeout_min` and no
  activity of the job's own for that long, or `unattended_idle_min` (15) if that is shorter. It shows `stopped: stuck`, exit 76, which never
  reads as a failed check.
- **Not knowing is not idle.** A job that cannot be measured stops only after
  `unattended_max_hours`, with its question unanswered, so nothing holds a slot for ever.
- **A queued job is never stopped.**
- **mulebox cannot interrupt an agent.** A question reaches it through `events`, or at its next
  command in the project. That is why the answer window is long and a working job does not need
  an answer at all.
- GitHub runner reservations are outside all this: GitHub owns those jobs.
- The limits are `[limits]` in the coordinator's `node.toml`. The service writes them to `meta`
  when it starts, so `mulebox rpc` processes and the read-only dashboard share them.

Until 0.55.0 a job was stopped for having nobody watching it: `unattended`, with limits of 15
minutes and 24 hours. Real use showed that wasted working jobs, so it went.

## Results an agent need not repeat

A job is the same job when the project, the job's name, the exact files, uncommitted changes
included (`fingerprint`), and argv, setup, toolchain and env are the same. `mulebox check` on the
same job gets the result of the last 24 hours (a failure only from the mulebox running now), or joins it if it is queued or running, and `--again`
forces a run. Only a job that really ran counts. A finished job whose result reached nobody is
told once, at the project's next command (`jobs.told_at`).

## Agent contract

`mulebox contract` tells an agent how a project builds, tests and uses git through mulebox.
It is generated from `.mulebox.yml` and from the tables the code itself uses, so there is
no file to keep in step, and it needs no network, so its rules are readable when the build
machine is down. Text by default; `--json` has stable keys and a `schema` number, raised
when a key is removed or changes meaning, and when the skill has to teach something new.
Exit 0 outside a project; a broken `.mulebox.yml` exits 2 rather than hiding the mistake.

The skill ships in the package and says which schema it was written for, so an agent can
tell the user that its copy is behind; `mulebox skill update` is for that person to run.

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
- **The machine's `job_env` goes into services.** What a machine needs (a timeout for a slow
  network, say) is needed where installs run, and that is often a container. It is added to
  the generated file; a service's own value wins, so it cannot change what a project set.
- **Containers start first**, before `setup`, inside the job's unit, with `up --wait`. Setup
  can then use them, as CI does, and the timeout, cancel and log redaction need no special
  case. The cost: `setup` cannot produce something an image build needs.
- **Teardown is the worker's**, after the unit ends, by label, on
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
of browser versions to maintain. mulebox never deletes from that folder, and it turns off
Playwright's own cleanup there (`PLAYWRIGHT_SKIP_BROWSER_GC`): that removes any browser whose
project folder is gone, and a job's checkout always is, so each job deleted the last one's
browsers. Versions therefore add up until a person removes them. A download that drops still
restarts from zero, up to 5 times: Playwright does not resume, so a slow link can lose a whole
job to it, but only until one job has fetched that version.

## Job stages

A job's log says what happened, but not what took the time, and the first real jobs needed
that answer: 18 minutes on images, then two installs. The worker records one row per stage in
the coordinator's store; a log stays a file. The stages of the script are marked in its own
output, which keeps them in order with what they printed, needs no trap a project could
replace, and adds no process. `environment` is a stage of its own for what mulebox provides,
apart from a project's `setup` and commands: the direction is that a job declares what it
needs and mulebox prepares it. A report never holds up a job, and its rows are not a
source of truth for how a job ended. That stays `outcome` on the job.

The rows also give what is usual for a project and job: the median of its last passed runs, leaving
out any that lost a connection while fetching images or packages,
per stage and as a whole. mulebox says what past runs took and leaves it there. A percentage
would be a guess presented as a measurement, since a cold cache or a new image changes
what a stage takes.

`install` is the stage for what fills a project's folder. It is the one part of a compose job that
can be reused, as what it makes outlives the job's containers, so it has its own state beside
`setup`'s and depends on the compose files too. `setup` keeps running in every compose job, since
it may load a database into containers that are new each time. An `install` that fails counts as a
job that never ran, exit 5: an agent should not go looking for a bug in code that did not run.
It stays inside the job and its slot. Moving it outside would run more work than the machine's
`slots` allow, with a job's containers already up.

## Project folders

Everything lives at `<projects>/<project>/`: `repo.git`, `trees/<branch>-<hash>/` and
`state/`. `mulebox projects` shows each folder and its size. All of it can be made again by a
job, so removing it costs time, not data.

- `mulebox project clean` removes branch folders with no job for 14 days (`--days`), keeping each
  project's newest.
- `mulebox project reset <project>` removes the whole folder and the project's last snapshot, or
  one branch's with `--branch`, and the package caches with `--caches`. Use it when a job only
  fails or only passes because of what an earlier job left in an ignored folder.
- Both only list what would go until `--yes`. A project with a job on a machine is refused. While
  a folder goes the project is held (`coordinator/holds.py`, a row in `meta` that `claim` reads in
  its own transaction), so no job can start in it; a hold ends by itself after 15 minutes.
- They run on the coordinator's machine, the only one with workers until M5.

## Package caches

A new project folder, a lockfile change or a compose job's fresh containers still mean an
install, and on a slow network that is most of a job's time, and a project's `external` cache volume cannot be used because it would cross jobs and projects. A
project can ask for a cache with `needs: [cache-pnpm]` or `cache-composer`: one folder per
project and tool, `<cache>/packages/<project>/<tool>`.

- **Opt-in**, because sharing changes what a job can affect, and only a project's owner can
  weigh that for it.
- **Per project, not per machine.** Sharing across projects would save more disk and more
  downloads, but a folder that every project reads is where a mistake in one reaches the
  rest. The price is a copy of a package per project.
- **`needs`, not a new field.** A worker reports the names by itself, so an older worker
  cannot claim such a job and silently run it without a cache, and no client or wire change
  is needed.
- **The project mounts it.** mulebox does not add mounts to services: only the project knows
  which service installs and where. The policy lets a writable bind through only if it
  resolves into a folder of this job's caches; external volumes stay refused.
- **The job's log names each cache it used**, and `mulebox cache clear` on the machine is the
  way out. Nothing evicts: there is no safe guess at what is stale, and mulebox never deletes
  what it was not asked to.
- `packages/` holds downloads only. A later install step run by mulebox, keyed on lockfile,
  toolchain and image, would keep its results in a folder of its own beside it, read
  downloads from here, and leave this layout as it is.

## Client commands

```text
mulebox doctor               check the project, the machine and the skill; uploads nothing
mulebox check [job]          run a job from .mulebox.yml (default: check)
mulebox check --detach       the same, left running; prints the job id
mulebox events --job <id>    a job's state changes as lines, no log; --json for tools
mulebox status <id>          one job's current state
mulebox wait <id>            the result of a job, as `check` would have given it
mulebox run -- <cmd...>      run an ad-hoc command (for example one test file)
mulebox queue [--watch]      list running/waiting/recent jobs; full-screen live view
mulebox logs <id>            show a job's log
mulebox cancel <id>          cancel a job
```

While waiting, `check` shows its queue position and, once a job has passed at least 3 times,
how long it usually runs, labelled as an estimate (the median of its last 20 passed runs with
the same command, from the same stage rows as `usual`). That is not the time in line: nothing here knows how long the jobs ahead
will take. At position 2 or later, or for a job that usually takes 5 minutes or more, it
suggests `--detach`. While running, the live log. Ctrl-C cancels.

Recommended agent rule for each project: run builds, type checks, lint and tests with
`mulebox check` / `mulebox run`; keep only git, search, reading and diffs local.

## Dashboard

- A separate read-only process beside the coordinator (the optional cancel button is the one
  exception, and its write goes through `mulebox rpc`): aiohttp, plain HTML and JS, canvas
  graphs. One Server-Sent Events stream for queue changes and metrics, one per open job
  log; both resume by event id after drops. Contract: [interfaces-m2.md](interfaces-m2.md).
- Shows: every machine with whether it is online, its free slots, capabilities, what it
  runs and a small CPU and memory reading (only where measured: today the dashboard's own
  machine, the rest say so until workers report, M5.3); the queue by machine (one lane per
  machine with what runs and what waits for it; jobs several machines could take in one
  shared list, jobs no machine fits marked stuck), failed, passed and recent jobs behind
  tabs, live log, history, and CPU per core, memory, disk and Docker containers for the
  machine the dashboard runs on.
- Layout: a live monitor in boxes that fills the window, machine load first and the jobs
  box below, one theme over the whole page, and a system, light or dark switch remembered
  per browser. System is the default; the sign-in page always follows the system.
- Honest about the queue: a waiting job is not assigned until a worker claims it, so the
  lanes only ever say where a job can go, never where it will.
- What a running job does, on its card: its stage in words (a CI job's GitHub step) and a meter
  of the cores the job alone uses, which pulses only at half a core or more, so the busy job
  stands out. An agent job is read from its unit and containers, a CI job from its runner's
  service (containers a workflow starts itself are not counted). Downloads are told by the stage
  only: per-job network is not measured.
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
  environment variables or full container inspect output. A job's `setup` line is redacted the
  same way before the dashboard shows it, as the command is.
- Cancelling from the page is optional and off by default. It exists only for someone signed in
  on the `lan` address: stopping another person's job is the one thing here that needs to know
  somebody asked, and the tunnel and a passwordless `lan` cannot tell. Where the button does not
  exist, `mulebox cancel` still does. It sends what `mulebox cancel` sends, by the same `mulebox
  rpc`, so a job cancelled from the page ends like any other, and the dashboard process never
  holds a writable store. Protection against other pages: interfaces-m2.md, Cancel button.

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
- A reservation's log is the runner job's steps as they start and each step's output once the
  runner writes it to its own files (in 4 KB blocks or at the step's end), read, never changed, by
  the worker. The last step's output can come up to a minute after the slot is released.
  GitHub keeps the whole log and the result.

## Safety

- Configured roots per worker (`jobs/`, `projects/`, `cache/`, `runners/`); the path-safety module
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
- A package cache is written by one job and read by the next, so it is a channel between
  jobs of one project, on purpose and only if the project asks. It is not one between
  projects: each has its own folder, and compose may mount only its own (see Package caches).
- Log retention removes a finished job's log file through the path-safety module, from the
  logs folder only, and only for a name it found in the job table.
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
  worker/       agent.py  project_home.py  workspace.py  executor.py  cleaner.py  docker.py
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
