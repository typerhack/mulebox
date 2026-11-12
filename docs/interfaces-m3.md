# Interfaces for M3 (GitHub Actions runners)

Contract for the parallel build of M3. Earlier contracts: [interfaces.md](interfaces.md),
[interfaces-m1.md](interfaces-m1.md). Design: [design.md](design.md) (GitHub Actions).
Changes to this file go through the integrator.

## Idea

A GitHub self-hosted runner lives on a worker as its own user service. Before GitHub's job
starts, the runner calls its job-started hook, which **reserves a slot** in the mulebox
queue pinned to that worker and blocks until the slot is granted. The job-completed hook
releases it. Agent jobs (`mulebox check`) and runner jobs share one line and the
same slot limits, so the machine never runs more than `slots` heavy jobs at once.

A completion hook is skipped when the runner crashes, so the worker supervises active
reservations: while the runner has a job process the reservation stays alive; when it is
gone for 60 s the worker releases it.

## Reservations (coordinator)

- A reservation is a job row with `kind = "runner"` (agent jobs have `kind = "job"`), no
  snapshot, `pinned_worker = <node name>`, `project = <owner>__<repo>` (`/` replaced, so it
  passes the name rule), `job = <GITHUB_JOB>`, `branch = <GITHUB_REF_NAME>`, `client =
  "github"`, `argv = []`. It is created directly in `queued` (it skips `uploading`).
- New columns (schema version bump with a migration for existing databases): `kind TEXT
  NOT NULL DEFAULT 'job'`, `pinned_worker TEXT`, `runner TEXT`, `run_url TEXT`.
- One line across both kinds, oldest first unless its owner moved a row (`priority`,
  `store.line_key`): `queue.claim` (agent jobs) never takes `kind = runner` rows, and does not
  take a job while a queued reservation pinned to that worker is **ahead** of it in line.
  `acquire` (below) grants a reservation only when it is first in line among the queued rows
  the worker could run (a paused agent job keeps its place without holding it back) and a cluster slot and a worker slot are free. Granting moves it `queued ->
  starting -> running` in one transaction, sets `worker = pinned_worker`, `started_at`, and
  a worker lease.
- A waiting reservation can be moved in line (`job_control` `first|up|down|last`, the
  dashboard's arrows and three dots), and nothing else. A granted one can be paused, resumed,
  boosted and set back (`pause|resume|boost|normal`): the worker's supervisor freezes or thaws the
  runner's service `mulebox-runner@<name>.service` (on a Mac stops or continues the process group
  of its launchd agent, and boosts nothing of its own) and pauses its Compose containers (those whose
  Compose folder is in the runner's `_work`), or raises their CPU and disk weight
  (runners/runner_controls.py); a boost keeps new jobs off the machine, as for an agent job. A
  frozen listener stops answering GitHub, so a long freeze can fail the run. When the
  reservation ends while paused or boosted, the service is thawed and set back; after a worker
  restart the first round sets it as the coordinator says.
- The dashboard cancels a run by asking GitHub: `gh run cancel <run id> -R <owner/repo>` on the
  dashboard's machine, from the reservation's `run_url` (runners/cancel_run.py). `gh` must be
  logged in there with rights on the repository; otherwise the reply says so. The slot frees when
  the runner stops, through its completed hook.
- Slot accounting counts `starting|running|cleaning` rows of both kinds.

## Wire messages (protocol.py additions)

| Request | Body | Reply |
| --- | --- | --- |
| `reserve` | `worker`, `repository`, `job`, `run_id`, `run_attempt`, `runner`, + `branch`, `run_url`, `idempotency_key` | `submit_ok` (job_id, state) |
| `acquire` | `job_id` | `status_ok` (state `running` when granted, else `queued` + `position`) |
| `release` | `job_id`, `outcome` (`passed`/`failed`/`cancelled`/`interrupted`), + `ci_result` | `status_ok` |
| `runner_jobs` | `worker` | `queue_ok` (active reservations pinned to that worker) |

`idempotency_key` defaults to `gh-<repository>-<run_id>-<run_attempt>-<job>-<runner>`, so a
hook retried by GitHub never creates two reservations. `heartbeat` with `lease: "worker"`
and no `attempt_id` renews a reservation's worker lease. Reservations ignore the client
lease. A release on a finished reservation is a no-op `status_ok`. `ci_result` is how the GitHub
job went, as the completed hook read it: `outcome`, and for a failure `step` (the first step that
failed) and `message` (what GitHub says on it), strings cut to 32, 200 and 500 characters,
anything else dropped. Stored as `jobs.ci_result` (schema 17); empty means not known.

## Runner recovery (measured)

- Hard kill: GitHub keeps the old session for about 3 minutes and answers "A session for
  this runner already exists". The runner retries every ~30 s and reconnects by itself;
  nothing needs restarting.
- Reboot: the unit starts with the machine and the runner connects in seconds to a few
  minutes, depending on the network. GitHub can show it `offline` for a few minutes more.
- A reservation whose hook died while waiting for a slot is released by supervision 60 s
  after the worker starts. Until then it holds its place in the line.
- GitHub ends an interrupted run on its own; queued runs then start on the runner.

## Hook entry points (`mulebox/runners/hooks.py`, CLI `mulebox runner-hook`)

- `mulebox runner-hook started`: reads `GITHUB_REPOSITORY`, `GITHUB_RUN_ID`,
  `GITHUB_RUN_ATTEMPT`, `GITHUB_JOB`, `GITHUB_REF_NAME`, `GITHUB_SERVER_URL`, `RUNNER_NAME`
  from the environment. First, before the node config is read, the guard (`runners/guard.py`
  `admit`), which finds the runner folder from `ACTIONS_RUNNER_HOOK_JOB_STARTED` or the job's
  working directory, on `GITHUB_EVENT_PATH`,
  `GITHUB_ACTOR`, `GITHUB_TRIGGERING_ACTOR` and the runner's `actors` in `.mulebox-runner.json`:
  a fork's pull request, a follow-on run of one, a comment on a pull request, an unreadable
  event, missing or unreadable metadata, or another account's run kills the runner's
  `Runner.Worker` (as supervise.py finds it, and among the hook's own parents; a failed hook alone
  lets `if: always()` steps run) and exits 1 with `mulebox: this runner refuses ...`, reserving
  nothing; with no such process found it holds the job until GitHub ends it. `started.sh` kills
  its parent `Runner.Worker` when mulebox exits with any failure. Then it sends `reserve`, then `acquire` every 2 s until granted, printing
  `mulebox: waiting for a build slot (position N)` at most every 30 s. Writes the job id to
  `<runners>/<runner>/.mulebox-reservation` (atomic). Exit 0 once granted. Gives up after
  `MULEBOX_HOOK_TIMEOUT_MIN` (default 120) with exit 1 and a clear message. Talks to the
  coordinator through the worker's `open_link` (local link in M1-style single node).
- `mulebox runner-hook completed`: reads the reservation file, sends `release` with outcome
  from `GITHUB_JOB_STATUS` if present (`success` -> passed, `cancelled` -> cancelled, else
  failed). GitHub does not set it for hooks (all 129 reservations before 0.76.0 were stored
  as passed), so otherwise the result comes from the runner's newest diary,
  `<runner>/_diag/Worker_*.log` (runners/diary.py): the last `job state = '<state>'` or `Update
  job result with current step result '<state>'` before the hook, the first `Step result:
  Failed` step and its telemetry's `errorMessages`. Checked on 124 real runs against the
  runner's final `Job result after all job steps finish`: all agreed. Nothing found: passed,
  with no `ci_result`. Removes the file (safepath, runners root). Always exits 0 (a failed release is
  logged; supervision cleans up).
- Hook scripts installed per runner: `<runners>/<runner>/mulebox-hooks/started.sh` and
  `completed.sh`, each `exec ~/.mulebox/bin/mulebox runner-hook <started|completed>`.

## Supervision (`mulebox/runners/supervise.py`, called from the worker loop)

- Every 10 s: `runner_jobs` for this worker. For each active reservation: if the runner's
  job process is alive (`Runner.Worker` process whose cwd or argv is under
  `<runners>/<runner>/`, found through `/proc`, or by argv in `ps` on a Mac; injectable for
  tests), send a worker
  heartbeat; if it has been gone for 60 s, `release` with outcome `interrupted`.
- The worker's own claim loop is unchanged otherwise.

## Runner management (`mulebox/runners/manage.py`, `mulebox/runners/github.py`)

On the node (CLI `mulebox runner ...`):
- `runner add --repo <owner/repo> --actors a,b [--labels a,b] [--name N]`: registration token on
  **stdin** (never argv, never logged). Downloads the latest `actions/runner` release for
  linux-x64/arm64, or osx-x64/arm64 on a Mac (GitHub API `releases/latest`), verifies the
  tarball against the SHA-256
  published in the release body (`<!-- BEGIN SHA linux-x64 -->...<!-- END SHA linux-x64 -->`),
  extracts into `<runners>/<name>/` (safe extraction, shared `worker/archive.py`), runs
  `./config.sh --unattended --url https://github.com/<owner/repo> --token <t> --name <name>
  --labels <labels> --work _work --replace`, writes the hook variables into the runner's
  `.env` (`ACTIONS_RUNNER_HOOK_JOB_STARTED=...`, `ACTIONS_RUNNER_HOOK_JOB_COMPLETED=...`),
  starts the runner's service through `mulebox/services/` (`runner_start`): the unit
  `mulebox-runner@<name>.service`, or on a Mac the launchd agent `mulebox-runner-<name>`
  (services/launchd_runners.py).
  Default name `<node>-<repo>`; default labels `mulebox` (GitHub adds `self-hosted`,
  `Linux`, `X64`).
- `runner add --isolated --repo <owner/repo> --actors a,b [--labels a,b] [--name N]`: no token.
  Linux nodes only. Checks with the node's `gh` that it is an admin of the repository
  (`permissions.admin`), builds the runner image (`place_image.py`), creates the
  `mulebox-isolated` network and writes `<runners>/<name>/.mulebox-runner.json` with
  `isolated: true` and `public`. The worker's `PlaceKeeper` starts a thread for it within 10 s
  (`place.py`): per job, `gh api -X POST repos/<owner/repo>/actions/runners/generate-jitconfig`
  (name `<name>-<8 chars>`, group 1, labels `self-hosted`, `Linux`, the arch, the given ones), a
  container on stdin, the hook's request in `io-<id>/request.json`, the answer in
  `io-<id>/answer.json`, the reservation under `<name>`.
  `--count N` (1 to 8) makes a group: `<name>`, `<name>-2`, ..., each a place of its own whose
  metadata has `group: <name>`; an existing group gains only its missing members. `runner remove
  <name>` and `--repo` remove the whole group.
- `runner list`: name, repo, service state (`running` or `stopped`, `isolated` for an isolated
  runner), busy/idle.
- `runner caches <name> --project <project> [--only cache-npm,...] | --off`: writes the project's
  package cache settings (worker/caches.py `for_job`) into the runner's `.env`, drops them with
  `--off`, records `caches_of` in `.mulebox-runner.json`, restarts the service. Refused while
  busy.
- `runner remove <name>`: removal token on stdin; stops and disables the service, runs
  `./config.sh remove --token <t>`, removes the runner folder through safepath. An isolated
  runner needs no token: its containers (label `mulebox.place=<name>`), its one-job runners left
  on GitHub (named `<name>-<8 chars>`), its tool volume and its folder are removed.
- Unit template `mulebox/machine/systemd/mulebox-runner@.service`: `ExecStart=%h/.mulebox/runners/
  %i/run.sh`, `WorkingDirectory=%h/.mulebox/runners/%i`, `Environment=RUNNER_MANUALLY_TRAP_SIG=1` (so
  run.sh passes a stop on to the listener), `KillMode=mixed` (anything left is killed: a restart
  never leaves the old listener running beside the new one),
  `KillSignal=SIGTERM`, `TimeoutStopSec=5min`, `Restart=always`, `RestartSec=10`. install.sh
  copies it with the others (enable is per runner).

On the dev machine (CLI `mulebox runner register|unregister --repo <owner/repo>`): gets a token
with `gh api -X POST repos/<owner/repo>/actions/runners/registration-token --jq .token`
(or `remove-token`), and runs `mulebox runner add|remove` on the coordinator over
`common.ssh` with the token on stdin. Requires `gh` logged in with admin rights on the repo;
clear error otherwise. `--actors` defaults to the account `gh` is signed in as (`gh api user`),
stored as `actors` in the runner's `.mulebox-runner.json`. `register --isolated` asks for no
token and allows a public repository; the command runs `runner add --isolated` with an empty
stdin line.

## Module ownership for the parallel build

- Agent "slots": `mulebox/common/protocol.py` (new types only), `mulebox/coordinator/`
  (schema, reservations, api), `mulebox/runners/hooks.py`, `mulebox/runners/supervise.py`,
  the call into supervision in `mulebox/worker/agent.py`, CLI `runner-hook`.
- Agent "manage": `mulebox/runners/manage.py`, `mulebox/runners/github.py`,
  `mulebox/runners/release.py` (download + verify), CLI `runner add|list|remove` and
  `runner register|unregister`, `mulebox/machine/systemd/mulebox-runner@.service`, the install.sh
  line that copies it.
- Both: `mulebox/runners/__init__.py` exists already; each adds its own
  `commands_*.py`; `mulebox/runners/commands.py` (integrator) registers both.

## Decisions made during the build (0.6.0)

Slots:
- Schema 2 adds `workers.slots` (a worker's total slots, recorded on `claim` as
  `free_slots` plus its active agent jobs); `acquire` uses it, `cluster_slots` until a
  worker has claimed once. `claim` subtracts a worker's active reservations from
  `free_slots`.
- A worker restart (`restarted: true`) interrupts agent jobs only: a runner is its own
  service and keeps running; supervision handles it.
- `runner_jobs` returns queued reservations too, so a runner that dies while its hook waits
  is released after 60 s instead of blocking the queue. Heartbeats go to granted ones only.
- The started hook writes the reservation file right after `reserve` and, when it gives
  up, releases the reservation as cancelled.
- `GITHUB_JOB_STATUS` unset -> the runner's diary; with nothing there either, `passed` and no
  `ci_result`, which the views show as `released`. The GitHub run stays the authority.
- `mulebox cancel` on a running reservation only marks it; mulebox cannot stop a GitHub job.

Runner management:
- The registration/removal token reaches `config.sh` through `ACTIONS_RUNNER_INPUT_TOKEN`
  (environment), never argv; output is redacted with the token.
- `runner remove` also takes `--repo`; default runner name `<node>-<repo>` (max 64 chars).
- `roots.runners` must be `~/.mulebox/runners` (the unit template uses that path).
- Runner tarballs are cached in `<cache>/actions-runner/` and re-verified on every use.
- Each runner folder has `.mulebox-runner.json` (repo, labels, version).
- Shared download code moved to `mulebox/common/download.py` (also used by toolchains).

Also in 0.6.0: `.mulebox.yml` `env:` (schema 3 stores it as `jobs.env`; since schema 7 the
order of the file travels beside it as `env_order`, because JSON objects are sorted on the wire
and in the store: `submit`, `claim_ok`, `jobspec.in_file_order`). The worker sets
`MULEBOX_JOB_SLUG` (job id, lowercase, `_`) and replaces `${NAME}` in env values with a
mulebox variable or an earlier env entry; no shell is involved. `PATH`, `HOME`, `USER`,
`SHELL` and `MULEBOX*` names are refused.
