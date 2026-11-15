# mulebox design

Status: implemented up to the open tasks in [phases.md](phases.md). Version: see [../VERSION](../VERSION).

## Problem

AI coding agents work in many git worktrees at once. Each runs builds, type checks, lint
and test suites on the dev machine it lives on. Several at once overheat the dev machine, stall video
and the browser, and can crash applications. Hosted CI is slow and has minute quotas.
Most people have, or can cheaply get, an idle Linux machine on the same network.

## Goals

- Agents keep editing locally; every heavy job runs on nodes on the LAN.
- One queue for all projects and all sources (agents, the user, GitHub Actions).
- Results identical in meaning to running locally: same command, exit code, output.
- Safe by default: jobs never touch anything outside mulebox's own folders.
- Easy to grow: add or replace nodes without changing agents or projects.
- Simple to operate for one person; no cloud services, no inbound internet access.

Non-goals (for now): multi-tenant use, internet-facing access, automatic failover,
scheduling by machine speed or job weight, an MCP server (a thin wrapper may come later).

## Roles

| Role | Runs on | Does |
| --- | --- | --- |
| client | the dev machine | `mulebox check`, `mulebox queue`, terminal live view, snapshot upload |
| coordinator | one always-on machine | queue, leases, history, staging of inputs, web dashboard |
| worker | each node | claims jobs, prepares workspaces, runs and supervises jobs, cleanup |

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
2. **Queue**: one line, oldest first unless the owner set order rules (Order of the line,
   below). Assignment is atomic: the first job in line a free worker can run. The owner can steer it (`mulebox pause|resume|first|up|down|last|boost|normal`, or the
   dashboard): a waiting job moves to the front, one place up or down, or to the end (only the moved
   job is pinned, next to another job's place; Order of the line), a paused one keeps its place and does not start,
   and a machine running a `boost`ed job takes no new one (coordinator/job_control.py). A whole
   project can be paused for a while (`mulebox project pause`, coordinator/project_pause.py), and
   an upgrade can wait in the line like a job (`mulebox setup <machine> --queued`,
   coordinator/upgrades.py): nothing behind it starts on its machine until it has installed.
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
  dev machine asleep, Wi-Fi gone), and its result waits. Ctrl-C and `mulebox cancel` stop a job.
- Worker lease: renewed by the worker while it executes; separate from the client lease.
- Idempotent submit (client-chosen key): a lost reply never creates a duplicate job.
- Restart: the coordinator reconciles stored jobs; the worker, before it claims anything,
  stops orphan units and removes leftover job folders and Docker resources found by label.
  Interrupted jobs are marked, never replayed automatically.
- Coordinator down: no new submissions or assignments; running jobs continue until their
  worker lease expires, then stop and clean. A job is never reassigned just because its
  worker vanished.
- Client disconnected after submit: the outcome is "unknown"; reconnect by job id.
- Node unreachable: the client fails fast with a clear message and never falls
  back to running locally on its own.

## Order of the line (M23.3, M24.4, 2026-11-13)

The user asked for settings that order the line beside moving jobs by hand. One line stays: agent
jobs, GitHub runs' slots and waiting upgrades, in one order (`coordinator/line.py`), which
`queue.claim`, a GitHub run's grant, an upgrade's turn, positions and moves all read.

**Precedence.** Each step only breaks the ties of the one before:

1. **Moves by hand** (`mulebox first|up|down|last`, the dashboard's arrows) pin only the moved
   row; see below.
2. **Levels from the rules**, higher first, added up per row:
   - `projects`: a level per project, -3 to 3 (low -1, normal 0, high 1), for agent jobs and a
     repository's GitHub runs alike (`owner__repo` is a project name).
   - `branches`: a level per branch name or pattern (`main`, `release/*`). The exact name wins,
     else the longest pattern that matches.
   - `github`: a level for every GitHub run's slot against agent jobs.
   - `workflows`: a level per GitHub workflow, by its `name:` exactly as GitHub gives it in
     `GITHUB_WORKFLOW` (such as `CI` or `Nightly build`). The runner's job-started hook sends it with
     `reserve`, and the slot keeps it (`jobs.workflow`, schema 22). A run from a hook older than
     1.17.1 has none and takes no workflow level.
   - `aging_min` (default 30): every that many minutes in line add one level, so a low project
     or a long job is never held back for good. An upgrade takes aging only.
3. **Fair turns** (`fair_turns`, off by default): among rows of one level, the k-th waiting row
   of a project gets turn k plus what that project already runs, and turns go first. So one
   project's burst of ten jobs does not hold back another project's single job, and a project with
   two jobs running waits behind one with none. Of rows on the same turn, the project that last
   started a job longer ago goes first, one that never started any first of all: when a burst's
   job ends its project runs nothing for a moment, and arrival alone gave it back the slot it had
   just left, each time (seen on the node, 2026-11-14).
4. **Shortest first** (`shortest_first`, off by default): among rows of one level and turn, the
   one whose `usual` length (usual.py: an agent job's median passed run, a GitHub run's median
   held slot) is shorter goes first. A row with no history counts as the line's average, the
   median of the known lengths of the rows in line; with none known, arrival decides. It comes
   after fair turns, so short jobs of one project cannot take every turn.
5. **Arrival**: `queued_at`, then `seq`. (A row moved by hand before 1.17.1 may still carry a
   `priority`, which goes first, higher first, as it did then; nothing writes one any more, and a
   move leaves it, so a row others are pinned to keeps its place.)

**The user's decisions (2026-11-13).** Aging is 30 minutes by default and only counts once another
rule is on (as built in 1.17.0). A move by hand pins only the moved job, so a later rule change
still applies to the rest (1.17.0 wrote the whole visible order into every waiting job, which froze
the line). Under shortest first a job with no past runs counts as the line's median, not after the
known jobs. A workflow rule is wanted, so the hook sends the workflow's name.

**Moves pin one row.** A move puts the row in the gap it asks for and pins it there, in the moved
row only (`pin_side`, `pin_job`, `pin_order`; coordinator/line_moves.py):

- `first`: `front`, ahead of everything the rules order, the latest such move first.
- `up`, `down`, `last`: `before` the row right after the gap, or, at the end of the line, `after`
  the row right before it. If that neighbour is pinned itself, the moved row joins it at the same
  place, just ahead of or behind it (`pin_order`). Between two rows of one place it takes the
  middle of their `pin_order`s; when floating point has none left (about 50 moves back and forth
  in one place), the rows of that place are numbered 0, 1, 2 again in the same write.

A pin is to the other row's place by the rules, not to wherever that row is shown: the line is
built from the rows nobody moved, in the rules' order, with each pinned row set just ahead of or
behind the place of its row. When that row is moved too, or has left the line (it started, or was
cancelled), its place by the rules still holds and the pinned row stays in it; a pin to a row no
longer in the store is dropped and the row goes by the rules again. So in a first-come line `up`
passes one job and stays ahead of it, `down` lets one pass, `last` goes behind the last row and
ahead of jobs sent later, and when the row it went behind starts first it simply keeps that place.
A GitHub run's slot and a waiting upgrade move the same way; a queued upgrade is pinned `front`
unless sent with `--behind`, and `boost` on a waiting job pins it `front` too.

**Defaults keep today's line exactly.** With no project, branch, GitHub or workflow level, fair
turns and shortest first off, and no row moved, `line.read` takes the SQL order of arrival
(`priority DESC, queued_at, seq`), as the line was before. Aging alone cannot change that order (an
older row has always waited longer), so its default of 30 minutes only counts once another rule is
on. A test holds the two equal for mixed lines.

**Cost.** `queue.claim` reads the line inside its `BEGIN IMMEDIATE`, so the read must not grow with
the history. It takes a fixed number of queries however long the line is: the queued rows, the
rules, the rows that left the line but still hold a pinned row's place, what each project runs, and
the usual lengths of every row at once (`usual.lengths`, one query per kind, each row still counting
only the runs before it). That query looks up each project, job, command and place in time once,
and each lookup walks the history index back from its place and stops at the 20 runs it counts, so
a project with 1000 passed runs costs what one with 20 does (1.17.1 read them all). 1.17.0 asked the history once per row; 6000 waiting jobs took 4.4 s
inside the claim, holding back every other write. One request reads the line once and hands it on,
to the waiting reasons and the upgrade checks too.

**Where the settings live.** In the coordinator's store, `meta` key `line_rules`, one JSON value
like the project pauses and holds, read in the same `BEGIN IMMEDIATE` transaction that starts a job,
so the claim stays atomic. A move's pin is in the moved row's own columns. Set by the owner from any
dev machine (`mulebox queue rules`, `mulebox project priority <project> <level>`) or from the
dashboard, both sending `queue_rules`. Never in a project's `.mulebox.yml`: a project must not be
able to raise itself above the others, and an agent can edit that file.

**On the dashboard (M14.15).** Every waiting line's heading has an Order button; its panel lists
the rules in the order of precedence above, with their switches, and the levels (High, Normal, Low;
another stored number is shown as it is). The page edits a copy and sends only what differs on Save
(`web/src/lib/order.ts`, `changeOf`); Reset sends `{reset: true}` after asking twice. A waiting row
shows a short reason built from `order` (`placeOf`), with `place_reason` in full as its tooltip and
on the job's page. With the controls off the panel is read-only.

**Every project keeps its level row (the user, 2026-11-13).** The node never forgets a project: one
last used two years ago can still be given a level. The panel only says which are in use. Projects
with a job or a GitHub run in the last seven days (or one waiting now) come first, under "Active in
the last 7 days", by name, each with its runs and how long ago the last one was; the rest follow
under "Other projects", the latest run first, with the day of that run, and one with a level that
never sent a job last. Every one of the rest is always shown, with no button to open more (the
user's call, 2026-11-13), so no project and no set level is ever out of sight. Both groups are one list, so a project whose use changes while the panel is open keeps its
row, and the focus stays on its choice. A project with a job waiting has a row even before the
rules are read again. The facts come with the rules (`project_activity`, `line_rules.project_activity`): one pass
over the job history per read, 7 ms on 20000 jobs.

**Explainable.** While any rule is on, every waiting row says why it is where it is: `place_reason`
(such as `project example-app +1; waited 30m or more +1; turn 2 of example-app; then by arrival`)
and `order` (`by_hand`, `level`, `levels` with the rule each came from, `turn`, `usual_s`,
`counted_as_s` for a row with no usual length, and `moved` for a pinned row), in `status`, `queue`
and the dashboard, beside `waiting_for` and `running_ahead`, which still say why a job has not
started. A moved row says so with no rule on too (`moved to the front by hand`, `moved by hand, just
ahead of <job>`, or `... which has left the line, so in its place`). Aging is said in whole steps,
not minutes, so a reason changes only when the order behind it can: the dashboard redraws on a
changed reason, not every minute. With every rule at its default and nothing moved there is nothing
to say beyond arrival, and the fields are absent.

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

## A job that looks stuck (M24.8, agreed 2026-11-15)

Time limits stop a stuck job only after a question has gone unanswered for a `timeout_min`, so at
the earliest an hour in with the default. Until then an agent that follows a hung job sees nothing
wrong, waits, or gives up and runs it again. This tells it early, and tells the owner on the
dashboard. It is a judgement with its evidence, and stops nothing: the rules above are unchanged.

- **Evidence, not a timer** (the user's ask). A job is judged on everything mulebox can see of it:
  its output, its own CPU, the bytes its own processes read and write (`/proc/<pid>/io`, so a
  download at a few KB/s and near-zero CPU still counts as working), its services' CPU and traffic,
  and what its log says: download progress (common/download_watch.py) and the last lines.
- **What it says.** One verdict per running job, with what it is based on:
  - `working`: something moved in the last `stuck_after_min` (2). Nothing is shown.
  - `slow`: the only thing that moved is I/O or a download, below 50 KB/s for that long. A
    warning, not a stuck job: "downloading slowly, 12 KB/s, 41 MB of 300 MB".
  - `waiting`: nothing moved, and its last line says it waits on purpose (a retry with a delay,
    "waiting for", a sleep). Said as it is, with the line.
  - `asking`: nothing moved, and its last line reads as a question for input (`[y/N]`,
    `Password:`, `Press any key`). Jobs get no input, so it will not go on: stuck, with the line.
  - `stuck`: nothing moved and the log gives no reason. With how long, the stage and the last line.
- **Not knowing is not stuck.** A job whose activity cannot be read (the `images` stage, its
  containers not known yet) is never `stuck`, nor is a paused, queued or cancelled one, or a
  GitHub run. On a Mac node a job's own I/O is not read (no per-process counters there), so only
  CPU, services, output and the log count, as the hint says.
- **Once per spell.** A verdict is told when it starts, and `working` again when the job moves, so
  an agent can go back to waiting.
- **Where.** `mulebox status` shows the verdict, its evidence, and the two ways on: `mulebox logs
  <id>` to look, `mulebox cancel <id>` to stop it. `mulebox events` gets a `stuck` event (`verdict`,
  `text`, `stage`, `last_line`, `limit_s`, and `since` and `quiet_s` when nothing moved) and `moving`. `wait` and an attached `check`
  print the same line on stderr, once per spell. The contract and the skill say what to do: read
  the last lines, then cancel or keep waiting, and never send the same job again while it runs.
  The dashboard shows it as a line across the running card's foot (icon, short label, its one
  figure), which opens to the sentence, the log and Cancel, and as a strip on the job's page:
  option B of design-system/stuck/, the user's pick.
- **How fast.** The worker samples every 10 s and reports with every heartbeat (3 s), so a
  verdict comes within about 15 s after the limit.
- **The limit.** `stuck_after_min` in `[limits]` of the coordinator's node.toml, written to `meta`
  like the others. A project whose jobs are quiet for long on purpose sets `stuck_after_min:` in
  `.mulebox.yml`, per job or for all; it can raise the node's limit, never lower it.
- **Blind spot.** A `docker run` or `docker build` the job starts itself has no mulebox label, so
  only its output and the `docker` client's own I/O count (worker/job_meter.py); a long silent
  build of its own can read as `stuck`. The verdict shows its evidence, so an agent can tell.

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
  to its user and posts only with their approval. `post` is off until `feedback_repo` is set, and for
  the projects listed in `feedback_off`.
- **Enough to trace.** A draft holds the summary, the mulebox version, the operating system
  and, for every job id given, the id, its result, stages and the mulebox that ran it, plus log
  lines picked by pattern or from the end when asked. Job ids identify nobody and are how the
  people running mulebox look a job up. Never a project, branch or machine name.
- **Scrubbed.** Secrets, then every name known locally and from the coordinator, including
  other projects' (also inside longer words such as an env name), then home folders, email and
  IP addresses, user@host targets and links (`common/anonymize.py`). Kept, as they identify
  nobody: loopback addresses, links to public package registries and toolchain sites, and
  `package@version`. Private code and business text cannot be recognised: the procedure
  (`mulebox feedback guide`, client/feedback_guide.py) has the agent read the draft for them.
- **Checked again.** `post` refuses a file the scrub would still change, so what was
  reviewed is what is sent, and details added by hand are caught when they match a rule. The
  refusal names each line and the kind of thing found, never the value.
- **One skill.** The procedure is printed by the CLI, not a second skill: the `mulebox` skill
  is already loaded when something goes wrong, and the guide cannot fall behind the tool.
- **Logs on request only.** The scrub cannot recognise a private file name or line of code
  it has no name for, so `--log` is a choice, and reading the draft is a real step.
- **No screenshots.** They cannot be scrubbed, and `gh issue create` cannot attach them.

## Results on GitHub (M24.6, 2026-11-12)

A pass on a node counts on GitHub too, as a commit status, so a pull request shows it and branch
protection can require it. Opt-in per project, `github_status: true` in `.mulebox.yml`
(`client/github_status.py`):
- **Only on a pushed commit, exactly.** Before the job is sent, the dev machine checks that the
  worktree is clean (no change, no untracked file) and that a remote-tracking branch holds HEAD. Then
  the files the node gets are that commit's, so a status on it tells the truth; anything else posts
  nothing and says why. Settled before sending, as files can change while the job runs.
- **From the dev machine, not the node.** Its own `gh` posts `repos/{owner}/{repo}/statuses/<sha>`
  after the job ends, so the node holds no GitHub token and nothing reaches in to it.
- **One status per job**, context `mulebox/<job>`: `success` on exit 0, `error` when the job gave no
  verdict (could not start, cancelled, interrupted, stopped, mulebox's own errors), else `failure`.
  A result given back for the same files (Results an agent need not repeat) is posted the same way.
- **Not with `--detach`**: nothing is left on the dev machine to post at the end. Posting from a later
  `mulebox wait` was left out for now: `wait` does not know the commit.
- A commit status, not a check run: check runs can only be made by a GitHub App, which mulebox
  does not have. Who set the status is the account `gh` is signed in as.

## Projects

There is no project registry. What a project needs lives in its `.mulebox.yml`, and which
projects exist is already in the job history, so a registry would be a second copy of both.
`mulebox projects` lists what the coordinator has seen, worked out from its jobs. The cost:
a project appears only after its first job, and nothing can be stored about one. Add a
table only when real adoption shows something that belongs in neither place.

## Job minutes

`mulebox stats` and the dashboard's Statistics page (`/api/stats`) answer how long jobs ran, from
one module, `coordinator/stats.py`, so the two never disagree. The measure is wall time on a
machine, added up: two jobs side by side for ten minutes count twenty. It is not CPU time and
not time saved. Agent jobs count from their start to the end of their command, GitHub runs
from the slot granted to its release; upgrades are not jobs. A run still going counts to now
and is also given apart, a run that ended with no length (most often interrupted) is counted
as unknown, never as zero, and frozen time is in it, as the store keeps that a job is paused,
not when. A run is cut at a range's edges, so a job across midnight counts on both days. The
caller sends the ranges in epoch seconds: only it knows its own midnight and summer time.
Filters and breakdowns: project, job, source (`client`: a dev machine or `github`), machine and
kind. Job rows are kept for ever, so the totals since the first job stay exact.

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
Xcode is pinned the same way (`xcode: "16.2"`), on a Mac node only, but never installed by a job:
the worker reports the Xcodes it has, and the job gets the pinned one's `DEVELOPER_DIR`
(worker/xcode.py). A simulator runtime is found the same way (`simulator: "iOS 18.2"`), and a job
that asks for one gets a simulator of its own (worker/simulator.py): its script makes it, so a
slow CoreSimulator holds up that job only and a cancel stops it; the cleanup removes it by its name
on every outcome, as it tears down a compose job's containers, and a worker that starts removes
any an earlier one left. Only simulators named `mulebox-job-...` are ever removed, through `simctl`,
as the device set is the user's own, shared with Xcode.

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
  trust on a node.

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
`state/`. `mulebox projects` shows each folder and its size, counted as `du` counts it (a file
hard-linked into several `node_modules`, as pnpm does, once; one walk of the folder). All of
it can be made again by a job, so removing it costs time, not data.

- `mulebox project clean` removes branch folders with no job for 14 days (`--days`), keeping each
  project's newest.
- `mulebox project reset <project>` removes the whole folder and the project's last snapshot, or
  one branch's with `--branch`, and the package caches with `--caches`. Use it when a job only
  fails or only passes because of what an earlier job left in an ignored folder.
- Both only list what would go until `--yes`, and both reach every online node: the dev machine
  asks the coordinator (`project_order`), which keeps one order per online node
  (`coordinator/project_orders.py`, table `project_orders`, schema 24). Each worker gets its
  orders with its next claim or heartbeat reply, runs them in a thread of its own
  (`worker/orders.py`, the removal itself in `worker/project_work.py`) and answers `order_done`
  with what it printed; the dev machine prints each node's answer under its name. A node that
  is offline is named and keeps its folders; one that gave no answer in 5 minutes counts as
  lost (it may run a mulebox older than 1.22.0), and the command then exits 1. A coordinator
  older than 1.22.0 does not know the request, and the old path runs on its own machine only.
- `reset --yes` holds the project (`coordinator/holds.py`, a row in `meta` that `claim` reads in
  its own transaction) on every node until each answered: refused while one of its jobs runs
  anywhere, and no job of it starts meanwhile; a hold ends by itself after 15 minutes. With the
  last answer the coordinator's last snapshot of the project goes too.
- `clean` takes no hold: a node skips the branch folders it runs a job in now, and claims no
  job while an order runs. The branch history it needs goes in the order.

### Disk use and cleanup on its own (the user's decisions, 2026-11-14)

Found on the real node: 63 GB in 144 branch folders after 10 days, as every pull request and test
branch keeps a whole folder with its installed dependencies and nothing removed them until
someone ran `project clean`. So each node now keeps its own disk in check, and the user sets how
(a node setting each, Node settings below; changed from afar like `slots`):

| Setting in node.toml | Default | Meaning |
| --- | --- | --- |
| `keep_free` | `"10%"` | the disk floor: free space mulebox leaves on the disk of its folders, a share of it (1 to 90%) or a size (`"50GB"`); it counts only when the disk is nearly full for another reason |
| `unused_days` | 7 | a branch folder with no job for this long is removed on its own |
| `keep_latest` | true | each project's latest folder stays however old, so the next job after a break is still quick |
| `slim_hours` | 12 | a branch folder with no job for this long loses what git ignores in it (installed packages, build output), its files stay; 0 never (1.29.0) |
| `idle_days` | 14 | a project with no job for this long gets a suggestion to clean its latest folder, never a removal |
| `auto_clean` | true | the sweep removes on its own; off, it only says what would go, and removes when the user runs it (`mulebox storage clean`, the dashboard's Run now) |
| `docker_clean` | true | Docker's unused build cache, dangling images and the images mulebox's jobs pulled and no job used since go too (below) |
| `max_size` | `"20GB"` | space for mulebox: the most it may hold on the node, everything it keeps; past it the oldest folders are slimmed, then the oldest that may go removed, never a running, kept or latest one; from 80% of it every command from a project tells the agent to ask its user for more; `"off"` for no limit and no warning (1.30.0; `"off"` before) |

- **Last use** of a folder is the time of its last job on this node: every job commits in its
  folder, so git's log of the folder's branch (`repo.git/logs/refs/heads/tree-<folder>`) has it,
  for folders from before this too. Per node, not the coordinator's history, as a branch run
  lately on another node may have sat unused here.
- **Gone branches** (1.26.0, the user's ask: most folders were of branches merged and deleted
  long before 7 days passed): every job carries the dev machine's own branches (`refs/heads`,
  not remote-tracking names, which outlive a branch deleted on GitHub until pruned); the
  coordinator keeps the newest list per project and dev machine (`project_branches`, schema 26)
  and sends each node the branches no dev machine has any more (`storage_gone`). A branch is
  gone only when every dev machine that ran a job on it has sent a list since that job and no
  recent list has it, so a dev machine on an older mulebox, which sends none, never has its
  branches judged. Its folders go at the next sweep, latest or not; the latest mark moves to the
  newest folder of a live branch.
- **The sweep** runs on each worker (`worker/storage_sweep.py`, the rules in
  `worker/storage_rules.py`): a minute after the worker starts, then an hour after the last, and
  within a minute when free space falls under `keep_free` (at most every 10 minutes for that). It removes branch folders unused for `unused_days` through the same removal
  as `project clean` (`project_disk.py`, safepath), and never: a folder a job runs in now, a
  project's latest with `keep_latest`, or anything the user marked to keep. The node claims no
  job while it removes, as with a project order.
- **Keep marks**: `mulebox project keep <project> [--branch <b>]` (`--off` to drop it), on the
  dashboard too. Kept on the coordinator (`storage_keeps`, schema 25) and sent to every worker
  with each claim or heartbeat reply, so they hold on every node.
- **When that is not enough**, free space under `keep_free` after the sweep, mulebox removes no
  more on its own: the node reports what it could remove next and how much that frees (latest
  and kept folders, oldest first), the dashboard shows it, and the user decides. Idle projects
  are shown the same way, as a suggestion.
- **What mulebox holds** on each node: the worker measures its folders in the sweep's own thread,
  each sweep (one walk over all of them, a file hard-linked in
  several counted once; never on a page load), with the disk's size and free space, and sends
  it with its next claim or heartbeat: per project its branch folders (size, last job, and what
  will happen to each), its package caches, toolchains and browsers, GitHub runners, logs and
  snapshots, Docker's own totals (`docker system df`), and where each part is on the node (`paths`, for the dashboard's "copy path"). The coordinator keeps the last report
  per node (`workers.storage`) for `mulebox storage` and the dashboard's `/api/storage`.
- **Slim folders** (1.29.0, the user's ask, M25.9: most of a folder is what its jobs installed
  and built, 277 MB of a 364 MB folder of one project, `.next` 27 GB of another's 35 GB, and most
  branches get no job again): a folder with no job for `slim_hours` (12; 0 never) loses what git
  ignores in it (`git ls-files --others --ignored --directory`), through safepath, and keeps the
  checkout and its git history (`worker/slim.py`). Never the latest, a kept or a running folder,
  and only a `stays` one: a folder that goes anyway is removed, not slimmed. Slimming forgets the
  folder's `setup` and `install`, so its next job runs them again, and leaves a mark,
  `state/<folder>.slim`, which that job's `prepare` takes away. Before it runs, the report says
  what it frees (`frees`): the bytes of files whose every hard link is inside what goes
  (`common/tree_size.freed`), so a pnpm `node_modules`, linked from its store, counts as little.
  The cost: a branch's next job after a day installs again from the package caches, and a build
  starts without its own cache (`.next/cache`).
- **What goes now is said as it is** (1.28.0, the user's ask: the page said 6.5 GB would go
  within a day while a cleanup would have removed 17 GB of gone branches, as the branch list had
  come after the last measurement): between sweeps the worker makes the plan again on its last
  measurement when the gone branches or keep marks change, and every 15 minutes (last jobs
  and free space read again; a folder made or used by a job since is measured alone, the rest
  keep their measured size), and sends the new report. It carries
  `measured_at` and `next_sweep`, and the dashboard and `mulebox storage` say "Run now removes N
  branch folders, X GB; the next cleanup does in M minutes".
- **Docker** (1.26.0, `docker_clean`): a job's own images, containers, networks and volumes go
  with its cleanup already. The sweep also removes build cache unused for `unused_days` (`builder
  prune --filter until=`, which goes by the cache's last use) and dangling images older than
  that. On the containerd image store an image's age counts from when the node stored it, not
  from its `Created` date, which a build with cached steps keeps from its first build; a CI step
  that runs `docker build` with no tag leaves one such image per run, its layers shared, so they
  take little room and go once a week old. Docker keeps no time of last use for an image, and between jobs every base image a
  project pulls is "unused" by Docker's count, so the worker notes the images each compose job's
  services pull when it starts (`worker/image_use.py`); an image no job used for `unused_days`,
  and no container uses, is removed by name (`worker/docker_prune.py`). An image mulebox never
  noted is the owner's and stays; volumes stay; `image prune --all` and `system prune` stay
  refused in `worker/docker.py`.
- **History**: each sweep's record, why it ran (`start`, `hourly`, `low`, `now`), the folders it
  removed with the reason (`gone`, `unused`, `size`), what Docker freed, free space before and
  after and any error, goes with the report and is kept per node (`storage_sweeps`, the newest
  1000), for `mulebox storage --history` and the dashboard, so a cleanup that does the wrong
  thing can be seen and fixed.
- **Space for mulebox** (1.30.0, the user's call: three settings, the free space to keep, a size
  limit and a warning size, were one idea): `max_size` is the one limit, 20 GB by default, and
  `keep_free` the disk's floor beside it, in one panel. From 80% of `max_size` (`WARN_SHARE`)
  every command from a project adds a notice for the agent to ask its user for more space
  (`heavy_nodes`, client/attention.py); past it the sweep trims, slimming the oldest folders first
  and removing only when that is not enough. `warn_size`, a setting from 1.26 to 1.29, is gone:
  a node.toml that has it still reads, the coordinator refuses it from afar, and a node's report
  carries the worked-out size under that name for coordinators older than 1.30.
- An older worker sends no report and sweeps nothing; the dashboard says to upgrade it. An older
  coordinator ignores the report and sends no keep marks.

### Agents asking for more space (the user's decisions, 2026-11-15)

From 80% of a node's `max_size` every command from a project tells the agent to ask its user for
more. Five projects at once may need more than 20 GB, and the user should not have to find the
setting: the agent asks for them, and every change is recorded.

- **The request**: with its user's yes, the agent runs `mulebox storage ask --size 30GB --reason
  "..."` (`--node` when there are several). The coordinator keeps it in `setting_asks` (schema
  27) with the project, the dev machine, the job and the reason (coordinator/setting_asks.py).
  Only `max_size` can be asked for, and only more than the node has.
- **Who confirms is the owner's choice**, the Agents option (`mulebox agents ask|allow`, the
  Agents window): "Ask me first", as installed, keeps a request waiting for the owner's answer;
  "Allow, and record it" applies it at once (many owners trust their agents). Either way it is in
  the settings history.
- **The answer**, on the dashboard's strip under the header (option A of the mockups in
  design-system/approvals/, the user's pick): Approve, Decline with an optional note, or another
  value; or `mulebox storage approve|decline`. Several requests for one setting of one node get
  one answer, offered at the largest value asked. A yes goes to the node as the owner's own
  change would (node_settings.change), on its next check-in.
- **The agent hears the answer** in its next command from that project (`space_answers`, once);
  while a request waits, the notice says so and not to ask again, and for 7 days after a decline
  it says the owner declined, with the note.
- **The settings history** (`setting_changes`, the newest 2000): every change of a node's
  setting, by the owner in the settings window or with `mulebox machine config`, an answered
  request, one applied without asking, an undo, and a change of the Agents option itself, so a
  later change with no confirmer is explained. Each has the old and new value, who asked and
  why, who confirmed (the dashboard has no sign-in, so "the dashboard, from <address>", or the
  command and dev machine), and when the node took it. A change can be undone while it is the
  node's latest of that setting, once; undoing a raise mulebox has filled leaves the node over
  its limit until the cleanup catches up.
- **What it does not do**: the commands have no sign-in either, so "Ask me first" keeps an
  honest agent waiting for its user, not a rogue one; the skill tells agents never to answer a
  request. A worker needs no change: the answer reaches it as any setting from afar.

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

- A separate read-only process beside the coordinator (its controls are the one exception, and
  their writes go through `mulebox rpc`): aiohttp serving static files, canvas
  graphs. One Server-Sent Events stream for queue changes and metrics, one per open job
  log; both resume by event id after drops. Contract: [interfaces-m2.md](interfaces-m2.md).
- Shows: every machine with whether it is online, its free slots, capabilities, what it
  runs and a small CPU and memory reading, as each worker reports it with its claims and
  heartbeats (M5.3); the queue by machine (one lane per
  machine with what runs and what waits for it; jobs several machines could take in one
  shared list, jobs no machine fits marked stuck), failed, passed and recent jobs behind
  tabs, live log, history, and CPU per core, memory, disk and Docker containers for the
  machine the dashboard runs on. For another machine, CPU per core, memory and its fullest
  disk over the last 5 minutes, from what its worker sends with its claims and heartbeats,
  kept by the dashboard process (no Docker count or overhead there).
- Look: the design system, [design-system.md](design-system.md) (Gauge, chosen 2026-11-10).
- The front end is React (M14.10), in `web/` at the repository root: React 19, Vite, TypeScript,
  Tailwind CSS locked to the design system's tokens (its own palette and scales are switched
  off, and a lint step fails on a value typed into a class name), Radix primitives for menus
  and tooltips, Lucide icons, Geist bundled. No state library: the one event stream feeds
  small stores read with `useSyncExternalStore`, and the routes are hashes. It is built to
  static files in `mulebox/dashboard/app/` at release time and by `mulebox setup` on the
  dev machine, so a node never needs Node.js and the install stays one command. Next.js was
  weighed and left out: it would need Node and a second server on every machine.
- With no build in the package, `/` answers 503 with how to get one, and the API keeps
  working.
- The sign-in page of `lan` mode is part of the build too (`web/login.html`), with no script,
  and only it, its stylesheet and the fonts are open without a session.
- Layout: a live monitor in boxes that fills the window, machine load first and the jobs
  box below, one theme over the whole page, and a system, light or dark switch remembered
  per browser. System is the default; the sign-in page always follows the system.
- Honest about the queue: a waiting job is not assigned until a worker claims it, so the
  lanes only ever say where a job can go, never where it will.
- What a running job does, on its card: its stage in words (a CI job's GitHub step) and a meter
  of the cores the job alone uses, which pulses only at half a core or more, so the busy job
  stands out. An agent job is read from its unit and containers, a CI job from its runner's
  service and the Compose containers started from the runner's work folder (a plain
  `docker run` of a workflow says nothing of where it came from and is not counted). What it is
  downloading, how far and how fast, is a reading of its own (Downloads, below).
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
- The page can steer the queue: cancel, pause, resume, move in line and boost a job, and pause a
  machine. A GitHub run's slot moves in line while it waits; once it runs it can be frozen and
  boosted like a job (its runner's service and containers), and cancelled, by asking GitHub. mulebox is for its owner's own network, so these are on wherever the page opens, as
  the same commands are from any dev machine with ssh to the machine (decided by the user on
  2026-11-10; before 0.87.0 cancelling needed a sign-in on the `lan` address and was off by
  default). Each sends what the CLI sends, by the same `mulebox rpc`, so the dashboard process
  never holds a writable store. Protection against other pages: interfaces-m2.md, Controls.

### Downloads (the user's ask, 2026-11-13)

A node behind a slow VPN restores GitHub's cache at 0.6 MB/s, and a step doing that sits at no
CPU for minutes, which looks hung. So a running job's card and `mulebox status` say what is
downloading, how much of how much, how fast, and whether it waits on the network or has stalled,
so the slowness reads as the network's, not the node's. One reading per job, `download` in the
heartbeat's `activity` (`common/download_watch.py`), made where the job runs and sent with the
heartbeats that already go (every 3 s for an agent job, 10 s for a CI run): no poll of its own.

- What is downloading comes from the job's own output, the lines tools print anyway
  (`common/download_lines.py`): GitHub's cache restore (`Received <done> of <total>`), a tool
  into the runner's tool cache, pnpm, pip and uv, Playwright's browsers, and image layers
  (pullnoise.py). A CI run's lines are read from the runner's pages with the times it stamped
  on them; they reach the node in blocks of about 4 KB, so on a slow link the figures trail,
  and the reading says how old they are rather than calling a quiet minute a stall.
- How fast the bytes move now is measured where it can be the job's own: an isolated runner's
  container has a network of its own. An agent job's unit and a plain runner share the node's
  network, which a desktop and the VPN keep busy, so its traffic is shown as the machine's and
  never decides anything, like the machine's readings in Time limits.
- Waiting on the network: something is downloading and the job's CPU is under a tenth of a core.
  An isolated runner's own traffic with an idle CPU counts as a download with no line to name it.
- Stalled: no byte for 60 s. Any byte counts, in the job's own traffic where measured or in
  the printed figures, so a slow line is slow, never stalled. Playwright prints every tenth, so
  its lines alone call a stall only past twice the longest gap seen between them, and nothing
  before the first. pip prints a file's size and nothing after, so its stall is unknown, never
  guessed. A download ends at its total, at its own end line (a named one ends only its
  download), or for images when every layer has its data, before the extraction.
- A line that only looks like progress, with figures out of reach, is no reading: the parser
  never raises on output.
- A download belongs to its stage or step. Not read: git's `Receiving objects`, curl and wget
  meters (they redraw one line, which a log without a terminal does not keep), Gradle and Maven.

## Multiple machines

- Workers declare capabilities (`slots`, `docker`, `arch`, toolchains) and claim the
  first compatible job in line (Order of the line). Which free node takes a job is below,
  Which node runs a job. No speed scores or weights yet.
- A job whose `needs` no known worker offers is refused at submit, with what to change. A
  queued job whose capable workers are all offline stays queued and says so.
- Add a machine: `mulebox setup <worker> --worker-of <coordinator>` (docs/install.md, More
  machines). The worker gets a key of its own, which the coordinator lets run `mulebox rpc` and
  `rpc-download` only, and over `rpc` only a worker's requests (`coordinator/worker_keys.py`).
  It registers with its first claim, with its slots, capabilities and toolchains. There is no
  warm-up step: toolchains install themselves on a first job (M17.3), and `mulebox warm` fills a
  project's caches on whichever machine takes it.
- The cluster holds as many jobs at once as its online workers have slots, and never fewer than
  the coordinator machine's own `slots` (`workers.cluster_limit`); each worker keeps to its own.
- Replace a machine: `mulebox machine drain` (finishes current work, takes no new jobs; a
  `workers.draining` column, schema 15), stop it, then `mulebox machine remove`, refused while
  it is online or has jobs, as its next claim would bring it back. A drain leaves its GitHub
  runners alone: GitHub hands them jobs, and a reservation refused would leave a CI run hanging.
  Moving the coordinator is a documented manual step (docs/install.md).

### Which node runs a job (the user's ask, 2026-11-14)

Nodes ask for work and the coordinator never assigns it, so the project never chooses a node
and nothing has to know which nodes are idle: a free node asks within seconds. When a node asks,
it gets the first job in line it can run (needs, a free slot, its branch not busy), unless
another node that is free right now should have it (`coordinator/node_choice.py`):

1. **Priority** (M23.4, Node settings): a node ranked above that offers the job's needs, for
   `GRACE_S` (30 s).
2. **The branch's node:** on the same level, the node that ran the branch's last job, for
   `HOLD_S` (10 s). Its project folder already holds the branch and its set-up dependencies
   (Project folders), so a job there sends only what changed and skips `setup`; on another node
   the branch starts from nothing. Read from the job history, no new state.
3. **Room:** else, on the same level, a node with more free slots than the asking one, for
   `HOLD_S`. A tie takes the job at once. Free slots, not CPU readings: a slot is what a node
   promises a job, and a reading moves with every job's own phases.

Each wait counts from the first time a node left the job (`jobs.deferred_at`, schema 23), not
from its arrival as before 1.21.0, so a job that waited behind a busy line still gets its
preferred node, and a node that can never take it (an upgrade ahead of it, a GitHub slot) holds
it up at most that long. The waits are short as the preferred node is free and asks every few
seconds.

**`--on <node>`** (`check`, `run`, `warm`): the job is for that node alone, in `pinned_worker`
as a runner slot is, so none of the above applies and no other node takes it, however long it
waits. Refused at submit for a name no node has or a node without the job's needs. A result
counts as already tested (Results an agent need not repeat) only if it ran on that node. The
coordinator echoes `on`, and a client whose coordinator does not cancels the job, as one older
than this would run it anywhere. GitHub runs choose their node through their runner's labels
(docs/install.md, Which node runs a CI job).

**The system** (M25.6, 1.23.0): a job runs only on a node of the system its project was set up
for. Found 2026-11-14: a Mac node took a Linux project's jobs and one failed, as its
`node_modules` held x86-64 packages from the Linux node and the Mac's Docker is arm64. Each
worker offers `linux` or `macos` as a capability (`common/systems.py`), and the coordinator adds
that need to every job at submit (`needs.required`): `macos` for a job that needs `xcode` or
`simulator`, else `linux`, or what `.mulebox.yml` says in `os:`; `os: any` adds none, for a
project that runs the same on both. The coordinator adds it, not the client, so a client of any
version gets the rule, and an older coordinator ignores the field. A worker older than 1.23
offers no system and is read as `macos` if it offers `xcode` or `simulator`, else `linux`, so a
mixed cluster keeps running. The chip (`arm64`, `x86_64`) is not part of it: Docker images and
toolchains differ by chip too, but a node's own folders are set up on that node, and the
failure seen came from moving between systems, not between chips of one.

**Dev mode** (1.23.0, the user's ask, 2026-11-14): a node being set up or tried out takes no
project's jobs by accident. With `dev = true` in its `node.toml` a node claims only jobs pinned
to it, `--on` and its own runners' slots and upgrades; no other node waits for it (above); a job
only such a node could run waits with the reason and the fix. Set by `mulebox setup --dev` for a
new node, or from afar like `slots` (Node settings, below), where asking for it counts at once,
before the node has written it. The coordinator's own node can never be in dev mode: every job
goes through it, so `node.toml` refuses it there and a change from afar is refused.

## Node settings (M23.9, M23.4, the user's ask, 2026-11-13)

mulebox suggests how a node is set up and does that by default, and the owner decides: a node
with 2 slots may serve its owner better with 3. So a node's settings can be read and changed from
the dev machine (`mulebox machine config`) and from the dashboard, with no hand edit and no
restart.
- **What can be changed from afar: `slots`, `priority` and `dev`** (the user's decision,
  2026-11-13, `dev` 2026-11-14; the rest is shown read-only). Both only change how much work a
  node takes and when; a wrong value slows the queue and is undone the same way. Left out:
  `capabilities`, which say what the machine really has (Docker, Playwright's system packages),
  so a wrong one fails jobs, and `mulebox setup` finds them; `[job_env]`, which reaches every job's
  processes, so writing it from a page with no sign-in would let anyone on the network run code
  on every node (`PATH`, `NODE_OPTIONS`, `LD_PRELOAD`); and roots, roles, the coordinator and the
  dashboard, which need the services restarted.
- **The truth stays in each node's `node.toml`.** The coordinator holds only a requested change,
  `workers.wanted` (schema 21), and what the worker last reported, `workers.settings`. A worker on
  another machine cannot be written by the coordinator, and should not be: it reaches the
  coordinator, never the other way round. So the change travels back on what the worker already
  asks: a claim's or heartbeat's reply carries `node_settings` while a change waits, the worker
  writes it into its own `node.toml` (only the value on each setting's line, its key bare or
  quoted, its comment and every other line kept; read and written through safefile, so a symlink
  is refused and the file is replaced whole, never half written; a file over 1 MiB is refused,
  never cut), checks the result with the same reader the service uses, and reports what it now
  has with its next claim or heartbeat, which clears the request. A worker that cannot write it
  reports why, and the request stays with that reason until the owner changes or drops it. A
  machine that is offline gets it when it comes back. A worker older than this never reports
  settings, so a change for it is refused with "upgrade it first" rather than left waiting.
- **The next job, no restart (M23.9).** The worker reads its `slots` before every claim, so a new
  value counts from the next claim. Running jobs keep their slot: a lower value than what runs
  only stops new claims until enough jobs end, it never stops a job. A hand edit of `node.toml`
  applies the same way: the worker looks at the file's time every 2 s and takes `slots`,
  `priority` and `capabilities` from it live; a file that does not read is logged and the old
  values stay; other changed fields are logged as needing `mulebox service restart worker`.
- **A suggestion beside the value.** From the cores and memory the worker last reported: about 4
  cores and 6 GB a job, at least 1, `max(1, min(cores // 4, memory_gb // 6))` with memory in
  decimal GB like every size shown (8 cores and 16 GiB, 17.2 GB, give 2, today's default; 16 and
  32 GiB, 34.4 GB, give 4). It is shown next to the current value with its
  reason (the formula is the user's decision, 2026-11-13), and never applied by itself: the owner's value stays until the owner changes it. From
  afar slots go from 1 to 64; a hand edit may set more, as a big machine may want it.
- **Node priority (M23.4).** `priority = "preferred" | "normal" | "fallback"` in `node.toml`,
  `normal` when left out (the names and the 30 s wait below are the user's decision, 2026-11-13). A node takes a job only when no node ranked above it could take that job
  now: online, not paused, not running a boosted job, with a free slot and the job's `needs`. So
  the spare machine is `preferred`, the owner's desktop `normal`, a Mac `fallback`, and the
  desktop runs jobs only while the spare one is full. Within a level the order is as before:
  whoever claims first. The rule is per job, so a job only the lower node can run is not held
  back. A job left waiting 30 s in spite of a free better node (one that cannot claim it for a
  reason of its own, such as an upgrade or a GitHub slot ahead of it on that node) goes to the
  next node, so a ranked node can never leave a job stranded; the 30 s count from the first time
  it was left (Which node runs a job, above). Runner reservations are pinned to their machine
  and do not use it.

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
  GitHub keeps the whole log. The result is GitHub's too, but GitHub does not hand it to the
  completed hook, so the hook reads it from the runner's own diary: passed, failed or
  cancelled, the first failed step and GitHub's message on it.

### Runners for public repositories (M23.6, the user's ask, 2026-11-12)

On a public repository anyone can open a pull request, and GitHub runs the workflow file from it,
so a stranger can name the runner and run anything on the node. Two layers, the first for every
runner, the second for public repositories:

1. **The guard** (built, 1.3.0, `runners/guard.py`). The job-started hook's first step refuses a
   fork's pull request, a follow-on run of one, a run with no readable event, and, on a runner
   registered with accounts, a run any other account started or re-ran. Read in
   actions/runner (`JobExtension.cs`, `JobHookProvider.cs`, `GitHubContext.cs`): the hook runs
   after the job's actions are downloaded, before Docker actions are built, before `container:`
   and `services:` start and before any step; its environment is built empty and filled from the
   `github` context's allowlist, so a workflow's `env:` cannot fake the actor or the event path.
   A failed hook does not end the job, though: the runner goes on to every step whose `if:` holds,
   `if: always()` included (`StepsRunner.cs`; found by Sol's review). So a refusal kills the
   runner's `Runner.Worker` while the hook still runs inside it. A comment on a pull request is
   refused too, as the event does not say where that pull request came from. The fork rules are
   runner-up's (github.com/kunchenguid/runner-up).
2. **A fresh container per job** (built, 1.4.0, `runners/place*.py`, `runners/jit.py`). The guard
   can be wrong, and an allowed run can still pull in a bad dependency, so on a public repository
   no job runs as the node's user. An isolated runner is a folder whose `.mulebox-runner.json`
   says `isolated`; the worker keeps a thread for each (`place_keeper.py`), which loops:
   - A one-job runner from GitHub (`generate-jitconfig`), made with the node's own `gh` signed in
     as the repository's admin: GitHub lets only an admin make a runner. A token file was weighed
     and left out, as the node's `gh` already is that admin (the user's call). Its configuration
     goes to the container on stdin, so neither `ps` nor `docker inspect` shows it; one never given
     a job is deleted when its container stops.
   - The container, from GitHub's runner image with git, curl, shellcheck and archivers, built once
     per runner release (`place_image.py`), so a job starts in about 10 s. Removed when it ends.
   - Confined (`place_container.py`): no folder of the node but the runner's `hooks` (read-only),
     `io` and `_diag`, no Docker socket, all capabilities dropped, `no-new-privileges`, the image's
     own user, limits on memory and processes, half the CPU weight, a network of its own. One tool
     cache volume per runner, written only by runs the guard let in. The project's package caches
     are not mounted: the node's caches are its own jobs', and a read-only mount was left for later.
   - The slot (`place_hook.py`, `place_bridge.py`): the container's job-started hook writes the
     job's GitHub values and its event to `io` and waits. The node reads them before any step (no
     symlink, a size limit, GitHub's names only), runs the guard and reserves the slot under the
     runner's own name, so supervision, the dashboard and release work as for a host runner. A
     refusal kills `Runner.Worker` inside the container, as on the host. Pause and boost act on the
     container (`docker pause`, CPU shares) in place of a service.
   - Worker restarts (`place_handover.py`, 1.13.7): a deploy restarts the worker, and its stop
     used to remove every container, also one whose one-job runner GitHub had just given a job,
     which then hung for about 10 minutes and could not be cancelled. Two ways out were weighed:
     upgrades that wait for busy places, and containers that outlive the worker. Waiting cannot
     close the gap, as GitHub can hand a runner a job at any moment, also between the check and
     the restart, so the containers outlive it. On stop, a container is kept if its job has asked
     or GitHub refuses to delete its one-job runner (it does once it has given it a job); only a
     runner GitHub has deleted can never get a job, so only then does its container go. The
     container runs with `--sig-proxy=false`, so the stop signal the worker's `docker` client
     gets does not reach it, and Docker removes it when it ends; that client then ignores
     SIGTERM, so the worker kills it itself (1.13.8), or it holds the stop for systemd's 90 s. The next worker finds it by its
     `.mulebox-place`, follows it, answers its job if nothing has (the reservation key is the
     job's own, so asking again finds the same reservation), and ends the round as usual;
     supervision keeps the slot meanwhile. A worker stopped for good leaves such a job waiting for
     an answer (up to 6 h); `mulebox runner remove` removes it.
   - Left over: the container shares the node's kernel, and can reach the node's network beyond
     what the firewall closes. A job that needs Docker itself cannot run in it. A job can write its
     own diary in `_diag`, so the result mulebox shows for it is the job's word.

## Isolation per job (M23.1, decided by the user 2026-11-14)

Today a job runs under systemd as the node's user. Code an agent wrote, or a package it pulled in,
can read what that user can: `~/.ssh`, the `gh` login, the coordinator's key, other projects'
folders, and it can use Docker, which is root on the node. Safety above says so: mulebox is not a
sandbox. This is a proposal to make it one, as a choice, for nodes that run code their owner has
not read.

**Levels.** `isolation:` names how far a job is kept from the node:

| Level | A job runs | Keeps it from | Costs |
| --- | --- | --- | --- |
| `none` (today) | as the node's user, under systemd | other jobs' files, by convention only | nothing |
| `container` | in a fresh container per job | the node's home, keys, other projects, Docker itself | about 1 s to start; no Docker in the job (below) |
| `vm` (later) | in a throwaway virtual machine | also the node's kernel | a VM image to keep; 10 to 30 s to start; memory set aside per job |

`vm` is named so the field has room for it; it is not part of this step.

**Who decides.** The node's owner carries the risk, so the node sets a floor and a project can
only ask for more: `isolation = "container"` in node.toml makes every job there run isolated,
whatever `.mulebox.yml` says; `isolation: container` in `.mulebox.yml` asks for it on a node whose
floor is `none`. A node that cannot give a level (a Mac, below; a node with no Docker) does not
claim a job that asks for it, through its capabilities, as with `needs:`. Proposed default floor:
`none`, so nothing changes for anyone until they ask.

**The container.** Built like an isolated runner's place (`runners/place_container.py`), so the
confinement is one piece of code:

- Mounts: the job's branch tree (read-write), its own package caches (read-write, as today), the
  node's toolchain folder (read-only), the browser folder for `needs: [playwright]` (read-only).
  Nothing else of the node: no home, no `~/.mulebox` beyond these, no Docker socket.
- The node's user id (`--user`), so files the job writes are the worker's to clean, with no
  `reclaim`; all capabilities dropped, `no-new-privileges`, a read-only root file system with a
  `tmpfs` for `/tmp`, `HOME` inside the job folder. Limits on memory and processes; CPU weight as
  today, so Boost and Freeze (`docker pause`) work as they do for a runner's place.
- The image: a mulebox job image, built once per node from Ubuntu with git, a compiler and the
  usual build tools, matching the node's own system so toolchains it installed (M17.3) run in
  it. A project may name its own (`image:`), then bringing its own toolchains.
- Network: one network per job. It reaches the internet and the job's own compose services; it
  does not reach the node's own services on 127.0.0.1 (dashboard, a database the owner runs).
  The node's LAN stays as reachable as the firewall leaves it, as for a runner's place.
- What a job is told and measured stays the same: `env:`, `job_env`, ports, check-ins, activity
  (the container's CPU through the engine, `worker/docker_stats.py`), cancel and time limits.

**Compose jobs, the hard part.** Today a job line runs `docker compose exec -T api ...` with the
node's Docker. Inside the container there is no Docker, and giving it the socket would undo
everything above. Three ways were weighed:

1. **The socket mounted in.** Refused: Docker access is root on the node.
2. **The worker runs Compose, the job gets a narrow door (proposed).** The worker brings the
   job's services up as well as down (today `up` runs inside the job's unit, teardown is already
   the worker's), under the same policy (`worker/compose_policy.py`), which already refuses what
   reaches past the job. The
   container joins the services' network, so `db:5432` works by name. For job lines that use
   `docker compose exec`, the container gets a socket from a small mulebox proxy that answers
   only `exec`, `logs`, `ps` and `inspect`, and `start`, `stop` and `restart`, each only for a
   container with this job's labels, and a listing shows only those; anything that would make a container, an image or a volume
   (`run`, `create`, `build`, `pull`, `cp`) is refused with a message. Images stay in the node's
   cache, so no extra download over a slow link. The cost is the proxy itself: code that must
   read Docker's API exactly, and tests against a real engine.
3. **A Docker engine of the job's own** (Docker-in-Docker, or Sysbox so it needs no privileged
   container). Any job line works, `docker build` and Testcontainers too, and nothing of the
   node's engine is reachable. But every job starts with an empty image cache, so every image is
   pulled again (minutes per job on a node behind a slow VPN), unless a registry mirror is kept
   on the node, and Sysbox must be installed by the owner with root.

Proposed: way 2, with way 3 left for a project that builds images or uses Testcontainers, which
then runs at `none` on a node that allows it. A job line that needs more than the proxy allows
fails with a message naming the call, not a hang.

**Mac nodes.** An Xcode build needs macOS, and macOS runs no macOS containers, so a Mac node offers
no `container` level for Apple jobs: it claims none that asks for it. A Linux-container job on a
Mac (Docker Desktop) could get it later. The macOS route is `vm` (Apple's Virtualization
framework), a step of its own.

**Left as it is.** A container shares the node's kernel, so a kernel bug is a way out; `vm` is
for that. Compose services run images the project chose, contained by the policy, not by this
step. A package cache is still a channel between jobs of one project, on purpose.

**Built:** part 1, 1.18.0: `isolation:` and `image:` in `.mulebox.yml` (common/isolation.py,
the need `isolated` a Linux worker with Docker offers by itself), the container
(worker/isolated.py, mulebox's image in worker/job_image.py, the confinement shared with a
runner's place in common/confined.py). The job's unit runs `docker run`, so cancel, time limits
and the log stay the unit's; the container and its network carry the job's labels, so the
teardown of compose jobs removes them, and pause and boost reach it. The project's git
repository is mounted too, as the branch tree is a worktree of it. A compose job asking for it
is refused until part 2.

Part 2, 1.19.0: compose jobs. The job's unit runs, on the node, the lines mulebox writes for a
compose job (`up --wait` and the report of the services' logs on failure), then makes the
container with `docker create`, joins it to every network of the job's Compose project, and
starts it attached (`docker start --attach`), so the services answer by name. The door
(worker/docker_door.py, its rules in worker/door_rules.py) runs in the unit beside it, on a
socket under the jobs root, mounted as the container's `DOCKER_HOST`, with the node's `docker`
command and Compose plugin read-only; it takes one request per connection, passes on only what
door_rules.py names for containers carrying the job's label, records the execs it made, and
refuses the rest, saying so in the log. `localhost:$MULEBOX_PORT_...`, which the docs tell
projects to use, is forwarded inside the container to each service's own port
(worker/port_forward.py, run by the image's Python; TCP only). The mounted `docker` command is
the node's, linked against its system, so in a project's own image of another system `docker
compose exec` may not run, and with no Python there the ports are reached by service name.

Part 3, 1.20.0: the floor. `isolation = "container"` in node.toml makes the worker add the need
`isolated` to every job it claims (worker/job.py, `floored`), so a job whose project says
nothing runs isolated there; it applies from the next claim, like `slots`. Every worker offers
the need `unisolated` by itself unless its floor is `container`, and an explicit `isolation:
none` in `.mulebox.yml` asks for it, so such a job is never claimed by an isolated node, and with
none left the coordinator refuses it at submit and names the floor (coordinator/needs.py). A
project that leaves the field out takes its node's floor. A node older than 1.20.0 offers no
`unisolated`, so a project that writes `isolation: none` needs its nodes upgraded.

**Decided by the user (2026-11-14):** the default floor is `none`; compose jobs take way 2, the
worker running Compose and a narrow proxy; the job image is mulebox's own, and a project may name
its own `image:`; a project cannot ask for less than its node's floor: such a job is refused and
says why.

## Safety

- Configured roots per worker (`jobs/`, `projects/`, `cache/`, `runners/`); the path-safety module
  resolves paths, rejects anything outside the roots, mount points and symlink escapes, and
  deletes with directory-descriptor-anchored operations (no check-then-delete race).
- No secrets leave the dev machine (excludes above); CI values in configs are throwaway.
- Test databases are per job; jobs must not use existing databases on the machine.
- Container ports of `compose:` projects bind to 127.0.0.1, whatever the compose file says.
- Docker access is root-equivalent: running jobs as the machine's normal user is fine for
  a single trusted owner; a dedicated user is optional hygiene, not isolation. mulebox is not
  a sandbox: its checks stop mistakes and a CI file's assumptions, not a hostile project.
  Isolation per job, above, is the way to run code nobody has read.
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
  dashboard/    server.py  pages.py  streams.py  hub.py  events.py  metrics.py  data.py
                app/ (the React build, not in git)
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

M4 Pro dev machine vs a 2014 4-core/8-thread i7 with 16 GB on 2.4 GHz Wi-Fi, two real projects:

| Workload | Dev machine | Old i7 | GitHub-hosted |
| --- | --- | --- | --- |
| Next.js + pnpm gate (lint, types, build, 5k tests) | 60 s | 208 s | 9-10 min job |
| Laravel + Docker + Playwright CI job | ~2.5 min | 4.5 min | ~10 min job |

Single-threaded tools were 2.2-2.6x slower on the old machine; first runs were dominated by
downloads over Wi-Fi, so warm caches matter more than CPU.
