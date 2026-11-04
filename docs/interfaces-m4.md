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
  `docker compose up --detach --wait`, then `setup`, then the job.
- `worker/compose_file.py`: `published_ports(model)`, `rewrite(model, project, labels,
  assigned, checkout) -> (model, notes)`; `compose_policy.check(model, checkout)` raises
  `ComposeError` for what is refused.
- `worker/ports.py`: `PortPool(free, pick)`: `take(job_id, names)`, `release(job_id)`. Range
  20000-29999, random start, proven free by a bind on 127.0.0.1, held until the job is clean.
- A compose problem found before the unit starts fails the job with the reason in its log.

## Browser tests

`worker/runspec.py`: `build(machine, job_id, claim, src, log_path, bins) -> (RunSpec, notes)`
holds what a job's capabilities add. With `playwright` in `needs`, the job gets
`PLAYWRIGHT_BROWSERS_PATH=<cache>/playwright` (`NodePaths.browsers_dir`), created through
safepath. A value in `env:` cannot override it. No other job gets the variable, so
projects that rely on Playwright's default folder are not affected.
