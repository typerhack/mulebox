# Interfaces for M3 (GitHub Actions runners)

Contract for the parallel build of M3. Earlier contracts: [interfaces.md](interfaces.md),
[interfaces-m1.md](interfaces-m1.md). Design: [design.md](design.md) (GitHub Actions).
Changes to this file go through the integrator.

## Idea

A GitHub self-hosted runner lives on a worker as its own user service. Before GitHub's job
starts, the runner calls its job-started hook, which **reserves a slot** in the mulebox
queue pinned to that worker and blocks until the slot is granted. The job-completed hook
releases it. Agent jobs (`mulebox check`) and runner jobs share one FIFO queue and the
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
- FIFO across both kinds: `queue.claim` (agent jobs) never takes `kind = runner` rows, and
  does not take a job while an **older** queued reservation pinned to that worker waits.
  `acquire` (below) grants a reservation only when it is the oldest queued row the worker
  could run and a cluster slot and a worker slot are free. Granting moves it `queued ->
  starting -> running` in one transaction, sets `worker = pinned_worker`, `started_at`, and
  a worker lease.
- Slot accounting counts `starting|running|cleaning` rows of both kinds.

## Wire messages (protocol.py additions)

| Request | Body | Reply |
| --- | --- | --- |
| `reserve` | `worker`, `repository`, `job`, `run_id`, `run_attempt`, `runner`, + `branch`, `run_url`, `idempotency_key` | `submit_ok` (job_id, state) |
| `acquire` | `job_id` | `status_ok` (state `running` when granted, else `queued` + `position`) |
| `release` | `job_id`, `outcome` (`passed`/`failed`/`cancelled`/`interrupted`) | `status_ok` |
| `runner_jobs` | `worker` | `queue_ok` (active reservations pinned to that worker) |

`idempotency_key` defaults to `gh-<repository>-<run_id>-<run_attempt>-<job>-<runner>`, so a
hook retried by GitHub never creates two reservations. `heartbeat` with `lease: "worker"`
and no `attempt_id` renews a reservation's worker lease. Reservations ignore the client
lease. A release on a finished reservation is a no-op `status_ok`.

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
  from the environment; sends `reserve`, then `acquire` every 2 s until granted, printing
  `mulebox: waiting for a build slot (position N)` at most every 30 s. Writes the job id to
  `<runners>/<runner>/.mulebox-reservation` (atomic). Exit 0 once granted. Gives up after
  `MULEBOX_HOOK_TIMEOUT_MIN` (default 120) with exit 1 and a clear message. Talks to the
  coordinator through the worker's `open_link` (local link in M1-style single node).
- `mulebox runner-hook completed`: reads the reservation file, sends `release` with outcome
  from `GITHUB_JOB_STATUS` if present (`success` -> passed, `cancelled` -> cancelled, else
  failed), removes the file (safepath, runners root). Always exits 0 (a failed release is
  logged; supervision cleans up).
- Hook scripts installed per runner: `<runners>/<runner>/mulebox-hooks/started.sh` and
  `completed.sh`, each `exec ~/.mulebox/bin/mulebox runner-hook <started|completed>`.

## Supervision (`mulebox/runners/supervise.py`, called from the worker loop)

- Every 10 s: `runner_jobs` for this worker. For each active reservation: if the runner's
  job process is alive (`Runner.Worker` process whose cwd or argv is under
  `<runners>/<runner>/`, found through `/proc`; injectable for tests), send a worker
  heartbeat; if it has been gone for 60 s, `release` with outcome `interrupted`.
- The worker's own claim loop is unchanged otherwise.

## Runner management (`mulebox/runners/manage.py`, `mulebox/runners/github.py`)

On the build machine (CLI `mulebox runner ...`):
- `runner add --repo <owner/repo> [--labels a,b] [--name N]`: registration token on
  **stdin** (never argv, never logged). Downloads the latest `actions/runner` release for
  linux-x64/arm64 (GitHub API `releases/latest`), verifies the tarball against the SHA-256
  published in the release body (`<!-- BEGIN SHA linux-x64 -->...<!-- END SHA linux-x64 -->`),
  extracts into `<runners>/<name>/` (safe extraction, shared `worker/archive.py`), runs
  `./config.sh --unattended --url https://github.com/<owner/repo> --token <t> --name <name>
  --labels <labels> --work _work --replace`, writes the hook variables into the runner's
  `.env` (`ACTIONS_RUNNER_HOOK_JOB_STARTED=...`, `ACTIONS_RUNNER_HOOK_JOB_COMPLETED=...`),
  installs and starts `mulebox-runner@<name>.service`.
  Default name `<node>-<repo>`; default labels `mulebox` (GitHub adds `self-hosted`,
  `Linux`, `X64`).
- `runner list`: name, repo, service state, busy/idle.
- `runner remove <name>`: removal token on stdin; stops and disables the unit, runs
  `./config.sh remove --token <t>`, removes the runner folder through safepath.
- Unit template `install/systemd/mulebox-runner@.service`: `ExecStart=%h/.mulebox/runners/
  %i/run.sh`, `WorkingDirectory=%h/.mulebox/runners/%i`, `KillMode=process`,
  `KillSignal=SIGTERM`, `TimeoutStopSec=5min`, `Restart=always`, `RestartSec=10`. install.sh
  copies it with the others (enable is per runner).

On the laptop (CLI `mulebox runner register|unregister --repo <owner/repo>`): gets a token
with `gh api -X POST repos/<owner/repo>/actions/runners/registration-token --jq .token`
(or `remove-token`), and runs `mulebox runner add|remove` on the coordinator over
`common.ssh` with the token on stdin. Requires `gh` logged in with admin rights on the repo;
clear error otherwise.

## Module ownership for the parallel build

- Agent "slots": `mulebox/common/protocol.py` (new types only), `mulebox/coordinator/`
  (schema, reservations, api), `mulebox/runners/hooks.py`, `mulebox/runners/supervise.py`,
  the call into supervision in `mulebox/worker/agent.py`, CLI `runner-hook`.
- Agent "manage": `mulebox/runners/manage.py`, `mulebox/runners/github.py`,
  `mulebox/runners/release.py` (download + verify), CLI `runner add|list|remove` and
  `runner register|unregister`, `install/systemd/mulebox-runner@.service`, the install.sh
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
- `GITHUB_JOB_STATUS` unset -> `passed` (GitHub may not set it for hooks; the GitHub run is
  the authority for the job's real result).
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
