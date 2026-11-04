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
  containers) and lists again, up to 3 passes; `DockerError` if anything stays. Images found
  this way are the ones built for the job, with a tag only it uses.
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
