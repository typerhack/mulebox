# Interfaces for M4 (Docker Compose projects)

Contract added on top of [interfaces-m1.md](interfaces-m1.md). Design: [design.md](design.md).

## Needs nobody offers

`coordinator/needs.py`. Before 0.16.0 a job whose `needs` no worker offered waited in the
queue without a word, for as long as its client lived.

- `submit` replies `error` with code `no_worker` when workers are known and none offers the
  job's `needs`, offline ones included. The message names each machine and what it offers,
  and says what to change. The client exits 4. A repeated `idempotency_key` still returns
  its job. Before any worker has been seen nothing is refused.
- A queued agent job that cannot start now carries `waiting_for` (text) in `status_ok`,
  `queue_ok` entries and the `watch` stream, which re-sends when it changes. Reasons: no
  worker connected yet, every capable worker offline, or no worker offers the needs any
  more. Reservations never carry it: they are pinned to their machine. Both fields are
  additive, so the protocol version stays 1.
- `mulebox check` prints `queued, position 1; waiting: <reason>`; `mulebox queue` prints the
  reason on a line under the job. `workers.OFFLINE_AFTER_S` is the one definition of
  offline, shared with the dashboard's machines panel.

## Docker cleanup

- `worker/docker.py`: `Docker(runner).run(*args, env=, cwd=, timeout_s=)` returns stdout or
  raises `DockerError` with redacted stderr; `.lines()` for listings. Any argument equal to
  `prune` or `system` is refused before anything runs. `DockerMissing`: no docker command.
- `common/compose.py`: `project_name(job_id)` is `mulebox-<job id in lowercase>`. Labels:
  `mulebox.job=<job id>`, `mulebox.worker=<node name>`. `job_filter`, `project_filter` and
  `worker_filter` give the `--filter` values; the first two refuse anything but a valid job id.
- `docker_cleanup.teardown(docker, job_id)`: lists containers, networks, volumes and images
  under `job_filter` and `project_filter`, removes those ids (`rm --force --volumes` for
  containers) and lists again, up to 3 passes; `DockerError` if anything stays. Images are
  listed by `repository:tag`, and only tags from `compose.image_name` go, with a plain
  `image rm`: no ids and no force. Another tag on the same image keeps it.
- Cleanup runs in a thread (`worker/background.py`). The loop keeps heartbeats, cancels and
  supervision going, and heartbeats the cleaning job too. On stop the worker waits up to
  60 s for it; what is left then is found by label on the next start.
- `docker_cleanup.labelled_jobs(docker, worker)`: job ids on containers, networks and volumes
  carrying `mulebox.job` and this worker's label.
- `worker/cleaner.py`: `Cleaner.clean(project, job_id, uses_docker)` tears down, then removes
  the folder; on `RemovalDenied` it runs the helper once and removes again. Raises to retry.
  `Cleaner.recover()` handles `leftover_job_dirs` and `labelled_jobs`, logs what fails, and
  goes on. Recovery tears down for every leftover folder, whatever kind of job it was.

## Root-owned files

`worker/reclaim.py`. The helper is `docker run --rm` of an Alpine image pinned by digest:
`--network=none --read-only --security-opt=no-new-privileges --cap-drop=ALL`, then
`--cap-add` of `CHOWN`, `DAC_READ_SEARCH` and `FOWNER`, `--pids-limit=16`, and one `--mount` of
type bind. It runs `chown -hR <uid>:<gid>` and `chmod -R u+rwX` on the mount, nothing else.
`safepath.confirm_dir(path, roots)` is what allows the mount: spelled under the root, no
`..`, not the root, no symlink in any component (opened one by one with `O_NOFOLLOW`), no
mount at, below or above it inside the root. The root passed is the jobs root alone, and a
comma in the path is refused because it would end the `--mount` value.

## Compose jobs

- `.mulebox.yml`: `compose: [a.yml, b.yml]`, files next to it, in Compose's merge order.
  Implies `docker` and `compose-v1` in `needs` (`ProjectConfig.all_needs`). A worker reports
  `compose-v1` by itself in `claim` when it offers docker (`compose.worker_capabilities`), so
  a worker from before compose can never claim such a job. The coordinator adds both to any
  job carrying `MULEBOX_COMPOSE_FILES` (`needs.required`), so an older client cannot avoid it. `env:` may not set `COMPOSE_FILE`,
  `COMPOSE_PROJECT_NAME` or `COMPOSE_PATH_SEPARATOR` in such a project.
- Wire: the client adds `MULEBOX_COMPOSE_FILES` (the names joined by `:`) to the job's `env`.
  The worker removes it and checks each name again (`compose.split_files`). No new column
  and no schema change, so an older coordinator keeps working against the same store.
- `worker/compose_job.py`: `prepare(docker, pool, job_id, worker, files, src, project_env,
  build_env) -> ComposeJob(extra_env, script, notes)`. Runs `docker compose config --format
  json` twice in `src` (see its docstring), writes `<job folder>/compose.mulebox.yml` (JSON,
  which is YAML) and sets `src` to mode 0755.
- Job env added: `COMPOSE_PROJECT_NAME`, `COMPOSE_FILE`, `UID`, `GID` (so `user: "${UID}:${GID}"`
  works), and one `MULEBOX_PORT_<SERVICE>_<PORT>` per published port, with `_UDP` for UDP.
  Non-alphanumerics in a service name become `_`. `env:` values may use `${MULEBOX_PORT_...}`.
- Script: fetch the helper image if missing (so cleanup cannot fail on it later), set an EXIT
  trap that prints `docker compose ps --all` and `logs --tail=50` when the script fails,
  `docker compose up --no-start` (pulls, builds, creates), `docker compose up --detach --wait`,
  then `setup`, then the job.
- `worker/compose_file.py`: `published_ports(model)`, `rewrite(model, project, labels,
  assigned, checkout) -> (model, notes)`; `compose_policy.check(model, checkout)` raises
  `ComposeError` for what is refused.
- `worker/ports.py`: `PortPool(free, pick)`: `take(job_id, names)`, `release(job_id)`. Range
  20000-29999, random start, proven free by a bind on 127.0.0.1, held until the job is clean.
- `job_env` names go to `prepare` as `machine_names`. Each service's `environment` gets those
  names with the value the job has for them, so `env:` of the project counts, and `$` doubled
  for Compose's second reading. A service's own value wins. Before 0.27.0 `job_env` reached
  only the `docker compose` process: `${VAR}` in a compose file, no container.
- `compose_file.rewrite` gives a service with no `ulimits.nofile` a limit of `OPEN_FILES`
  (65536), soft and hard. Other `ulimits` stay, and a service's own `nofile` is left as it is.
  The hard limit is kept at that value, not raised to what a daemon allows, because a daemon
  that may not raise limits, such as a rootless one, would refuse to start the container.
- A compose problem found before the unit starts fails the job with the reason in its log.

## Package caches

`common/package_cache.py` holds the names `cache-pnpm` and `cache-composer`; a worker reports
them by itself (`compose.worker_capabilities`). `worker/caches.py`: `for_job(paths, project,
needs) -> JobCaches(env, folders, notes)` makes `<cache>/packages/<project>/<tool>` through
safepath and proves it with `confirm_dir`, so a folder a job swapped for a symlink fails the
next job instead of being followed. `env` holds `MULEBOX_CACHE_<TOOL>` and the tool's own
settings, through `extra` of `build_env`, so `env:` cannot override them. `folders` goes to
`compose_policy.check(model, checkout, shared)`, which lets a writable bind through only if its
source resolves into one of them; `external` volumes are not touched by this.
`caches.give_back` runs in `Cleaner.clean` after teardown of a compose job, and so after a
crash too, with `reclaim.reclaim_cache`: the helper, on `<cache>/packages/<project>`, with the
cache root as the root. A failure there is logged, not retried. `caches.clear` and
`caches.listing` are `mulebox cache clear <project>` and `mulebox cache list`.

Reserved for an install step run by mulebox: a folder beside `packages/`, such as
`<cache>/installs/<project>/<key>`, with the key made from lockfile, toolchain and image.

## Job steps

One row per stage of a job, in the coordinator's store (`job_steps`, schema version 6, a table
added by `migrate.py` with no change to `jobs`). `seq` orders them. Raw logs stay files.

| Column | Meaning |
| --- | --- |
| `job_id`, `seq` | primary key; `seq` counts from 0 within a job |
| `stage` | `status.STAGES`: `prepare`, `environment`, `images`, `services`, `setup`, `command`, `cleanup` |
| `started_at`, `finished_at` | epoch seconds on the worker; `finished_at` empty while it runs, and for good if the job ended without its worker |
| `exit_code` | 0 for a stage followed by another; the job's code for its last; empty if stopped |
| `bytes_downloaded` | image layers, at least this much (see Image pulls in a log); empty if none were seen |
| `failing_line` | last line the stage printed, redacted, at most 500 characters, for `failed` or `timed_out` only |

- `prepare`: snapshot and workspace. `environment`: what mulebox provides, today toolchains,
  caches and the compose file; an install step run by mulebox belongs here too, separate from
  `setup` and the commands. `images`: `up --no-start`. `services`: `up --wait`.
- `command` is one row for a job, also when the job has several lines: they are one shell
  command, and splitting shell text at line breaks is not safe. A later version can add rows,
  since nothing assumes a stage appears once.
- `worker/steps.py`: `StepTracker`. The script prints `::mulebox-step:<marker>:<time>:<stage>`
  (`mulebox_step`, jobspec.py), a random marker per job, and the tailer removes those lines
  after redaction, before anything is stored. Keep `${` and `$$` out of the script: systemd
  expands them in a unit's command line.
- Wire: `steps` (worker to coordinator), body `job_id`, `attempt_id`, `steps` (at most 64 whole
  rows, replaced by `seq`), answered like `job_update`. It goes after the log, and before
  `result`. A report is not worth a retry after an `error` reply, so an older coordinator
  does no harm: the job runs, without rows. The protocol version stays 1.
- Read: `status_ok` of a `status` request has `steps`, the rows in order (empty for a job
  that has none). Inside the coordinator: `coordinator/steps.py`, `for_job(conn, job_id)`,
  which the dashboard can use with its read-only store. Pure helpers in `common/status.py`:
  `current_stage(job, steps)`, `step_duration_s(step, now)`, `failed_step(steps)`.
- `coordinator/usual.py`: `usual(conn, project, job, argv=None)` gives `{"runs", "job_s",
  "stages": {stage: seconds}}`, or None without history: medians over the last 20 passed runs
  that have rows. `for_job(conn, job)` limits that to the job's command. A `status` reply has it
  as `usual` (null without history). `estimate(job, typical)` is the same figure for a queued
  job with at least 3 such runs: `estimate_s` and `estimate_runs`, in `status` and the watch
  stream. It gives lengths, not progress: a client may say "usually about 4 min", and must not
  turn it into a percentage.
- `failed_step(steps)` reaches clients as `stage` (`coordinator/steps.py`, `failed_stage`), for
  outcomes `failed`, `timed_out` and `interrupted` only: a cancelled job has a non-zero exit
  code in its last stage and did not fail there. A job that left no such row has no `stage`.
- A stop or a cancel ends the job, whatever the stage (`timeout_min` too on a worker older
  than 0.37). The rows are enough to turn that into
  a warning later: they say how long each stage took on this project.

## Image pulls in a log

`worker/pullnoise.py`. After redaction, before storing and streaming, per-layer progress is
dropped: `Pulling fs layer`, `Waiting`, `Downloading`, `Verifying Checksum`, `Download complete`,
`Extracting`, `Pull complete`, `Already exists` on a line that starts with a 12-digit layer
id, and BuildKit's `#N sha256:... a / b` and `#N extracting sha256:...` lines without `done`.
Lines about images, networks and containers stay, as does anything else, errors and retries
included. In their place: `mulebox: at least 640 MB of image layers downloaded`, every 100 MB
and after each run of layer lines. The raw `out.log` keeps all of it until the folder goes.

What Compose prints without a terminal, seen on 5.6: `<layer> Downloading 2.097MB`, the amount
so far with no total, and the last piece of a layer is not printed. So bytes are a lower bound,
and no percentage exists. Compose 2 printed `12.3MB/45.6MB`, and that total is used where
present. `--progress json` on 5.6 has `current` and `total` per layer, but only for layers that
have started, so a whole-pull percentage would still be a guess, and the flag would need a
version check. Not used.

## Retention

`coordinator/retention.py`: `sweep(store, staging, now, log_days, step_days) -> (logs, rows)`,
run by the coordinator service at the start and every hour. `Staging.log_job_ids()` lists
regular files directly in `<staging>/logs`, named `<valid job id>.log`, so a symlink, a folder or
a foreign file is never a candidate. A log goes when its job is `finished` and `finished_at`
is older than `log_days`, through `Staging.remove_log` and so safepath. A log of an unknown or
active job stays. `job_steps` rows go after `step_days`. Rows in `jobs` are never removed.
`mulebox logs` of a job whose log has gone prints nothing; the job still shows in history.

## Browser tests

`worker/runspec.py`: `build(machine, job_id, claim, src, log_path, bins) -> (RunSpec, notes)`
holds what a job's capabilities add. With `playwright` in `needs`, the job gets
`PLAYWRIGHT_BROWSERS_PATH=<cache>/playwright` (`NodePaths.browsers_dir`), created through
safepath. A value in `env:` cannot override it. No other job gets the variable, so
projects that rely on Playwright's default folder are not affected.
