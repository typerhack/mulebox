# mulebox for coding agents

This file is written for AI coding agents. A user may tell you: "read mulebox's
docs/agents.md and set this project up" or "use mulebox here". Follow it step by step.

mulebox runs a project's builds, type checks, lint and tests on a Linux build machine
through one queue, instead of on the laptop you are working on. You keep editing, reading,
searching and using git locally; heavy commands go through `mulebox`.

## 0. Check that mulebox works

    mulebox --version
    mulebox queue

If either fails (command not found, exit code 3 "build machine unreachable"), **stop and
tell the user**. Do not fall back to running heavy commands locally on your own.

Then read what applies here:

    mulebox contract          # add --json for stable keys

It prints this project's jobs and commands, what stays local, how git fits in, what is
never uploaded, the exit codes and the rules. It needs no network and is generated from
`.mulebox.yml`, so it is always current; if it disagrees with this file, trust it. Outside
a project set up for mulebox it says so, and section 2 is your next step.

If you came here through the mulebox skill: it says which contract schema it was written
for, and the contract's first line gives the current one. If the contract's is higher, tell
the user the skill is behind and that `mulebox skill update` fixes it. Never update the
skill yourself. `mulebox skill status` and `mulebox doctor` show the same.

Before a project's first job, and after changing `toolchain`, `needs` or compose files:

    mulebox doctor            # add --json for stable keys

It uploads nothing and creates no job. It validates `.mulebox.yml`, says whether a machine
offers the project's toolchain versions and capabilities (and which versions it has
instead), runs the worker's compose policy on the project's compose files, and warns when
the client and the machine run different versions of mulebox. The compose check needs no
Docker and sees only what the files show: not values with variables, and not files named by
`include` or `extends`, so a clean result does not promise the worker will agree. It exits 0
when a job can run, also with warnings, 1 when it would not, 2 without a usable
`.mulebox.yml` or client config, and 3 when the machine is unreachable.

## 1. Everyday use (project already set up)

| You want to | Run |
| --- | --- |
| the project's full gate | `mulebox check` |
| another job from `.mulebox.yml` | `mulebox check <job>` (e.g. `mulebox check test`) |
| leave a long job running and go on working | `mulebox check [job] --detach`, also `mulebox run --detach -- <cmd...>` |
| follow a job without its log | `mulebox events --job <job-id> --json` |
| see one job's state once | `mulebox status <job-id>` (add `--json`) |
| get a detached job's result | `mulebox wait <job-id>` |
| a one-off command (one test file, one script) | `mulebox run -- <cmd> <args...>` |
| see how this project works with mulebox | `mulebox contract` |
| check the project and the machine before submitting anything | `mulebox doctor` |
| see the queue | `mulebox queue` |
| list every project that has run on this build machine | `mulebox projects` |
| open the web dashboard (for a person; holds a tunnel until Ctrl-C) | `mulebox dashboard open` |
| read a job's log again | `mulebox logs <job-id>`; old logs expire on the build machine, and it says so when one has (`mulebox status <job-id>` still has the result) |
| see why a job failed, without its whole log | `mulebox logs <job-id> --summary` |
| stop a job | `mulebox cancel <job-id>` (Ctrl-C on a running `check` also cancels) |

- The job's output arrives on stdout as if it ran locally; mulebox's own status lines go to
  stderr and start with `mulebox:`.
- A failed job ends with a short summary on stderr: the failed stage if known, the exit
  code, and its last lines without progress output and container logs. It is the last thing
  printed, after the container logs, so the end of the output is where the error is. Read that
  first; open the full log only if it is not enough.
- The exit code is the job's exit code. mulebox's own codes:

| Code | Meaning | What to do |
| --- | --- | --- |
| 0 / job's code | the job ran; read its output like a local run | fix the code if it failed |
| 2 | config or usage error (`.mulebox.yml`, not in a git worktree) | fix the config |
| 3 | build machine unreachable, or the live view lost the connection | tell the user; if a job id was printed, `mulebox wait <id>` later |
| 4 | the build machine refused the request, for example no machine offers what `needs` asks for | read the message; tell the user |
| 5 | the job could not start (toolchain missing, compose file refused), so no project code ran | not a failed check: read the reason in the log; `mulebox doctor` checks most causes |
| 75 | the job was interrupted on the build machine (restart, crash) | run it again once |
| 124 | the job hit `timeout_min` | look for a hang; raise `timeout_min` only if the work really takes that long |
| 130 | cancelled | - |

- **Long jobs run detached.** `mulebox check --detach` uploads the snapshot, prints the job
  id on stdout and exits; the upload has to finish first, the queueing does not. The job then
  does not depend on your session: an attached job is cancelled about 5 minutes after its
  client disappears, a detached one is not. `mulebox wait <job-id>` returns what an attached
  `check` would have: the same log on stdout, the same failure summary and the same exit
  code, whenever you ask, also after the job ended. From the project it also gives the stale
  warning. Ctrl-C on `wait` stops the waiting, not the job. `timeout_min` still applies, a
  dead build machine still ends it `interrupted`, and `mulebox cancel` still stops it. If you
  no longer want it, cancel it: nobody else will.
- **Watching a job.** `mulebox events --job <job-id> --json` prints one JSON line per state
  change and no log text, and exits when the job ends, with the job's exit code. A dropped
  connection is resumed for 30 minutes with nothing repeated and the final line kept; if it
  gives up (exit 3), run it again, a finished job still gives its result. In Claude Code, the
  Monitor tool can follow this command, so each line reaches you while you do other work.

```json
{"estimate_s": 214.0, "event": "queued", "job_id": "job-...", "position": 2, "state": "queued", "v": 1, "waiting_for": null}
{"event": "started", "job_id": "job-...", "machine": "build-1", "state": "running", "v": 1}
{"duration_s": 212.4, "event": "finished", "exit_code": 2, "job_id": "job-...", "outcome": "failed", "stage": "setup", "state": "finished", "v": 1}
```

  Ignore events and keys you do not know; an event per stage and `check_in` events are planned.
  In `finished`, `stage` is where a job that ended badly failed, null when that is not known.
  `exit_code` is the code the command exits with (5 could not start, 124 for a timeout,
  130 cancelled, 75 interrupted). `mulebox status <job-id>` answers once and exits 0 whatever the job did.
- mulebox uploads a snapshot of your worktree: tracked and untracked files that git does
  not ignore. Secret files are never uploaded (`.env*`, `.envrc`, `.netrc`, `.npmrc`,
  `.secret/`, `secrets/`, `*.pem`, `*.key`, ssh keys). If a job needs a value from such a
  file, give it a throwaway value in `.mulebox.yml` `env:` instead. The exception is a
  template tracked in git (`.env.example`, `.env.sample`, `.env.template`, `.env.dist`),
  which is uploaded so `setup` can build `.env` from it. Keep real values out of templates.
- If you edit files while a job runs, mulebox prints a "stale" warning at the end: the
  result belongs to the snapshot, not to your current files. Run it again.
- Jobs wait in one queue shared by every project and by GitHub Actions. Waiting is normal;
  do not cancel and resubmit to "speed it up". While queued, `check` prints its position and,
  once a job has at least 3 passed runs with stage rows, an estimate of how long it runs once
  started (the median of its last 20 with the same command). There is no estimate of the time in line. At position 2 or later,
  or for a job that usually takes 5 minutes or more, it suggests `--detach` for next time. A
  line such as
  `queued, position 1; waiting: no build machine for this job is online` is different:
  nothing will start until a person fixes it, so tell the user.

A job goes through stages: `prepare`, `environment`, `images`, `services`, `setup`, `command`,
`cleanup`. `mulebox status <job-id>` shows them; with `--json`, `steps` has when each started
and ended, its exit code and the last line of a failed one. The first four need no action
from a project. `usual` is what passed runs of this job with this command took, whole and per
stage, or nothing if there is no history yet. Say "usually about 4 min" if that helps. It is
not progress, so never turn it into a percentage. Once a job has ended badly, the reply, the
failure summary and the `finished` event name the failed stage.

Image pull progress is summarised, so a quiet log during a pull is normal (section 2a).

A build machine keeps a job's log for 30 days unless its owner chose otherwise. After that
`mulebox logs <id>` says the log has expired, and the job's result and stages remain.

The coordinator and the workers must be upgraded together: stage rows, toolchain reports and
detached jobs need both. If `mulebox doctor` reports different versions, tell the user.

## 2. Setting up a project (`.mulebox.yml`)

Do this once per repository, on a branch, following the project's own rules for commits
and pull requests.

1. **Learn how the project is checked today.** Read its README, AGENTS.md / CLAUDE.md,
   `package.json` scripts (or Makefile, composer.json, pyproject.toml), and the CI
   workflow in `.github/workflows/`. Find: the one command that is the full gate, the
   install step, the Node/pnpm (or other) versions, the services it needs (database,
   Docker), and the environment variables CI sets.
2. **Write `.mulebox.yml`** in the repository root:

```yaml
project: example-app            # letters, digits, '.', '_', '-'
toolchain:                      # exact versions, quoted
  node: "22.22.3"
  pnpm: "11.22.0"
needs: []                       # worker capabilities, e.g. [playwright]
env:                            # throwaway CI values only, never real secrets
  CI: "1"
  NEXT_TELEMETRY_DISABLED: "1"
  APP_URL: http://localhost:3000
  DATABASE_URL: mongodb://localhost:27017/example_app_ci_${MULEBOX_JOB_SLUG}
setup: pnpm install --frozen-lockfile
jobs:
  check: pnpm check              # required: the full gate
  test: pnpm exec vitest run
  typecheck: pnpm typecheck
timeout_min: 30
exclude: [reports/]             # extra paths never uploaded (secrets are excluded already)
```

   Rules for the values:
   - **Databases are per job.** A database a job shares with anything else, such as one
     already running on the build machine or reached by address, needs `${MULEBOX_JOB_SLUG}`
     (the job id in lowercase with `_`, safe in database names) in every name, prefix or schema.
     A database in a compose service of the job itself is that job's alone and gone afterwards,
     so its name is free, and a project's fixed name works.
     Env values may use `${MULEBOX_JOB_ID}`, `${MULEBOX_JOB_SLUG}` and earlier `env:`
     entries, in the order the file lists them; nothing else is expanded and no shell runs. An
     entry that uses a later one is a config error, caught before any upload (exit 2, also from
     `mulebox contract` and `mulebox doctor`). A name the file does not explain may come from the
     machine's `job_env`, so `doctor` warns about it; if nothing sets it the job cannot start
     (exit 5). Never point a job at a database
     that already exists on the build machine.
   - Values are strings: quote numbers (`CI: "1"`). `PATH`, `HOME`, `USER`, `SHELL` and
     `MULEBOX*` cannot be set.
   - **No real secrets.** Use obviously fake values (`ci-secret-at-least-32-characters`).
     If a check truly needs a real credential, stop and ask the user.
   - **Toolchain versions** must match what the project uses (`.nvmrc`, `packageManager`,
     `engines`, the CI workflow). If the build machine lacks one, the job fails with a
     message listing the versions it has and naming `mulebox toolchain install <name>
     <version>`. Switch to a listed version only if it matches the project; otherwise ask
     the user to run the install.
   - `setup` runs before every job in the same shell; keep it to dependency install.
   - A job may span several lines (`check: |`). The first line that fails ends it, as in a
     GitHub Actions `run:` step.
   - If the project runs containers for its checks, use `compose:` (section 2a). Never run
     `docker compose up` in a job: nothing would remove the containers afterwards.
3. **Verify it.** Run `mulebox doctor`, then `mulebox check`. It must pass on a clean main branch, with the same
   result as the project's CI. Then prove a broken change fails the same way it would
   locally: add an obvious type error, run `mulebox check typecheck` (or `check`), confirm
   it fails with that error and a non-zero exit code, and **revert the change**.
4. **Add the agent rule** to the project's AGENTS.md (or CLAUDE.md if that is where the
   rules live). Show the user the exact text before committing it:

```markdown
## Builds and tests: use mulebox

Run builds, type checks, lint and tests through mulebox, never directly on this machine:

- full gate: `mulebox check`, or `mulebox check --detach` for a long run, then
  `mulebox wait <job-id>`
- one job from `.mulebox.yml`: `mulebox check <job>`
- one-off command (single test file, script): `mulebox run -- <cmd...>`

Keep git, search, reading files and diffs local. If mulebox is unreachable (exit 3), stop
and tell the user instead of running the command locally. See mulebox's docs/agents.md.
```

5. **Commit** `.mulebox.yml` and the rule on a branch and open a pull request if that is
   the project's workflow. Report to the user: the jobs you defined, the check time, and
   anything you could not set up.

## 2a. Projects that need containers (`compose:`)

```yaml
project: example-app
compose: [docker-compose.yml, docker-compose.ci.yml]   # merged in this order; needs docker
env:
  APP_URL: http://127.0.0.1:${MULEBOX_PORT_API_8000}   # service api, container port 8000
setup: docker compose exec -T api composer install
jobs:
  check: docker compose exec -T api php artisan test --parallel
  migrate: docker compose exec -T api php artisan migrate --seed --force
timeout_min: 30
```

mulebox starts the containers (`docker compose up --detach --wait`) before `setup`, inside
the job. Every job gets its own containers, networks and volumes. All of them are removed
when the job ends, however it ends; pulled images and build layers stay as cache. An image
the project builds gets a tag of this job only, whatever `image:` says, so reach it through
the service name (`docker compose exec`), not by a tag in `docker run`.

- **`docker compose exec -T <service> ...`** works as it is, from any folder. Use `-T`: a job
  has no terminal. Do not add `-f` or `-p`, and do not run `up` or `down`.
- **Ports always move.** Each published port is bound to `127.0.0.1` on a port chosen for the
  job, whatever the compose file says, and the log names it. Use the variable
  `MULEBOX_PORT_<SERVICE>_<PORT>` in `env:` or in commands, never a number from the compose
  file. Letters are uppercased and other characters become `_`; UDP ports end in `_UDP`.
  Between containers nothing changes: use the service name and the container port.
- **`env:` reaches compose**, for `${VAR}` in compose files, as it reaches commands. A service
  only sees what its `environment:` passes on, as always. `UID` and `GID` are set, so
  `user: "${UID}:${GID}"` works.
- **The build machine's `job_env` reaches services** (settings such as `NODE_OPTIONS` for a
  slow network), and your commands. A value in a service's `environment:` or `env_file:`
  wins; a value in `.mulebox.yml` `env:` replaces it for the whole job, and may add to it
  with `${NODE_OPTIONS}`. It does not reach a `RUN` line of an image build.
- **Open files.** A service with no `ulimits.nofile` of its own gets 65536, soft and hard:
  containers can start at 1024, and a database under test then dies with "Too many open
  files". A value in the compose file always wins, so set one if a service needs more.
- **`.env*` files are not uploaded**, apart from tracked templates, so `env_file: .env.ci`
  fails on the build machine. Move those throwaway values into `env:` and `environment:`.
- **Root-owned files** in the checkout are fine: mulebox cleans them up.
- **`up --wait` needs every service to stay up** and, if it has a healthcheck, become healthy.
  A service that exits on purpose should be a `depends_on` with
  `condition: service_completed_successfully`, or moved into a job command. A healthcheck
  that depends on `setup` having run cannot pass, because setup comes after.
- When a job fails, its log ends with the state and last lines of its containers.
- Images are pulled and built by `docker compose up --no-start`, then `up --detach --wait`
  starts them, so a job's stages can tell the two apart. Layer-by-layer pull progress is left
  out of the log. It shows `Image ... Pulled` and `mulebox: at least 640 MB of image layers
  downloaded`, every 100 MB. No news for a while during a pull is normal on a slow network.

These are refused with the reason, because they reach past the job:

- the host's namespaces (`network_mode`, `pid`, `ipc`, `uts`, `userns_mode`, `cgroup` set to
  `host`) and those of containers outside the project (`container:...`). `service:...` of the
  same project is fine;
- `privileged`, privileged hooks, `devices` (also under `deploy.resources`), `device_cgroup_rules`,
  `gpus`, `cgroup_parent`,
  `runtime`, `provider`, `use_api_socket`, `external_links`;
- `cap_add` beyond Docker's defaults and `SYS_NICE`, `SYS_PTRACE`, `IPC_LOCK`; `security_opt`
  other than `no-new-privileges`;
- `volumes_from` of anything but a service of the project;
- builds with `network: host`, `privileged`, `entitlements`, `ssh` or `cache_to`;
- `external` networks, volumes, secrets or configs; networks not on the bridge driver;
  volumes not on the local driver or on a host device;
- anything under `/run` or `/var/run`, any Unix socket, or a folder holding a known runtime's socket (Docker, containerd, CRI-O,
  podman, k3s, BuildKit), in any bind or file secret, read-only or not; writable bind
  mounts outside the checkout, except this job's package caches (section 2a-1), and any bind
  outside it whose source does not exist on the build machine (mulebox never creates one
  there).

This stops a CI file's assumptions from reaching past the job. It does not contain a hostile
project: a job can run any command and Docker access is root-equivalent, so a build machine
is only for projects its owner trusts.

`env:` may not set what changes how a job starts: `BASH_ENV`, `ENV`, `SHELLOPTS`, `BASHOPTS`,
`PS4`, `IFS`, `GCONV_PATH` and `BASH_FUNC_*` for any project, and for a `compose:` project
`LD_PRELOAD`, `LD_AUDIT`, `LD_LIBRARY_PATH` and
`COMPOSE_*` and `DOCKER_*`, except `DOCKER_BUILDKIT` and `DOCKER_DEFAULT_PLATFORM`. A job that
sets one fails at the start, whichever client sent it.

`container_name`
is dropped, with a note in the log; use the service name. Put CI-only changes in a separate
compose file rather than changing how the project runs locally.

If mulebox says no build machine offers `docker`, tell the user: a person has to add it
to the build machine's `capabilities`. If it says the machine's mulebox is too old, it has to
be upgraded. `compose-v1` in `needs` comes with `compose:`; nobody sets it.

## 2a-1. Package caches

Installs are slow on a slow network, and a job starts from nothing. Ask for a cache in `needs`
and downloads stay on the build machine between jobs of this project. It is off unless the
project asks.

```yaml
needs: [cache-pnpm, cache-composer]
```

| `needs` | Folder on the build machine | Set for commands on the machine |
| --- | --- | --- |
| `cache-pnpm` | `<cache>/packages/<project>/pnpm` | `pnpm_config_store_dir`, `npm_config_store_dir`, `MULEBOX_CACHE_PNPM` |
| `cache-composer` | `<cache>/packages/<project>/composer` | `COMPOSER_CACHE_DIR`, `MULEBOX_CACHE_COMPOSER` |

Commands on the machine need nothing more. **A container sees a cache only if the compose
file mounts it**, and that mount is yours to write. `MULEBOX_CACHE_<TOOL>` is the folder, and
it is the one writable path outside the checkout that compose may mount. Put this in a
CI-only compose file:

```yaml
# docker-compose.ci.yml, listed last in `compose:`
services:
  api:
    user: "${UID}:${GID}"
    environment:
      COMPOSER_CACHE_DIR: /cache/composer
    volumes:
      - ${MULEBOX_CACHE_COMPOSER}:/cache/composer
  web:
    user: "${UID}:${GID}"
    environment:
      pnpm_config_store_dir: ${MULEBOX_CACHE_PNPM}
    volumes:
      - ${MULEBOX_CACHE_PNPM}:${MULEBOX_CACHE_PNPM}
```

- **Replacing an external cache volume.** mulebox refuses `external: true`, and a cache does
  not change that, because every project on the machine would share such a volume. Add the
  `cache-*` need, and in a CI-only compose file mount the cache on the same container path:

  ```yaml
  # docker-compose.yml, unchanged: composer_cache:/root/.composer/cache, external: true
  # docker-compose.ci.yml
  services:
    api:
      volumes:
        - ${MULEBOX_CACHE_COMPOSER}:/root/.composer/cache
  ```

  With `compose: [docker-compose.yml, docker-compose.ci.yml]` the later mount replaces the
  volume on that path, and Compose drops the volume once no service uses it, so the check
  passes and the project's main file stays as it is. Every service that used the volume
  needs this. If mulebox still says the volume is external, one of them was missed.
- **pnpm: use the same path in the container and on the machine**, as above, if `setup` runs
  on the machine and a job runs in a container, or the other way round. pnpm records its
  store's path in `node_modules`. When the path differs, it throws `node_modules` away and
  installs again. For the same reason, use one toolchain version for both.
- **Who writes.** Run the service as root or as `"${UID}:${GID}"`. Any other user cannot write
  to the folder and the install fails with a permission error. After a compose job
  mulebox hands what root wrote back to the machine's user.
- A pnpm install across mounts copies packages instead of linking them. That is slower than
  a link and far faster than a download.
- A service that uses one of these variables fails at the start if the project does not ask
  for that cache: the variable is empty. For running the same file on a laptop, give it a
  default, as in `${MULEBOX_CACHE_PNPM:-/tmp/example-app-pnpm}`.

**What sharing means.** Every branch of a project on a machine shares its cache: every job of
this project on this machine, on any branch, reads and
writes the same folder, and the job's log says so. A job can therefore leave something behind
that a later job of this project gets: a change on a branch can reach the next run of main. pnpm
checks each package against the hash in the lockfile; Composer checks a download only where
the lockfile has a hash, and many entries have none. Another project has its own folder, and
compose refuses a mount of it. A project's name comes from its `.mulebox.yml`, so two
projects with the same `project:` share a cache. As everywhere on a build machine, this is
for projects its owner trusts, not a defence against a hostile one: a job with Docker
access can reach any folder.

If a cache looks wrong, a person clears it on the build machine, with no job of that project
running: `mulebox cache clear <project>`. `mulebox cache list` shows the sizes. Caches are
never cleaned by themselves. Do this only when the user asks: do not ssh in yourself.

## 2b. Browser tests (Playwright)

Add `playwright` to `needs`. The build machine must offer it: that means a person has
installed the system libraries browsers use. mulebox then sets `PLAYWRIGHT_BROWSERS_PATH` to
one folder on the build machine, so a browser is downloaded once, not for every job.

```yaml
needs: [playwright]
env:
  BASE_URL: http://127.0.0.1:${MULEBOX_PORT_API_8000}
jobs:
  e2e: pnpm exec playwright install chromium && pnpm exec playwright test
```

`playwright install chromium` does nothing once that version is there, so keep it in the
job: it is what keeps the version in step with the project's lockfile. Do not use
`install --with-deps`: it needs root, which a job does not have. Browsers run on the
build machine, not in a container, so they reach containers through `127.0.0.1` and the
`MULEBOX_PORT_...` variable. Read the URL from the environment in `playwright.config`, and
do not let Playwright's `webServer` start something on a fixed port.

## 3. Moving GitHub Actions to mulebox runners

A repository's CI can run on the build machine through the same queue. Do this only when
the user asks for it.

1. **Register a runner** (needs `gh` logged in with admin rights on the repository):

       mulebox runner register --repo <owner>/<repo>

   It installs a runner on the build machine as a service with the labels `self-hosted`,
   `Linux`, `X64`, `mulebox`.
2. **Point the workflow at it.** In `.github/workflows/*.yml`:

```yaml
jobs:
  check:
    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '["self-hosted","Linux","X64","mulebox"]') }}
```

   With the `CI_RUNS_ON` repository variable the user can switch back (for example to
   `["ubuntu-latest"]`) without a code change.
3. **Linux differences to check:**
   - The build machine is Linux, not macOS: Docker is Docker Engine, not Docker Desktop.
     Containers that write into the checkout leave root-owned files. Run them with the
     runner's user id (`user: "${UID}:${GID}"`) or clean them up in a final step: `compose:`
     cleanup covers mulebox jobs, not GitHub runner jobs.
   - Steps that install system packages with `sudo` will fail: the runner has no sudo.
     Ask the user to install such packages on the build machine once.
   - Use per-run database names, as in section 2.
   - Do not hardcode the build machine's paths or host name in the workflow.
4. **Verify** with a pull request: the job is picked up by the mulebox runner (its log
   starts with `mulebox: waiting for a build slot` or goes straight on), passes, and a
   deliberately failing commit fails.
5. If the project had a runner on the laptop before, tell the user it can be stopped; do
   not remove it yourself.

## 4. Reporting what mulebox could not handle

If mulebox itself got in the way, and the user wants it reported:

    mulebox feedback draft <job-id> --summary "what happened" > draft.md   # sends nothing
    mulebox feedback post draft.md                                         # opens the issue

Add `--log` to the draft to include the job's last lines. Leave out the job id when no job
is involved, such as an unreachable machine. **Show the user the draft and get their
approval before posting.** Read it yourself too: file names and code in logs cannot be
recognised automatically. `post` needs `feedback_repo` in `client.toml`, and it refuses a
file that still holds something the scrub would remove.

## 5. Things you must not do

- Do not run heavy commands locally when mulebox is unavailable; tell the user.
- Do not ssh into the build machine to change, install or delete things.
- Do not put real secrets, real hosts or personal paths into `.mulebox.yml` or workflows.
- Do not use or modify databases that already exist on the build machine.
- Do not raise `timeout_min` above what the work needs, and do not cancel other people's
  jobs.
