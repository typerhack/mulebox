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

## 1. Everyday use (project already set up)

| You want to | Run |
| --- | --- |
| the project's full gate | `mulebox check` |
| another job from `.mulebox.yml` | `mulebox check <job>` (e.g. `mulebox check test`) |
| a one-off command (one test file, one script) | `mulebox run -- <cmd> <args...>` |
| see how this project works with mulebox | `mulebox contract` |
| see the queue | `mulebox queue` |
| list every project that has run on this build machine | `mulebox projects` |
| open the web dashboard (for a person; holds a tunnel until Ctrl-C) | `mulebox dashboard open` |
| read a job's log again | `mulebox logs <job-id>` |
| stop a job | `mulebox cancel <job-id>` (Ctrl-C on a running `check` also cancels) |

- The job's output arrives on stdout as if it ran locally; mulebox's own status lines go to
  stderr and start with `mulebox:`.
- The exit code is the job's exit code. mulebox's own codes:

| Code | Meaning | What to do |
| --- | --- | --- |
| 0 / job's code | the job ran; read its output like a local run | fix the code if it failed |
| 2 | config or usage error (`.mulebox.yml`, not in a git worktree) | fix the config |
| 3 | build machine unreachable, or the live view lost the connection | tell the user; if a job id was printed, `mulebox logs <id>` later |
| 4 | the build machine refused the request, for example no machine offers what `needs` asks for | read the message; tell the user |
| 75 | the job was interrupted on the build machine (restart, crash) | run it again once |
| 124 | the job hit `timeout_min` | look for a hang; raise `timeout_min` only if the work really takes that long |
| 130 | cancelled | - |

- mulebox uploads a snapshot of your worktree: tracked and untracked files that git does
  not ignore. Secret files are never uploaded (`.env*`, `.envrc`, `.netrc`, `.npmrc`,
  `.secret/`, `secrets/`, `*.pem`, `*.key`, ssh keys). If a job needs a value from such a
  file, give it a throwaway value in `.mulebox.yml` `env:` instead.
- If you edit files while a job runs, mulebox prints a "stale" warning at the end: the
  result belongs to the snapshot, not to your current files. Run it again.
- Jobs wait in one queue shared by every project and by GitHub Actions. Waiting is normal;
  do not cancel and resubmit to "speed it up". A line such as
  `queued, position 1; waiting: no build machine for this job is online` is different:
  nothing will start until a person fixes it, so tell the user.

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
   - **Databases are per job.** Every database name, prefix or schema must include
     `${MULEBOX_JOB_SLUG}` (the job id in lowercase with `_`, safe in database names).
     Env values may use `${MULEBOX_JOB_ID}`, `${MULEBOX_JOB_SLUG}` and earlier `env:`
     entries; nothing else is expanded and no shell runs. Never point a job at a database
     that already exists on the build machine.
   - Values are strings: quote numbers (`CI: "1"`). `PATH`, `HOME`, `USER`, `SHELL` and
     `MULEBOX*` cannot be set.
   - **No real secrets.** Use obviously fake values (`ci-secret-at-least-32-characters`).
     If a check truly needs a real credential, stop and ask the user.
   - **Toolchain versions** must match what the project uses (`.nvmrc`, `packageManager`,
     `engines`, the CI workflow). If the build machine lacks one, the job fails with a
     message naming `mulebox toolchain install <name> <version>`; ask the user to run it.
   - `setup` runs before every job in the same shell; keep it to dependency install.
   - A job may span several lines (`check: |`). The first line that fails ends it, as in a
     GitHub Actions `run:` step.
   - If the project runs containers for its checks, use `compose:` (section 2a). Never run
     `docker compose up` in a job: nothing would remove the containers afterwards.
3. **Verify it.** Run `mulebox check`. It must pass on a clean main branch, with the same
   result as the project's CI. Then prove a broken change fails the same way it would
   locally: add an obvious type error, run `mulebox check typecheck` (or `check`), confirm
   it fails with that error and a non-zero exit code, and **revert the change**.
4. **Add the agent rule** to the project's AGENTS.md (or CLAUDE.md if that is where the
   rules live). Show the user the exact text before committing it:

```markdown
## Builds and tests: use mulebox

Run builds, type checks, lint and tests through mulebox, never directly on this machine:

- full gate: `mulebox check`
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
when the job ends, however it ends; pulled images and build layers stay as cache.

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
- **`.env*` files are never uploaded**, so `env_file: .env.ci` fails on the build machine. Move
  those throwaway values into `env:` and `environment:`.
- **Root-owned files** in the checkout are fine: mulebox cleans them up.
- **`up --wait` needs every service to stay up** and, if it has a healthcheck, become healthy.
  A service that exits on purpose should be a `depends_on` with
  `condition: service_completed_successfully`, or moved into a job command. A healthcheck
  that depends on `setup` having run cannot pass, because setup comes after.
- When a job fails, its log ends with the state and last lines of its containers.

These are refused with the reason, because they reach past the job:

- the host's namespaces (`network_mode`, `pid`, `ipc`, `uts`, `userns_mode`, `cgroup` set to
  `host`) and those of containers outside the project (`container:...`). `service:...` of the
  same project is fine;
- `privileged`, privileged hooks, `devices`, `device_cgroup_rules`, `gpus`, `cgroup_parent`,
  `runtime`, `provider`, `use_api_socket`, `external_links`;
- `cap_add` beyond Docker's defaults and `SYS_NICE`, `SYS_PTRACE`, `IPC_LOCK`; `security_opt`
  other than `no-new-privileges`;
- `volumes_from` of anything but a service of the project;
- builds with `network: host`, `privileged`, `entitlements`, `ssh` or `cache_to`;
- `external` networks, volumes, secrets or configs; networks not on the bridge driver;
  volumes not on the local driver or on a host device;
- the Docker socket, or a folder holding it, in any bind or file secret; writable bind
  mounts outside the checkout, and any bind outside it whose source does not exist on the
  build machine (mulebox never creates one there).

`container_name`
is dropped, with a note in the log; use the service name. Put CI-only changes in a separate
compose file rather than changing how the project runs locally.

If mulebox says no build machine offers `docker`, tell the user: a person has to add it
to the build machine's `capabilities`.

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
