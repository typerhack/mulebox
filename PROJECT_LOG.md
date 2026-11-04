# Project log

Every change to this repository is logged here, newest first, in the same commit as the
change, together with the version bump it causes. Rules: [AGENTS.md](AGENTS.md) (Versioning).

Entry format:

    ## <version> - <YYYY-MM-DD> - <patch|minor|major>
    - what changed and why (one line each)

## 0.40.1 - 2026-11-04 - patch
- A build machine gets `~/.local/bin/mulebox`, so the command has the same name there as on
  the laptop. A real file of that name is left alone.
- The theme button has a third setting: it steps through system, light and dark and shows
  the current one. System was the default but could not be chosen again once set.

## 0.40.0 - 2026-11-04 - minor
- `ports: [vite]` on a job gives it `MULEBOX_PORT_VITE`, a free port for a process of the job
  itself, such as a dev server a browser test starts, from the pool compose ports use and held
  until the job is cleaned up. The names travel in `env` like the compose list, so the store and
  the protocol stay as they are; a worker older than this refuses the job at the start, exit 5.
- `env:` entries built on another job's port are left out for a job that does not have it.
- Contract schema 7: `job_settings` has `ports`.

## 0.39.0 - 2026-11-04 - minor
- A job in `.mulebox.yml` may be a mapping with `run`, its own `setup` (or `setup: false`) and
  `compose: false`, so a quick job skips containers it does not use. A plain command keeps the
  top-level defaults, and `mulebox run` always does. `env:` entries that need a compose port are
  left out for a job without containers, and `check` says which. Client only: `setup` and the
  compose list already went with every job.
- Contract schema 6 with `project.job_settings`.
- `submit.py` split: what a job is on the wire is in `client/job_body.py`.

## 0.38.0 - 2026-11-04 - minor
- The dashboard warns the user: a warning triangle, the word `unattended` and the time left on the
  job, on its machine in both places, and a count on the Queue tab. A job's page says what happens
  and gives the commands to take it back or end it. The time left counts down in the browser.
- A stopped job reads `stopped: unattended` in the queue, its page and history, with the reason
  on its page, and stays out of the Failed tab. History rows now carry `shown_state`.
- The job page's `Timeout` is now `Check-in every`.

## 0.37.0 - 2026-11-04 - minor
- `timeout_min` is a check-in now, not a hard limit: every `timeout_min` a running job reports its
  time, stage, last output and machine readings, as a `check_in` event and a warning in `check`
  and `wait`. A watched job has no limit; `mulebox status` shows its activity and who watches.
- A detached job nobody watches is unattended. `wait` and `events` take it back, also from older
  clients. Stopped after 15 minutes without output, CPU or network (`unattended_idle_min`) or
  at 24 hours whatever it does (`unattended_max_hours`, queued jobs too), both `[limits]` in
  node.toml and saved to `meta` when the service starts.
- A stop shows as `stopped: unattended`, exit 76, reason in `stop_reason`. On the wire it stays
  `cancelled`, so older peers keep working. 124 only comes from a worker older than 0.37.
- The agent is warned by an `unattended` event, `status`, `wait` and on stderr of any command run
  from the project; `--json` output is untouched. `mulebox queue` and the live view show `!`, a
  line per job and a line on top. `claim_ok` carries `limits: "coordinator"`, without it the
  worker keeps the hard limit. Store schema 8: `stop_reason`, `activity`, `active_at`.
- Contract schema 5 with `time_limits`.

## 0.36.7 - 2026-11-04 - patch
- Docs from real project reports: a hardcoded database address and `network_mode: service:...`,
  Playwright `--with-deps` in a project's own scripts, `COMPOSE_PROJECT_NAME` in CI scripts, and
  git-based checks staying local because a job has no git history. The contract's git section
  says the last one as well.

## 0.36.6 - 2026-11-04 - patch
- `mulebox feedback draft`: the report of a title cut at the first `;` could not be reproduced;
  a test now pins that a title keeps its punctuation. What the code did cut was a long first
  line at exactly 100 characters, in the middle of a word. It now cuts at a word, and the
  summary below the title stays whole.

## 0.36.5 - 2026-11-04 - patch
- Checked that the failure summary follows the container logs: it does, on stderr once the log
  has ended. Only the stale and expired-log lines could still come after it, so they now come
  first and the summary is the last thing printed by `check`, `wait` and `logs -f`.

## 0.36.4 - 2026-11-04 - patch
- The contract's database rule said every name needs `${MULEBOX_JOB_SLUG}`. That is for a
  database a job shares. A database in a compose service of the job is that job's alone, so a
  project's fixed name works; agents.md says the same.

## 0.36.3 - 2026-11-04 - patch
- An `env:` entry using a later one is a config error on the client: exit 2 before any upload,
  from `check`, `run`, `contract` and `doctor`. It used to reach the worker, where the job
  could not start. A name the file does not explain may come from the machine's `job_env`, so
  `doctor` warns and the worker still decides (exit 5).

## 0.36.2 - 2026-11-04 - patch
- `env:` entries are read in file order, as the docs say. They were not: JSON objects are
  sorted on the wire and in the store, so an entry using an earlier one failed whenever the
  names sorted the other way. The client now sends the order as `env_order`, stored beside
  `env` (schema 7) and given to the worker with the claim. An older client sends none and
  gets the sorted order it always had.

## 0.36.1 - 2026-11-04 - patch
- A stage mark counts only at the end of a line: a job printing its own mark mid-line could
  record a false stage and lose the rest of that line (found by review).
- A test pins that `job_env` cannot move a path the worker sets, such as a cache.

## 0.36.0 - 2026-11-04 - minor
- Merged the jobs box redesign, built on its own branch as 0.26.0:
- Jobs box redesigned (M2.8): tabs Queue, Failed, Passed and Recent, each with a live
  count and showing one thing, the choice remembered per browser. One running and one
  waiting job were lost above twenty finished rows; the user could not see what was in the
  queue. Released runner slots and cancelled jobs are neither a pass nor a failure, so they
  are listed under Recent (and History) only, with no tab of their own; the old mixed list
  is gone, because it was the crowding.
- The Queue tab is the queue by machine: a lane per machine with what it runs and what
  waits for it, in real queue order. The queue stays one line: a job sits in a lane only
  when that machine is the one place it can run, jobs several machines could take wait in
  one shared list, and a job no machine fits is shown first as stuck with the
  coordinator's reason. Lanes carry only the machine's name and state beside its jobs:
  slots and capabilities stay in the Machines box, shown once.
- Machines box: a small CPU and memory meter per machine, on the load ramp of the big
  graphs. Rows carry `cpu_pct` and `mem_pct`, null until measured: today only the machine
  the dashboard runs on (its own sampler, matched by the node name); every other machine
  reads "no live data" until workers report their load (M5.3), with no page change needed
  then. The worker and the protocol are untouched.
- Job log: the note beside the log says "connecting", "connected, no output yet", "not
  connected, retrying" or "wrote no output" instead of leaving the box blank. A user saw a
  blank box for a running job with a large log; a browser's limit of about six connections
  per site over plain HTTP can hold the stream back when several tabs are open.
- A theme switch redraws the graphs at once with the new colours; they kept the old ones
  until the next sample.
- Dashboard queue rows carry `needs`, `can_run_on` and `waiting_for` on waiting agent jobs
  (`views.placement`, `needs.capable`); the queue fingerprint sees them, so a capable
  machine going offline redraws the queue.
- Ticking times are keyed by job id, not document order, so a tab or lane can never show
  another job's time.
- A viewer's first queue snapshot is built when it connects. It was the last published
  event, so a viewer opening the page minutes after the last change ticked on from stale
  elapsed times (found in headless Chrome: 15 minutes shown for a job 23 minutes in).

## 0.35.0 - 2026-11-04 - minor
- Merge of the agent tools (0.25.4 to 0.34.0, below) and the worker branch. The worker branch
  used 0.26.0 to 0.32.0 as well; its changes are logged here, under the one number they ship
  with, oldest last. Those commits keep their old numbers in git history.
- Schema: one sequence. 3 -> 4 worker toolchains and version, 4 -> 5 `jobs.detached`, 5 -> 6
  `job_steps`, with the `jobs_project` index. A test takes every old schema to the final one.
  A store left at schema 4 by a build of the worker branch alone lacks the worker columns: start
  that one afresh, this version cannot tell it from the agent tools' schema 4.
- `coordinator/history.py` is gone: `coordinator/usual.py` is the one source of what a job
  usually takes, so the queue estimate now reads the last 20 passed runs (was 10) with stage
  rows (jobs from before stages do not count). The estimate's rule stays in it: same command,
  at least 3 runs. `usual` in a `status` reply now keeps commands apart as well.
- The failed stage is real: `failed_step` reaches `status`, the `result` line and `finished`
  events as `stage`, for a job that ended badly. The failure summary and `events` show it. A job
  that could not start shows the stage it stopped in where its worker sent rows, else `start`.
- `mulebox status` lists a job's stages beside what is usual, without a percentage.
- `compose_policy.check(model, checkout: Path | None, shared=())`. With no checkout a cache
  folder counts as written, and `..` is worked out from the text, so `mulebox doctor` cannot be
  told less than the worker by a path that walks out of a cache or to a socket.
- The expired-log line uses the real default (`DEFAULT_LOG_DAYS`), and a test removes a log with
  the real retention code before reading it through the client.
- The contract (schema 4), the skill and docs/agents.md teach package caches, `job_env` in
  services, open files, stages and `usual`, pull summaries, log retention, and that the
  coordinator and workers are upgraded together.
- Old logs are removed: nothing did before. `[retention]` in node.toml has `log_days` (30) and
  `step_days` (365). The coordinator service sweeps at its start and hourly, through safepath,
  only in the logs folder and only for files named after a finished job.
- Test only: what the rewrite adds to services moved to a test file of its own.
- Image pull progress is collapsed in what is stored and streamed: a real log had over 27,000
  lines of it. Outcome lines and errors stay, and a line says how much has been downloaded.
  The amount is a lower bound and also goes on the stage's row. Compose prints no total
  without a terminal, so there is no percentage.
- `status` replies give `usual`: the median length of a project's job and of each stage over
  its last passed runs, or nothing without history. No percentage: a length from the past
  does not say how far a running job has come.
- Job steps: a new table in the coordinator's store, schema version 4, holds one row per stage
  of a job: start, end, exit code, bytes downloaded, failing line. The worker reports them in
  a new `steps` message; `status` replies list them. The time of a slow job could not be
  placed before. `environment` is a stage of its own, for what mulebox provides.
- A compose job runs `up --no-start` before `up --detach --wait`, so images and services are
  separate stages.
- A compose service with no `ulimits.nofile` of its own gets 65536 open files. A real `mongo`
  service died mid-test with "Too many open files": containers started at a soft limit of 1024.
- `job_env` of a build machine reaches every compose service. It only reached the `docker
  compose` process, so a machine's fix for a slow network missed installs in containers. What a
  service sets itself wins, and a project's `env:` value is the one that goes in.
- Package caches: `needs: [cache-pnpm]` or `[cache-composer]` keeps a project's downloads on the
  build machine between jobs, in `<cache>/packages/<project>/<tool>`. A real job downloaded the
  same 905 packages twice and never reached its check. Opt-in and per project, so a job can
  only affect later jobs of its own project; each log names the cache it used.
- A compose file may mount the job's own cache writable; that is the one such path outside
  the checkout, and an external volume stays refused. After a compose job the worker gives
  what root wrote in the cache back to its own user.
- `mulebox cache list` and `mulebox cache clear <project>` on a build machine.

## 0.34.0 - 2026-11-04 - minor
- `mulebox logs`, `logs --summary` and `wait` say when a job's log has expired, rather than
  printing nothing (M8.10). The job's row keeps `log_size` after the file is gone, which tells
  an expired log from an empty one. The exit code does not change: the job's result is intact.

## 0.33.0 - 2026-11-04 - minor
- `mulebox doctor` checks a project's compose files before any upload, with the worker's own
  policy (M8.9): an external volume, a host network or a writable mount outside the checkout
  fails at once, rather than after the job has waited through the queue.
  `compose_policy.check` takes no checkout for this: this machine's paths say nothing about
  the build machine's, so only what the files show counts. `client/compose_check.py` gives it
  the model `docker compose config` would print, as far as the files show it.

## 0.32.0 - 2026-11-04 - minor
- A job that could not start exits 5, not 1, and its outcome line says so: it ran no project
  code, so it must not read as a failed check (M8.8). `check`, `wait`, `events` and the
  summary all go through `report.exit_code_for`. The contract, docs/agents.md and the skill
  say what 5 means.

## 0.31.0 - 2026-11-04 - minor
- The skill ships inside the package; `skills/mulebox/SKILL.md` is a link to it (M8.7).
  `mulebox skill install`, `update` and `status` handle every Claude config folder:
  `~/.claude`, `~/.claude-work` and `CLAUDE_CONFIG_DIR`. `cp -R skills/mulebox` no longer works.
- SKILL.md states the contract schema it was written for and the contract prints the current
  one (now 3, also raised when the skill must teach something new), so an agent can tell the
  user its skill is behind. It never updates itself. `mulebox doctor` reports it, and a test
  ties the two numbers.
- The contract's first rule is again the one against running heavy work locally; a test holds
  it there.

## 0.30.0 - 2026-11-04 - minor
- While queued, `check` suggests `--detach` once, at position 2 or later or for a job that
  usually takes 5 minutes or more (M8.6).
- A labelled estimate of how long a job runs once started: the median of its last 10 passed
  runs with the same command, from 3 runs up (`coordinator/history.py`), on `status_ok` and in
  `queued` events. design.md promised an estimate the code did not have; it now says what
  there is, and that the time in line is not estimated.

## 0.29.0 - 2026-11-04 - minor
- `mulebox events --job <id> --json`: one JSON line per state change, no log text, resumes a
  dropped connection with nothing repeated, exits with the job's exit code (M8.5). It reads
  the coordinator's `watch` stream through `common/status.py`, so it is not a second event
  source. `watch` takes `log: false`; an older coordinator's log is ignored.
- `mulebox status <id>`: one job's state; `status` replies carry the job's facts for it.
- `status_ok` names the worker of an active job. `check` printed `running` without it.

## 0.28.0 - 2026-11-04 - minor
- `mulebox check --detach` (also `run --detach`) prints the job id once the job is queued and
  leaves it running; `mulebox wait <id>` returns what an attached `check` would have, whenever
  asked (M8.4). An agent sat blocked for the whole job.
- A detached job has no client to lose: `jobs.detached` (schema 5) and the client lease sweep
  skips it. The worker lease, the upload timeout, `timeout_min` and `cancel` still apply.
- A coordinator echoes `detached`; without the echo the client cancels the job and fails,
  because an older coordinator would have ignored the flag and cancelled it minutes later.
- A watch stream cut in the middle of a line, or ended without a result, now counts as a
  dropped connection, so the client reconnects. It failed with exit 4 before.
- `logs -f`, `wait` and the like retry a dropped connection for 30 minutes, and fail at once
  when the machine cannot be reached at all.

## 0.27.0 - 2026-11-04 - minor
- `mulebox doctor`: before any upload, validates `.mulebox.yml`, says whether a machine offers
  the project's toolchain versions and capabilities, and warns when client and machine
  versions differ (M8.3). A missing toolchain showed only after submission.
- Workers report their toolchains and version with every claim (`worker/advert.py`, one call
  in `worker/agent.py`), kept in `workers` (schema 4); a new `machines` request reads them.
  A coordinator too old for it still gives its version through `mulebox version`.

## 0.26.0 - 2026-11-04 - minor
- A failed job ends with a short summary on stderr: stage if known, exit code, and its last
  lines without progress output and container logs (M8.2). `mulebox logs <id> --summary`
  prints it without the log, reading only the tail; `status` replies carry `log_size` for
  that. An agent read a huge log to find one line.
- The worker's two log notes the summary looks for are shared constants in `common/status.py`
  (one line each in `worker/agent.py` and `worker/compose_job.py`).

## 0.25.4 - 2026-11-04 - patch
- A missing toolchain error lists the versions the machine has (M8.1). It only named the
  install command, so an agent had no alternative to offer. Small change in
  `worker/toolchains.py`.

## 0.25.3 - 2026-11-04 - patch
- A template tracked in git (`.env.example`, `.sample`, `.template`, `.dist`) is now uploaded:
  a real project builds `.env` from one in `setup` and could not start without it. Untracked
  templates, real `.env` files and a project's own `exclude` stay out.

## 0.25.2 - 2026-11-04 - patch
- License: MIT, chosen by the user (M6.1). `LICENSE`, the README and the package metadata.

## 0.25.1 - 2026-11-04 - patch
- Docs: M2.7 status after a real compose job under full load on a build machine.

## 0.25.0 - 2026-11-04 - minor
- Dashboard redesigned as a live monitor: boxes that fill the window, per-core meters, CPU
  and memory history, disk meters, machines with slot squares, and one jobs list. The page
  was a task list before; the user wanted to see the machine at a glance.
- One theme over the whole page, with a sun and moon switch remembered per browser. The
  sign-in page follows the system setting, because it may not load scripts.
- Drawing stops while the tab is hidden, and two graphs replace nine.

## 0.24.7 - 2026-11-04 - patch
- Test only: the dashboard snapshot test read an event stream once and sometimes saw two of
  its three events. It now reads until all three arrive.

## 0.24.6 - 2026-11-04 - patch
- Nothing under `/run` or `/var/run` may be bind-mounted from outside the checkout. A list of
  socket paths missed a rootless BuildKit socket in a user's run folder; sockets there have
  names no list can hold.

## 0.24.5 - 2026-11-04 - patch
- The loader names `LD_PRELOAD`, `LD_AUDIT` and `LD_LIBRARY_PATH` are refused only for a
  `compose:` project, the only place with a checked file to protect, and other `LD_*` names
  are not refused at all. 0.24.0 failed ordinary builds that set `LD_RUN_PATH`.

## 0.24.4 - 2026-11-04 - patch
- A service using a name from `build.tags` follows the job's private tag, as one using `image:`
  did. It kept the shared name, so it ran a stale image or pulled an unrelated one.

## 0.24.3 - 2026-11-04 - patch
- The coordinator adds `docker` and `compose-v1` to any job carrying compose files. Only the
  client did, so an older client's job could still reach an older worker.

## 0.24.2 - 2026-11-04 - patch
- A bind or file secret that is a Unix socket is refused by its file type, and a folder holding
  a known runtime's socket by a list: Docker, containerd, CRI-O, podman, k3s, BuildKit. Only
  Docker's was known, and a read-only mount does not stop anyone talking to a socket.

## 0.24.1 - 2026-11-04 - patch
- Devices asked for through `deploy.resources` are refused, as `devices:` and `gpus:` already were.

## 0.24.0 - 2026-11-04 - minor
- Environment names that change how a job starts are refused, on the client and on the worker
  (`common/env_rules.py`): `BASH_ENV` and its like for every job, `COMPOSE_*` and `DOCKER_*` for
  a compose project. `BASH_ENV` ran project code before `up`, which could replace the checked
  file. `up` is the first line of the script, so nothing of the project runs before it now.
- design.md and agents.md say the boundary plainly: this stops a CI file's assumptions from
  reaching past the job, and does not contain a hostile project.

## 0.23.1 - 2026-11-04 - patch
- `tools/drill_compose.py`: a drill against a real Docker daemon, since the tests use a fake one
  and cannot show that generated files make resources teardown can find.
- M4 done, with what passed on a real machine and what was not run, in docs/phases.md.

## 0.23.0 - 2026-11-04 - minor
- `[job_env]` in node.toml: environment for every job on a machine, for what the machine
  needs and no project should have to know. Below a project's `env:`. Node's 250 ms limit per
  address made npm fail near 3 s on a slow network; `docs/install.md` has the setting.
- Troubleshooting says how bridges were fixed in real use, as a NetworkManager setting.

## 0.22.1 - 2026-11-04 - patch
- Port allocation probes the protocol a port is published on. It always tried TCP, so a UDP
  service on the chosen port was missed and the job failed with "address already in use".

## 0.22.0 - 2026-11-04 - minor
- A `compose:` job needs `compose-v1`, which a worker reports by itself. A worker from before
  compose offering `docker` used to claim such a job, ignore the compose file list and run
  its commands against the machine. It is now refused, with "upgrade the build machine".
  Deploy workers before clients.

## 0.21.3 - 2026-11-04 - patch
- Cleanup runs beside the worker's loop. It ran inside it, so a stuck Docker daemon could stop
  heartbeats past another job's lease, and cancels and runner supervision with them. The
  cleaning job heartbeats too, and the worker waits for cleanups when it stops. `compose
  config`, which still runs in the loop, gets a timeout that stays inside a lease.

## 0.21.2 - 2026-11-04 - patch
- A built image gets a tag only its job has, whatever `image:` and `build.tags` say; services
  using that image follow. Cleanup removes that tag by name, without force, not the image
  by id, so a tag someone else put on the same image survives.

## 0.21.1 - 2026-11-04 - patch
- A read-only bind outside the checkout must already exist, and gets `create_host_path: false`.
  Compose would otherwise create the folder on the build machine, and nothing removes it.

## 0.21.0 - 2026-11-04 - minor
- `worker/compose_policy.py` holds what a compose model may not do, and refuses more: `volumes_from`
  outside the project, `container:` namespaces, `uts`, `userns_mode` and `cgroup` on the host,
  `devices`, `cap_add` beyond a short list, `security_opt`, the Docker API, `provider`, `runtime`,
  privileged hooks and builds, non-bridge networks, non-local volumes, and any bind of a
  folder holding the Docker socket. Review found these went straight through.

## 0.20.1 - 2026-11-04 - patch
- M4 status from the real drills: M4.2 done, M4.1 and M4.3 built with what is still open.
  Troubleshooting entry for NetworkManager detaching Docker's bridges, which blocks services
  reaching each other on an affected machine.

## 0.20.0 - 2026-11-04 - minor
- Jobs from `.mulebox.yml` run with `bash -e`. A multi-line job used to report only its last
  line, so failed migrations followed by a passing line counted as passed. A job relying
  on a line being allowed to fail now needs `|| true` on it.

## 0.19.0 - 2026-11-04 - minor
- `needs: [playwright]`: jobs share one browser folder in the cache root, so a browser is
  fetched once per machine. A worker offers the capability once a person has installed the
  system libraries, which takes root. `worker/runspec.py` keeps this out of the agent loop.

## 0.18.0 - 2026-11-04 - minor
- `compose:` works. mulebox merges the project's files with `docker compose config`, rewrites
  the result (`worker/compose_file.py`) and gives the job only that file, through
  `COMPOSE_FILE` and `COMPOSE_PROJECT_NAME`, so `docker compose exec -T` needs no flags.
  Containers start before `setup`, inside the job, so the timeout, cancel and redaction apply.
- Every published port moves to 127.0.0.1 on a port mulebox picks (`worker/ports.py`), named
  by `MULEBOX_PORT_<SERVICE>_<PORT>`, so jobs clash neither with each other nor with what
  else runs on the machine. `container_name` is dropped; networks and volumes are renamed.
- Refused, with the reason: host network, PID or IPC namespace, `privileged`, external
  networks and volumes, volumes on a host device, the Docker socket, writable binds outside
  the checkout.
- A failed job's log ends with the state and last lines of its containers.
- `mulebox contract` has a `compose` key. `config.py` split: `common/config_project.py`.

## 0.17.0 - 2026-11-04 - minor
- Docker cleanup: `worker/docker.py` is the one place that runs the docker CLI and refuses
  `prune` and `system` outright; `worker/docker_cleanup.py` removes only what a listing
  filtered on one job's exact labels returned, and repeats until that listing is empty.
- `worker/reclaim.py`: root-owned files in a job folder are given back to the worker's user
  by a locked-down throwaway container, then deleted through safepath. No sudo. It mounts
  only a folder `safepath.confirm_dir` proved to be inside the jobs root.
- `worker/cleaner.py`: Docker first, folder second, on every outcome, and recovery after a
  crash from both the job folders and the labels. A folder that cannot be removed no longer
  stops the worker from starting.

## 0.16.0 - 2026-11-04 - minor
- A job whose `needs` no worker offers no longer waits forever without a word: it is refused
  at submit with what to change, and a queued job that cannot start says why in
  `waiting_for`, shown by `mulebox check` and `mulebox queue`. Details: docs/interfaces-m4.md.
- `workers.OFFLINE_AFTER_S` and `is_online` moved out of the dashboard, which now shares them.

## 0.15.0 - 2026-11-04 - minor
- `services:` in `.mulebox.yml` is now a config error that says to use `compose:` or `env:`.
  It was parsed and printed by `mulebox contract`, but nothing ever started a service.
  Removed from the contract, whose `schema` goes to 2, and from the design doc's example.
- `compose:` files are checked on the laptop: safe relative names, no repeats, present in
  the project. A `compose:` project needs a worker with `docker`, and may not set
  `COMPOSE_FILE` or `COMPOSE_PROJECT_NAME` in `env:`. Running it comes in a later change.
- `common/compose.py`: the names and filters every Docker step is derived from.

## 0.14.1 - 2026-11-04 - patch
- Docs: README, docs/install.md and the node.toml template now say the LAN password is
  optional. No behaviour change.

## 0.14.0 - 2026-11-04 - minor
- `lan_password = false` turns off the dashboard's LAN sign-in, keeping the code and the
  range and Host rules. Requested by the user; the default stays true. `/healthz` also
  returns `sign_in`, which decides whether the page shows the sign-out button.

## 0.13.0 - 2026-11-04 - minor
- `mulebox projects` (M7.4): every project the coordinator has seen, worked out from its
  jobs. New `projects` message, additive, so the protocol version stays 1; an older
  coordinator refuses it with an error.
- No project registry: it would only be a second copy of `.mulebox.yml` and the job history.

## 0.12.0 - 2026-11-04 - minor
- `mulebox feedback draft` and `post` (M7.3): agents report what mulebox could not handle as
  GitHub issues. Drafting is local; `post` needs `feedback_repo` and refuses a file the
  scrub would still change. Rules: docs/design.md, Agent feedback.
- `common/anonymize.py`: removes names, home folders, email and IP addresses and URLs, on
  top of `redact.py`.
- Screenshots from the original idea are dropped: they cannot be scrubbed automatically.

## 0.11.1 - 2026-11-04 - patch
- `skills/mulebox/`: an installable skill for coding agents (M7.2), which sends them to
  `mulebox contract` rather than copying it. Built here; installing it is the user's step.

## 0.11.0 - 2026-11-04 - minor
- `mulebox contract` (M7.1): tells an agent how this project builds, tests and uses git
  through mulebox. Generated from `.mulebox.yml` and the code's own tables, so there is no
  second copy; needs no network; `--json` has stable keys and a `schema` number.
- `ProjectNotFound`: a missing `.mulebox.yml` and a broken one are now told apart.
- docs/phases.md: new M7 for agent work, starting from the parking lot.

## 0.10.0 - 2026-11-04 - minor
- Dashboard machines panel (M2.6): every worker, online or offline, free slots and what it
  is running. New `GET /api/machines` and `machines` event.
- Job heartbeats now refresh a worker's `last_seen`. Claims stop while a worker is full, so
  a busy machine would otherwise have shown as offline for its whole job.
- Free slots are counted from active jobs, because the stored value is stale during a job.
- `coordinator/workers.py`: worker storage moved out of store.py, which neared 300 lines.

## 0.9.0 - 2026-11-04 - minor
- `lan` mode is now plain HTTP by default; HTTPS is the new optional `lan_tls = true`. User's
  decision: on a trusted home network, a browser warning on every visit is worse than no
  encryption, and installing a certificate on each device is not worth it.
- The password and range rules now follow the listener a request arrived on, not TLS.
  Without this, dropping TLS would have left the LAN port with no sign-in.

## 0.8.0 - 2026-11-04 - minor
- `lan` dashboard mode (M2.4): HTTPS on a configured address with a password, for devices
  on the LAN. The SSH tunnel keeps working. Set up with the new `mulebox dashboard cert`,
  `password` and `firewall` commands. New node.toml keys: `lan_address`, `lan_port`.
- `lan_range` must now be a private network, and `lan` mode is IPv4 only.
- Self-signed certificate marked CA, because phones only fully trust those, with name
  constraints so it is valid for one address. No new Python dependency.
- Firewall: mulebox prints a script for the operator instead of running anything as root;
  one nftables table for one port, leaving ufw, Docker and VPN clients alone.
- `mulebox-dashboard` no longer restarts on exit 2 (configuration), and a failed bind exits
  1 so that it retries. `/healthz` also returns `lan`.
- docs/phases.md: new M2.6 machines panel (next after M2.4), new M5.3 per-machine metrics.

## 0.7.1 - 2026-11-04 - patch
- docs/phases.md: parking lot ideas from the user: agent contract, installable skill, agent
  feedback through GitHub issues, project registration. No behaviour change.

## 0.7.0 - 2026-11-04 - minor
- Web dashboard (M2.1-M2.3, `local` part of M2.4): `mulebox dashboard open` on the laptop,
  service `mulebox-dashboard` on the coordinator machine. Queue, live log, history, CPU per
  core, memory, disk, Docker. Read-only and bound to 127.0.0.1; plain HTML and JS, no CDN.
  Contract: docs/interfaces-m2.md. New dependency: aiohttp.
- `common/status.py`: one status model for the terminal view and the dashboard.
- Found in real use and fixed before release: `ssh -L` joined a shared `ControlMaster` and
  exited, leaving a forward nobody held (the tunnel is now its own connection); a browser
  filter list blocked a script named `logview.js`, which blanked the page (renamed, and the
  page now says what to check if its scripts never run).
- README no longer claims LAN access, which is not built yet.

## 0.6.5 - 2026-11-04 - patch
- M3.3 done. A runner recovers from a hard kill by itself (GitHub drops the old session
  after ~3 min). Reboot drill passed with an agent job running and a CI job waiting; sudden
  power loss was not tested. Recovery times are in docs/interfaces-m3.md.

## 0.6.4 - 2026-11-03 - patch
- docs/phases.md: M3.1 and M3.2 done; M3.3 drill results (overlap, cancelled run, runner
  crash passed; GitHub session conflict after a hard kill and the reboot drill still open).
  Repository CI is now 16 s warm (was 47 s). M2 started on branch m2-dashboard.

## 0.6.3 - 2026-11-03 - patch
- Faster repository CI: tests run in parallel (`pytest-xdist`, `-n auto`; 23 s -> 5 s on
  the laptop), the venv is kept in the runner tool cache and rebuilt only when
  `pyproject.toml` changes. A parametrized protocol test now collects in a fixed order
  (it iterated a set, which xdist rejects).

## 0.6.2 - 2026-11-03 - patch
- Fixes from the first CI run on a mulebox runner (Linux, Python 3.12.3, the minimum):
  - `test_stream_early_stop_reaps_process` expected stderr closed; since 0.5.1 reap leaves
    a pipe to its still-waiting reader (another process held it on Linux). Test corrected.
  - GitHub does not tell hooks the job's result, so a released runner slot showed as
    "passed". Queue entries now carry `kind`; `mulebox queue` shows runner slots as
    `released` (the real result is on GitHub).

## 0.6.1 - 2026-11-03 - patch
- Repository CI (`.github/workflows/ci.yml`): the test suite on a mulebox runner by default,
  switchable with the `CI_RUNS_ON` repository variable. First real use of M3.

## 0.6.0 - 2026-11-03 - minor
- M3 GitHub runners, built in parallel on two branches:
  - Slot reservations: runner job-started/completed hooks reserve a slot pinned to the
    worker in the same FIFO queue as agent jobs (`reserve`, `acquire`, `release`,
    `runner_jobs`); the worker supervises runners and releases a crashed runner's slot
    after 60 s. Store schema 2 with an in-place migration.
  - Runner management: `mulebox runner register|unregister --repo owner/name` on the
    laptop (token from `gh`, sent on stdin), `mulebox runner add|list|remove` on the build
    machine (latest actions/runner release, checksum verified, `mulebox-runner@` user
    unit). The token never appears in argv or logs.
- `.mulebox.yml` `env:` for throwaway CI values; `${MULEBOX_JOB_ID}` / `${MULEBOX_JOB_SLUG}`
  and earlier entries expand, no shell. Store schema 3.
- docs/agents.md: a guide for coding agents (everyday use, setting a project up, moving
  GitHub Actions to mulebox runners); linked from the README.
- Shared download/verify code in `mulebox/common/download.py`.

## 0.5.3 - 2026-11-03 - patch
- docs/interfaces-m3.md: contract for GitHub runners (slot reservations through runner
  hooks, supervision, runner install from the laptop), so M3 can be built in parallel.
- `mulebox/runners/` package stubs wired into the CLI.

## 0.5.2 - 2026-11-03 - patch
- Client lease 120 s -> 300 s, and the client keeps reconnecting the live view for up to
  4 min (24 tries, 10 s apart): a real build machine on Wi-Fi dropped off for ~3 min, which
  would have cancelled a healthy job.
- After giving up on the live view, the client says the job keeps running and how to
  read its result (`WatchLost`), instead of the wrong "the job was not run".
- docs/phases.md: M1.6 done (real project passes, broken commit fails like locally); M1
  complete.

## 0.5.1 - 2026-11-03 - patch
- Fixes found by running M1.5 / M1.8 / M1.9 on a real build machine:
  - Ctrl-C took up to 2 minutes: closing an ssh pipe waited on a reader thread still
    blocked on it. `ssh.reap` no longer closes a pipe a live thread is reading.
  - A crashed worker's jobs stayed "running" until the 120 s worker lease ran out. The
    first claim after a worker start now carries `restarted: true` and the coordinator
    interrupts the jobs that worker still held (`recovery.release_worker`).
  - An ssh process killed by a signal counts as a lost connection (`SSHUnavailable`), so
    the watch stream reconnects instead of failing.
- docs/phases.md: M1.5, M1.8 and M1.9 done.

## 0.5.0 - 2026-11-03 - minor
- M1.4 coordinator (`mulebox/coordinator/`): SQLite store (WAL, `BEGIN IMMEDIATE`),
  atomic claim with cluster slots, idempotent submit, client and worker leases, restart
  recovery, upload staging with hash check and size cap, logs, `rpc` / `rpc-upload` /
  `rpc-download`, the watch stream, `coordinator serve`.
- M1.5 worker (`mulebox/worker/`): claim loop, safe workspace extraction plus a local git
  commit, systemd and subprocess executors, log tailing through the redactor, heartbeats
  and cancel, recovery of orphan units and job folders, node/pnpm toolchain install.
- M1.6 / M1.7 client (`mulebox/client/`): snapshot with built-in secret excludes, upload,
  submit, live log, exit codes like a local run, Ctrl-C cancel, stale warning, `queue`
  (with a live view), `logs`, `cancel`.
- M1.8 install (`install/`, `tools/deploy.sh`, docs/install.md): build-machine install as
  two systemd user services; never deletes, never uses sudo.
- Integration: worker local link wired to the coordinator; one shared line cap
  (`protocol.MAX_LINE_BYTES`); ssh helpers made public instead of reached into; worker
  heartbeat 3 s so a cancel lands in seconds; finished status replies carry the duration;
  `.envrc` and `.netrc` added to the secret excludes.
- Verified end to end on one machine with a fake ssh: pass, fail (same exit code),
  `mulebox cancel`, Ctrl-C (exit 130 in 1 s, no processes or folders left).
- docs/interfaces-m1.md: decisions made during the build.

## 0.4.1 - 2026-11-03 - patch
- docs/interfaces-m1.md: contract for the coordinator, worker, client and install script
  (M1.4 - M1.8), so they can be built in parallel. M1 simplifications recorded there (full
  snapshot instead of a build-machine clone, `rpc` opens SQLite directly).
- Protocol: message types `queue`, `queue_ok`, `logs`, `watch`.
- Package stubs `client/`, `coordinator/`, `worker/` with `commands.register`; the CLI
  dispatches to each subcommand's handler.

## 0.4.0 - 2026-11-03 - minor
- M1.3 `mulebox/common/safepath.py` (+ `roots.py`, `mounts.py`): the only code that
  deletes. Roots validated once (no `/`, home, system folders or overlaps; device and inode
  recorded). Deletion and creation anchored on directory descriptors with `O_NOFOLLOW`;
  the walk never follows symlinks, never leaves the root's mount (Linux mount ids from
  `/proc/self/mountinfo` and fdinfo, macOS `st_dev` + `ismount`), refuses mount points.
  Permission failures raise `RemovalDenied`; no escalation in this module.
- Tests cover symlink swaps mid-check and mid-walk, simulated mounts, prefix lookalikes,
  fd leaks; also run on Linux in a container.
- Known gaps: a directory renamed out of the root by someone with write access mid-delete;
  same-device mounts undetectable on macOS; real mounts only simulated in tests.
- README: rerun the editable install after a VERSION bump.

## 0.3.0 - 2026-11-03 - minor
- M1.2 shared modules in `mulebox/common/`, built in parallel to docs/interfaces.md:
  - `ids.py`: prefixed ULIDs (`job-...`), validation, timestamps.
  - `log.py`: idempotent setup of the `mulebox` logger, text or JSON lines.
  - `config.py` + `config_reader.py`: `.mulebox.yml`, `client.toml`, `node.toml`, strict
    validation (unknown keys, ranges, CIDR, ssh targets); errors name file and field.
  - `protocol.py`: versioned JSON-line messages, required body fields per type, job state
    machine (no self-transitions; finished is terminal).
  - `ssh.py`: argv-only subprocess, `--` before the `shlex.join` remote command, exit 255
    as `SSHUnavailable`, `RemoteError` / `RemoteTimeout`, streaming without deadlocks.
  - `redact.py`: known secrets and token patterns blanked; `StreamRedactor` catches secrets
    split across chunks.
- PyYAML 6.0.3 pinned as the first runtime dependency.
- docs/interfaces.md: additions found while building (see "Decisions made in M1.2").
- Known gaps: duplicate YAML keys are not detected; `decode` has no line-size cap (the
  reader must cap it); `RemoteError.stderr` is raw and must be redacted by callers.

## 0.2.1 - 2026-11-03 - patch
- docs/interfaces.md: the API contract for the shared modules (ids, log, config, protocol,
  ssh, redact, safepath), so they can be built in parallel.
- `mulebox/common/` package with the base `MuleboxError`.

## 0.2.0 - 2026-11-03 - minor
- M1.1 package skeleton: `pyproject.toml` (Python 3.12+, setuptools 84.2.1, version read
  from VERSION), `mulebox` CLI entry point with `--version` / `version`, pytest 9.2.0 as the
  pinned dev dependency, tests for the CLI and version source.
- File-size rule enforced in code: `tools/check_line_counts.py` warns above 300 lines and
  fails at 500; the test suite runs it on the whole repository.
- README: development section (venv, install, tests).

## 0.1.0 - 2026-11-03 - minor
- Project created from the design work in a private setup repo: README, design, roadmap
  (docs/phases.md), versioning and project-log rules, agent rules.
- Design reviewed by an external model (core queue, dashboard, multiple machines); the
  adopted changes are part of docs/design.md.
- Groundwork measured on a real setup (M4 Pro laptop vs a 2014 4-core i7 on Wi-Fi): the old
  machine ran two real CI suites 1.8x and 3.5x slower than the laptop, but 2-3x faster than
  GitHub-hosted runners, with the laptop left idle. Basis for "offload, then queue".
