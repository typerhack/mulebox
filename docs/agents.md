# mulebox for coding agents

This file is written for AI coding agents. A user may tell you: "read mulebox's
docs/agents.md and set this project up" or "use mulebox here". Follow it step by step.
To test mulebox on a project and report back, see [agent-trial.md](agent-trial.md).

mulebox runs a project's builds, type checks, lint and tests on a Linux node
through one queue, instead of on the dev machine you are working on. You keep editing, reading,
searching and using git locally; heavy commands go through `mulebox`.

## 0. Check that mulebox works

    mulebox --version
    mulebox queue

If either fails (command not found, exit code 3 "node unreachable"), **stop and
tell the user**. Do not fall back to running heavy commands locally on your own.

Then read what applies here:

    mulebox contract          # add --json for stable keys

It prints this project's jobs and commands, what stays local, how git fits in, what is
never uploaded, the exit codes and the rules. It needs no network and is generated from
`.mulebox.yml`, so it is always current; if it disagrees with this file, trust it. Outside
a project set up for mulebox it says so, and section 2 is your next step.

If you came here through the mulebox skill: `mulebox contract` says on stderr when an
installed copy of the skill differs from this mulebox's, and its first line gives the contract
schema, which the skill names too. Either way, run `mulebox skill update`, then read the skill
again: the session loaded the old text. Tell the user. `mulebox skill status` and
`mulebox doctor` show the same.

Before a project's first job, and after changing `toolchain`, `needs` or compose files:

    mulebox doctor            # add --json for stable keys

It uploads nothing and creates no job. It validates `.mulebox.yml`, says if the folder is no git
repository with a commit yet, says whether a machine
offers the project's toolchain versions and capabilities (and which versions it has
instead), runs the worker's compose policy on the project's compose files, warns when the machine cannot
connect to a registry the project's images come from, and warns when the client and the
machine run different versions of mulebox. The compose check needs no
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
| the same inside a compose service | `mulebox run --in <service> -- <cmd> <args...>` |
| the same with no containers, install or setup | `mulebox run --bare -- <cmd> <args...>` |
| change a file on the machine and get it back, such as a lockfile | `mulebox run --take <path> -- <cmd> <args...>`, e.g. `mulebox run --in api --take api/composer.lock -- composer update --no-install vendor/pkg` |
| see how this project works with mulebox | `mulebox contract` |
| check the project and the machine before submitting anything | `mulebox doctor` |
| see the queue | `mulebox queue` |
| list every project that has run on this node | `mulebox projects` |
| open the web dashboard (for a person; holds a tunnel until Ctrl-C). `check`, `queue`, `status` and `doctor` print its address when the machine has one on the LAN: pass it to the user | `mulebox dashboard open` |
| read a job's log again | `mulebox logs <job-id>`; old logs expire on the node, and it says so when one has (`mulebox status <job-id>` still has the result) |
| see why a job failed, without its whole log | `mulebox logs <job-id> --summary` |
| stop a job | `mulebox cancel <job-id>` (Ctrl-C on a running `check` also cancels) |

- The job's output arrives on stdout as if it ran locally; mulebox's own status lines go to
  stderr and start with `mulebox:`.
- A failed job ends with a short summary on stderr: the failed stage if known, the exit
  code, and its last lines without progress output and container logs. Earlier lines that read
  as the failure, up to 6, stand above them, before a `[...]` line: a test runner's stack and
  totals can fill the last lines. It is the last thing
  printed, after the container logs, so the end of the output is where the error is. Read that
  first; open the full log only if it is not enough.
- `--take <path>` (repeat it for more files) copies a file back into your project once the
  command passed, written in place. Paths are relative to the folder with `.mulebox.yml`. It
  waits, so not with `--detach`; it never brings back a file mulebox never sends (`.env`, keys,
  `exclude:`); a file the command did not leave is named, and the exit code is then 1. Use it for
  lockfiles a package manager rewrites, rather than running the package manager locally.
- The exit code is the job's exit code. mulebox's own codes:

| Code | Meaning | What to do |
| --- | --- | --- |
| 0 / job's code | the job ran; read its output like a local run | fix the code if it failed |
| 2 | config or usage error (`.mulebox.yml`, not in a git worktree, no commit yet) | fix the config |
| 3 | node unreachable, or the live view lost the connection | tell the user; if a job id was printed, `mulebox wait <id>` later |
| 4 | the node refused the request, for example no machine offers what `needs` asks for | read the message; tell the user |
| 5 | the job could not start (toolchain would not install, compose file refused, images out of reach on the network), so no project code ran | not a failed check: read the reason in the log; `mulebox doctor` checks most causes |
| 75 | the job was interrupted on the node (restart, crash) | run it again once |
| 76 | `stopped: stuck`: it did nothing and nobody answered its question (section 1a) | not a failed check, it says nothing about the code: run it again and watch it |
| 124 | the job hit a hard `timeout_min`, which only a node older than 0.37 applies | look for a hang; a current machine sends check-ins instead |
| 130 | cancelled | - |

- **Long jobs run detached.** `mulebox check --detach` uploads the snapshot, prints the job
  id on stdout and exits; the upload has to finish first, the queueing does not. No job depends
  on your session: one whose client went away, attached or not, runs to its end, and its result
  waits for you. `mulebox wait <job-id>` returns what an attached
  `check` would have: the same log on stdout, the same failure summary and the same exit
  code, whenever you ask, also after the job ended. From the project it also gives the stale
  warning. Ctrl-C on `wait` stops the waiting, not the job. A dead node still ends it
  `interrupted`, and `mulebox cancel` still stops it. If you no longer want it, cancel it.
- **Watching a job.** `mulebox events --job <job-id> --json` prints one JSON line per state
  change, with no log text but for `last_line` in a `check_in`, and exits when the job ends, with the job's exit code. A dropped
  connection is resumed for 30 minutes with nothing repeated and the final line kept; if it
  gives up (exit 3), run it again, a finished job still gives its result. In Claude Code, the
  Monitor tool can follow this command, so each line reaches you while you do other work.

```json
{"estimate_s": 214.0, "event": "queued", "job_id": "job-...", "position": 2, "running_ahead": ["job-..."], "state": "queued", "v": 1, "waiting_for": null}
{"event": "started", "job_id": "job-...", "machine": "build-1", "state": "running", "v": 1}
{"cpu_pct": 212.5, "elapsed_s": 1800.2, "event": "check_in", "idle_s": 4.1, "job_id": "job-...", "net_kib_s": 0.3, "number": 1, "output_idle_s": 41.0, "last_line": "Compiling app", "stage": "command", "state": "running", "v": 1}
{"duration_s": 212.4, "event": "finished", "exit_code": 2, "job_id": "job-...", "outcome": "failed", "stage": "setup", "state": "finished", "stop_reason": null, "v": 1}
```

  `branch_busy` names the job holding this job's branch: a branch runs one job at a time, and
  other branches run beside it, so use a branch per task to work in parallel.
  `waiting_for` is set only when nothing can run the job; a job simply in line has `running_ahead`, the jobs on the machines now. `estimate_s` needs 3 past passed runs. A `stage` event comes as the job enters each stage. Ignore events and keys you do not know. In `finished`, `stage`
  is where a job that ended badly failed, null when that is not known. `exit_code` is the code
  the command exits with (5 could not start, 76 stopped, 124 for a hard timeout, 130 cancelled,
  75 interrupted). `outcome` can be `stopped`, then `stop_reason` says why. Questions are in
  section 1a. `mulebox status <job-id>` answers once and exits 0 whatever the job did.
- mulebox uploads a snapshot of your worktree: tracked and untracked files that git does
  not ignore. Secret files are never uploaded (`.env*`, `.envrc`, `.netrc`, `.npmrc`,
  `.git-credentials`, `.pypirc`, `.ssh/`, `.aws/`, `.secret/`, `secrets/`, `*.pem`, `*.key`,
  `*.p12`, `*.pfx`, ssh keys). If a job needs a value from such a
  file, give it a throwaway value in `.mulebox.yml` `env:` instead. The exception is a
  template tracked in git (`.env.example`, `.env.sample`, `.env.template`, `.env.dist`),
  which is uploaded so `setup` can build `.env` from it. Keep real values out of templates.
- If you edit files while a job runs, mulebox prints a "stale" warning at the end: the
  result belongs to the snapshot, not to your current files. Run it again. Paths in
  `ignore_changes:` (same patterns as `exclude:`) are still sent but do not count: an edit
  there, such as a changelog line, keeps the result, and `check` gives it back without a rerun.
  List only files no job reads: a test that reads a listed file would pass on old content.
- Jobs wait in one queue shared by every project and by GitHub Actions. Waiting is normal;
  do not cancel and resubmit to "speed it up". While queued, `check` prints its position and,
  once a job has at least 3 passed runs with stage rows, an estimate of how long it runs once
  started (the median of its last 20 with the same command). There is no estimate of the time in line. At position 2 or later,
  or for a job that usually takes 5 minutes or more, it suggests `--detach` for next time. A
  line such as
  `queued, position 1; waiting: no node for this job is online` is different:
  nothing will start until a person fixes it, so tell the user. The owner may have set order
  rules (a project's or a branch's level, fair turns, shortest first) or moved a job by hand;
  then `mulebox status`
  and `mulebox queue` add a `place:` line, and `--json` `place_reason` and `order`, saying why
  the job is where it is. The rules are the owner's: do not change them to get ahead.

A job goes through stages: `toolchain` (only when it installs a pinned one), `prepare`, `environment`, `images`, `services`, `install`, `setup`,
`command`, `cleanup`. `mulebox status <job-id>` shows them; with `--json`, `steps` has when each started
and ended, its exit code and the last line of a failed one. The first four need no action
from a project. `usual` is what earlier passed runs of this job with this command took, whole and per
stage, or nothing if there is no history yet. A run that lost its connection while fetching does not count. Say "usually about 4 min" if that helps. It is
not progress, so never turn it into a percentage. Once a job has ended badly, the reply, the
failure summary and the `finished` event name the failed stage.

Image pull progress is summarised, so a quiet log during a pull is normal (section 2a).

A node keeps a job's log for 30 days unless its owner chose otherwise. After that
`mulebox logs <id>` says the log has expired, and the job's result and stages remain.

The coordinator and the workers must be upgraded together: stage rows, toolchain reports and
detached jobs need both. If `mulebox doctor` reports different versions, tell the user.

## 1a. Time limits

No job has a time limit. A job that is working finishes, however long it takes, whether anyone
is there or not.

- **`timeout_min` is a question, not a limit.** Every `timeout_min` of a running job (default 30),
  `mulebox events` prints a `check_in` event, and an attached `check` or `wait` prints the same:
  elapsed time, stage, seconds since the last output and that line, the job's own CPU, and the
  machine's CPU and network, null when they cannot be read.
- **Answer it.** `mulebox ok <job-id>` says the job is fine, and `mulebox cancel <job-id>` stops
  it. `mulebox status <job-id>` shows the same at any time.
- **Only a stuck job stops.** That takes both: its question unanswered for one more
  `timeout_min`, and no activity for that long, or for 15 minutes if that is shorter
  (`unattended_idle_min` in `node.toml`). So with the default it is asked at 30 minutes and stopped
  at 60; with `timeout_min: 1`, at 1 and 2. It then shows `stopped: stuck`
  and exits 76, which is not a failed check: it says nothing about the code.
- **Activity** is the job's, not the machine's: new output, its own processes using at least 1% of
  a core, its compose services using at least a tenth of a core together, or their traffic
  reaching 4 KiB/s. A `docker run` or `docker build` of the job's own is seen only through its
  output. While a job cannot be measured, and during `images`, nothing counts as idle; such a job
  stops only after 24 hours with its question unanswered (`unattended_max_hours`).
- **A queued job is never stopped, and a job goes on if its client goes away**, however that
  happens. Ctrl-C and `mulebox cancel` stop it.
- **Three ways to wait:** follow it (`mulebox check`, or `mulebox events --job <job-id> --json`), be
  pinged when it ends (`mulebox check --detach`, then `mulebox wait <job-id>` as a background
  command), or check later (`mulebox status <job-id>`).
- **Results wait for you.** A job that finished with nobody following is reported once, on stderr,
  by your next `mulebox` command in the project, so `--json` output stays clean. Do not retest.
- **`mulebox check` does not repeat itself.** On the same files, uncommitted changes included,
  and the same settings, it gives the result of the last 24 hours with its exit code, or joins
  the same job if it is queued or running. A cancelled or stopped job does not count, nor does a failure from before a mulebox upgrade, which may have been a fault in mulebox. `--again`
  forces a run.
- **GitHub runner reservations** are not touched by any of this: GitHub owns those jobs.

## 2. Setting up a project (`.mulebox.yml`)

Do this once per repository, on a branch, following the project's own rules for commits
and pull requests.

1. **Learn how the project is checked today.** Read its README, AGENTS.md / CLAUDE.md,
   `package.json` scripts (or Makefile, composer.json, pyproject.toml), and the CI
   workflow in `.github/workflows/`. Find: the one command that is the full gate, the
   install step, the Node/pnpm (or other) versions, the services it needs (database,
   Docker), and the environment variables CI sets.
2. **Write `.mulebox.yml`** in the repository root. `mulebox init` writes a first version from
   the project's files, and `mulebox init --print` shows it without writing; then correct it
   with what step 1 found. It takes the compose files and the Node version the project's CI uses
   (`.github/workflows/`), and runs Composer and PHP tests in the compose service built from that
   folder. For an Xcode project or a Swift package it writes `xcodebuild test` or `swift test`
   (section 2c). It cannot know CI's environment variables. The fields:

```yaml
project: example-app            # letters, digits, '.', '_', '-'
toolchain:                      # exact versions, quoted
  node: "22.22.3"
  pnpm: "11.22.0"
  # xcode: "16.2"               # Mac nodes only; the node must have it, a job never installs it
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
timeout_min: 30                 # how often a running job checks in; not a limit (section 1a)
exclude: [reports/]             # extra paths never uploaded (secrets are excluded already)
ignore_changes: ["*.md", docs/] # sent, but an edit there keeps a passed result (below)
github_status: true             # post `check`'s result to the pushed commit on GitHub (below)
isolation: container            # run each job in a confined container (below); default none
image: ghcr.io/example/ci:1     # an isolated job's own image; default mulebox's
```

   `github_status: true` makes `mulebox check` post its result as the commit status
   `mulebox/<job>` (`success`, `failure`, or `error` when the job gave no result), so a pull
   request shows it and it can be a required check. Only when the files sent are exactly a pushed
   commit: no change in the worktree, no untracked file, and a remote-tracking branch holds HEAD;
   else nothing is posted and `check` says why. Not with `--detach`. It goes out through the dev
   machine's own `gh`, which must be signed in with write access to the repository.

   `isolation: container` runs each job in a fresh container of its own on a Linux node with
   Docker: it sees the project's folder, its package caches and the node's toolchains
   (read-only), and not the node's home folder, keys, other projects or Docker. Use it for code
   nobody has read. It runs in mulebox's image (Ubuntu with git, a compiler, Python), built once
   per node by the first such job, or in `image:`, which then brings its own tools: the node's
   toolchains may not run in another system. In a compose project mulebox brings the services
   up on the node, and the job reaches them by name (`db:5432`) or, as usual, at
   `localhost:$MULEBOX_PORT_...` (forwarded inside the container when its image has `python3`).
   `docker compose exec`, `logs`, `ps` and `restart` of the job's own services work; anything
   that would make a container, image or volume (`docker run`, `build`, `cp`, Testcontainers) is
   refused with a message (docs/design.md, Isolation per job).

   A node's owner can make every job there isolated (`isolation = "container"` in node.toml),
   with or without this field. Leave the field out to take what the node gives; write
   `isolation: none` only for a project that cannot run in a container: on a node with that
   floor its jobs are refused, and the message says why.

   Rules for the values:
   - **Databases are per job.** A database a job shares with anything else, such as one
     already running on the node or reached by address, needs `${MULEBOX_JOB_SLUG}`
     (the job id in lowercase with `_`, safe in database names) in every name, prefix or schema.
     A database in a compose service of the job itself is that job's alone and gone afterwards,
     so its name is free, and a project's fixed name works.
     Env values may use `${MULEBOX_JOB_ID}`, `${MULEBOX_JOB_SLUG}` and earlier `env:`
     entries, in the order the file lists them; nothing else is expanded and no shell runs. An
     entry that uses a later one is a config error, caught before any upload (exit 2, also from
     `mulebox contract` and `mulebox doctor`). A name the file does not explain may come from the
     machine's `job_env`, so `doctor` warns about it; if nothing sets it the job cannot start
     (exit 5). Never point a job at a database
     that already exists on the node.
   - Values are strings: quote numbers (`CI: "1"`). `PATH`, `HOME`, `USER`, `SHELL` and
     `MULEBOX*` cannot be set.
   - **No real secrets.** Use obviously fake values (`ci-secret-at-least-32-characters`).
     If a check truly needs a real credential, stop and ask the user.
   - **Toolchain versions** must match what the project uses (`.nvmrc`, `packageManager`,
     `engines`, the CI workflow). If the node lacks one, the first job that needs it
     installs it, once, which can take minutes on a slow network, and the job's log says so. If
     that fails, the job exits 5 with the reason and the versions the machine has. Switch to a
     listed version only if it matches the project; otherwise tell the user.
   - `setup` runs before a job in the same shell, so what it exports reaches the job; a `cd`
     in it does not, the job's command starts in the project's folder. Keep it to dependency
     install. It is
     skipped when nothing it depends on changed: its text, the toolchain, the env and the
     manifests, lockfiles and version files at the root or one folder down (`package.json`,
     `pnpm-lock.yaml`, `pyproject.toml`, `requirements.txt`, `go.mod`, `VERSION`, `.nvmrc` and the
     like; the list is `SETUP_INPUTS` in `worker/project_home.py`). If `setup` reads any other
     file, change its text to make it run again. Its output must be something git ignores; if it
     is not, the next job loses it and `setup` runs again. A compose job always runs `setup`.
   - `install` is for dependencies in any project, with or without containers. It runs after the
     containers are up and before `setup`, so `docker compose exec -T api composer install` runs
     in the project's own image, and it is skipped like `setup` is, also in a compose job, as
     nothing it makes lives in a container. It also depends on the compose files and any
     `Dockerfile`; an image tag that moves on its registry is not noticed. What reads like a lost
     network is tried again, up to 3 times. If it fails the job exits 5, as it never ran: fix the
     lockfile or the network, not the code. Use `setup` for what must happen in every job's fresh
     containers, such as loading a database.
   - With an `install` or `setup` and pnpm (a pinned `pnpm` or `cache-pnpm`), a job turns off pnpm's
     check before each `pnpm run`, also in containers: the packages are settled, and that check can
     start a long, silent install.
   - `mulebox warm [job]` runs a job up to its command: toolchains, images, caches, `install` and
     `setup`. Use it ahead of a long wait or a slow link; it takes a build slot like any job.
   - **A branch keeps its folder.** Jobs of a branch run in one folder on the node, with
     the project's ignored files kept between them. Only one job of a branch runs at a time.
     `mulebox projects` shows the folders and sizes. If a job only fails or passes because of what
     an earlier job left there, `mulebox project reset <project> --branch <name> --yes` starts that
     branch clean. Leave `mulebox project clean` to the user.
   - **A job can differ from the defaults.** Instead of a command, give it a mapping; a job
     left as a plain command keeps the top-level `setup` and `compose:`.

     ```yaml
     jobs:
       check: pnpm check
       lint:
         run: pnpm lint
         setup: pnpm install --frozen-lockfile --ignore-scripts  # or false for no setup
         install: false                  # the top-level install runs in a service
         compose: false                  # no containers for this job
       e2e:
         run: pnpm exec vite --port "$MULEBOX_PORT_VITE" & pnpm exec playwright test
         ports: [vite]
     ```

     `ports: [vite]` on a job gives it `MULEBOX_PORT_VITE`, a free port for a process of the job
     itself, such as a dev server a browser test starts. Bind to `127.0.0.1` with that port;
     never a fixed number, another job may hold it. Use it in the job's commands or in `env:`. A
     name may not end in a number, and the port is the job's until it is cleaned up. Another
     job has no such variable, so `env:` entries built on it are left out there.

     With `compose: false` the job needs no Docker on its machine. It keeps the top-level `install`
     and `setup` unless it says otherwise, except a top-level `install` that runs `docker compose`,
     `docker exec` or `docker run`: with no containers it could not work, so the job goes without it.
     The order is always `install`, then `setup`, then the command; a `cd` in `setup` does not
     reach the command. `env:` entries built on `MULEBOX_PORT_...`, directly or through an earlier
     entry, are not set for that job; it says so only when it has containers or `ports:` of its
     own, as one with neither has nothing such an entry could point to. `mulebox run` always uses the top-level values.
     `ports:` needs a node on 0.40 or later: an older worker refuses the job at
     the start, with exit 5.
   - A job may span several lines (`check: |`). The first line that fails ends it, as in a
     GitHub Actions `run:` step.
   - If the project runs containers for its checks, use `compose:` (section 2a). Never run
     `docker compose up` in a job: nothing would remove the containers afterwards.
3. **Verify it.** Run `mulebox doctor`, then `mulebox check`. It must pass on a clean main branch, with the same
   result as the project's CI. Then prove a broken change fails the same way it would
   locally: add an obvious type error, run `mulebox check typecheck` (or `check`), confirm
   it fails with that error and a non-zero exit code, and **revert the change**.
4. <a id="agent-rule"></a>**Add the agent rule** to the project's AGENTS.md (or CLAUDE.md if that is where the
   rules live). Show the user the exact text before committing it:

```markdown
## Builds and tests: use mulebox

Run builds, type checks, lint and tests through mulebox, never directly on this machine:

- full gate: `mulebox check`, or `mulebox check --detach` for a long run, then
  `mulebox wait <job-id>`
- one job from `.mulebox.yml`: `mulebox check <job>`
- one-off command (single test file, script): `mulebox run -- <cmd...>`

Keep git, search, reading files and diffs local. If mulebox is unreachable (exit 3), stop
and tell the user instead of running the command locally. `mulebox contract` prints how
this project works with mulebox.
```

   Keep checks that read git history out of `jobs:`. A job runs on a snapshot of files in a
   repository of mulebox's own, without your project's history, so `commitlint`, `git diff origin/main...`, "changed files only" scripts and
   anything else that asks git stay local, where the history is. They are light anyway.
5. **Commit** `.mulebox.yml` and the rule on a branch and open a pull request if that is
   the project's workflow. Report to the user: the jobs you defined, the check time, and
   anything you could not set up.

## 2a. Projects that need containers (`compose:`)

```yaml
project: example-app
compose: [docker-compose.yml, docker-compose.ci.yml]   # merged in this order; needs docker
env:
  APP_URL: http://127.0.0.1:${MULEBOX_PORT_API_8000}   # service api, container port 8000
install: docker compose exec -T api composer install
jobs:
  check: docker compose exec -T api php artisan test --parallel
  migrate: docker compose exec -T api php artisan migrate --seed --force
timeout_min: 30
```

mulebox starts the containers (`docker compose up --detach --wait`) before `install`, inside
the job. Every job gets its own containers, networks and volumes. All of them are removed
when the job ends, however it ends; pulled images and build layers stay as cache. An image
the project builds gets a tag of this job only, whatever `image:` says, so reach it through
the service name (`docker compose exec`), not by a tag in `docker run`.

- **`docker compose exec -T <service> ...`** works as it is, from any folder. Use `-T`: a job
  has no terminal. Do not add `-f` or `-p`, and do not run `up` or `down`. For one test,
  `mulebox run --in api -- php artisan test --filter Login` is the same thing, shorter.
- **Ports always move.** Each published port is bound to `127.0.0.1` on a port chosen for the
  job, whatever the compose file says, and the log names it. Use the variable
  `MULEBOX_PORT_<SERVICE>_<PORT>` in `env:` or in commands, never a number from the compose
  file. Letters are uppercased and other characters become `_`; UDP ports end in `_UDP`.
  Between containers nothing changes: use the service name and the container port.
- **`env:` reaches compose**, for `${VAR}` in compose files, as it reaches commands. A service
  only sees what its `environment:` passes on, as always. `UID` and `GID` are set, so
  `user: "${UID}:${GID}"` works.
- **The node's `job_env` reaches services** (settings such as `NODE_OPTIONS` for a
  slow network), and your commands. A value in a service's `environment:` or `env_file:`
  wins; a value in `.mulebox.yml` `env:` replaces it for the whole job, and may add to it
  with `${NODE_OPTIONS}`. It does not reach a `RUN` line of an image build.
- **Open files.** A service with no `ulimits.nofile` of its own gets 65536, soft and hard:
  containers can start at 1024, and a database under test then dies with "Too many open
  files". A value in the compose file always wins, so set one if a service needs more.
- **`.env*` files are not uploaded**, apart from tracked templates, so `env_file: .env.ci`
  fails on the node. Move those throwaway values into `env:` and `environment:`.
- **Root-owned files** in the checkout are fine: mulebox cleans them up.
- **A hardcoded database address** such as `localhost:27017` in a test works without changing the
  code: run the tests in a service that shares the database's network, in a CI-only compose
  file. `network_mode: service:mongo` is allowed, as it stays inside the job's project, and that
  service then reaches the database on `localhost`. From a command on the machine the address
  is `127.0.0.1` and `MULEBOX_PORT_...`.
- **CI scripts that use `COMPOSE_PROJECT_NAME`** work: mulebox sets it, with `COMPOSE_FILE`, for
  the whole job, and `env:` cannot change it. So read it, as in
  `${COMPOSE_PROJECT_NAME}_default` for the job's network. A script that writes a fixed project
  or container name will not find the job's containers: use `docker compose exec` or the variable.
- **`up --wait` needs every service to stay up** and, if it has a healthcheck, become healthy.
  A service that exits on purpose should be a `depends_on` with
  `condition: service_completed_successfully`, or moved into a job command. A healthcheck
  that depends on `setup` having run cannot pass, because setup comes after.
- **A healthcheck must test the real server.** On a fresh volume the MySQL and MariaDB images
  first run a temporary server for their init scripts, then restart it, and `mysqladmin ping`
  on the socket passes during that first one. Ping over TCP, which the temporary server does not
  listen on: `test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "--protocol=TCP"]`. Then
  `setup` meets the real server, with no retry loop.
- When a job fails, its log ends with the state and last lines of its containers.
- Images are pulled and built by `docker compose up --no-start`, then `up --detach --wait`
  starts them, so a job's stages can tell the two apart. Layer-by-layer pull progress is left
  out of the log. It shows `Image ... Pulled` and `mulebox: at least 640.0 MB of image layers
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
  outside it whose source does not exist on the node (mulebox never creates one
  there).

This stops a CI file's assumptions from reaching past the job. It does not contain a hostile
project: a job can run any command and Docker access is root-equivalent, so a node
is only for projects its owner trusts.

`env:` may not set what changes how a job starts: `BASH_ENV`, `ENV`, `SHELLOPTS`, `BASHOPTS`,
`PS4`, `IFS`, `GCONV_PATH` and `BASH_FUNC_*` for any project, and for a `compose:` project
`LD_PRELOAD`, `LD_AUDIT`, `LD_LIBRARY_PATH` and
`COMPOSE_*` and `DOCKER_*`, except `DOCKER_BUILDKIT` and `DOCKER_DEFAULT_PLATFORM`. A job that
sets one fails at the start, whichever client sent it.

`container_name`
is dropped, with a note in the log; use the service name. Put CI-only changes in a separate
compose file rather than changing how the project runs locally.

If mulebox says no node offers `docker`, tell the user: a person has to add it
to the node's `capabilities`. If it says the machine's mulebox is too old, it has to
be upgraded. `compose-v1` in `needs` comes with `compose:`; nobody sets it.

## 2a-1. Package caches

Installs are slow on a slow network, and a compose job's containers start empty. Ask for a cache in `needs`
and downloads stay on the node between jobs of this project. It is off unless the
project asks.

```yaml
needs: [cache-pnpm, cache-composer, cache-npm, cache-pip]
```

| `needs` | Folder on the node | Set for commands on the machine |
| --- | --- | --- |
| `cache-pnpm` | `<cache>/packages/<project>/pnpm` | `pnpm_config_store_dir`, `npm_config_store_dir`, `MULEBOX_CACHE_PNPM` |
| `cache-composer` | `<cache>/packages/<project>/composer` | `COMPOSER_CACHE_DIR`, `MULEBOX_CACHE_COMPOSER` |
| `cache-npm` | `<cache>/packages/<project>/npm` | `npm_config_cache`, `MULEBOX_CACHE_NPM` |
| `cache-pip` | `<cache>/packages/<project>/pip` | `PIP_CACHE_DIR`, `MULEBOX_CACHE_PIP` |
| `cache-cocoapods` | `<cache>/packages/<project>/cocoapods` | `CP_CACHE_DIR`, `MULEBOX_CACHE_COCOAPODS` |
| `cache-spm` | `<cache>/packages/<project>/spm` | `MULEBOX_CACHE_SPM` only: pass it yourself (section 2c) |

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
- **The first job after turning a cache on starts empty** and downloads everything again, even if
  earlier jobs had the packages elsewhere. On a slow connection, plan for that one long run.
- **On a slow connection** a large download can take most of a job: a browser for Playwright is
  about 180 MiB, restarts from zero if the connection drops, and is kept once one job has it; and `corepack` fetches pnpm on every job, outside any cache. Prefer versions
  already on the machine, and run `mulebox doctor` first: it says whether registries are reachable.
- A pnpm install across mounts copies packages instead of linking them. That is slower than
  a link and far faster than a download.
- A service that uses one of these variables fails at the start if the project does not ask
  for that cache: the variable is empty. For running the same file on a dev machine, give it a
  default, as in `${MULEBOX_CACHE_PNPM:-/tmp/example-app-pnpm}`.

**What sharing means.** Every branch of a project on a machine shares its cache: every job of
this project on this machine, on any branch, reads and
writes the same folder, and the job's log says so. A job can therefore leave something behind
that a later job of this project gets: a change on a branch can reach the next run of main. pnpm
checks each package against the hash in the lockfile; Composer checks a download only where
the lockfile has a hash, and many entries have none. Another project has its own folder, and
compose refuses a mount of it. A project's name comes from its `.mulebox.yml`, so two
projects with the same `project:` share a cache. As everywhere on a node, this is
for projects its owner trusts, not a defence against a hostile one: a job with Docker
access can reach any folder.

If a cache looks wrong, a person clears it on the node, with no job of that project
running: `mulebox cache clear <project>`. `mulebox cache list` shows the sizes. Caches are
never cleaned by themselves. Do this only when the user asks: do not ssh in yourself.

## 2b. Browser tests (Playwright)

Add `playwright` to `needs`. The node must offer it: that means a person has
installed the system libraries browsers use. mulebox then sets `PLAYWRIGHT_BROWSERS_PATH` to
one folder on the node, so a browser is downloaded once, not for every job.

```yaml
needs: [playwright]
env:
  BASE_URL: http://127.0.0.1:${MULEBOX_PORT_API_8000}
jobs:
  e2e: pnpm exec playwright install chromium && pnpm exec playwright test
```

`playwright install chromium` does nothing once that version is there. A machine that cannot
reach the browser download (a VPN exit can be refused) needs that version copied into the shared
folder `~/.mulebox/cache/playwright/`, with its `INSTALLATION_COMPLETE` file, from a machine that
can. Browsers of other
versions stay, so keep it in the job: it is what keeps the version in step with the project's lockfile. Do not use
`install --with-deps`: it needs root, which a job does not have. That goes for a project's own
install script too: if `pnpm test:e2e:install` or a CI step says `--with-deps`, call
`playwright install chromium` from the job directly instead of the script. The system libraries
are already there, since a machine only offers `playwright` once a person installed them. Browsers run on the
node, not in a container, so they reach containers through `127.0.0.1` and the
`MULEBOX_PORT_...` variable. Read the URL from the environment in `playwright.config`, and
do not let Playwright's `webServer` start something on a fixed port.

## 2c. Apple platforms (Mac nodes)

A project that builds for macOS, iOS, watchOS, tvOS or visionOS runs on a Mac node. Pin its
Xcode as a toolchain; the node must have it, as a job never installs Xcode. For tests in a
simulator, add `simulator` to `needs`, or pin the runtime: each job gets a simulator of its own,
made before its commands and removed on every outcome, with its id in `$MULEBOX_SIMULATOR`.

```yaml
toolchain:
  xcode: "16.2"
  simulator: "iOS 18.2"         # optional; without it, the newest iOS runtime the node has
needs: [cache-spm]               # cache-cocoapods too, for a Podfile
jobs:
  test: >-
    xcodebuild test -scheme App -destination "id=$MULEBOX_SIMULATOR"
    -derivedDataPath "$MULEBOX_DERIVED_DATA" -packageCachePath "$MULEBOX_CACHE_SPM"
    CODE_SIGNING_ALLOWED=NO
```

Do not boot, erase or delete simulators yourself, and do not pick one by name
(`name=iPhone 16`): another job can be using it. A pinned Xcode or runtime the node lacks
exits 5, naming the ones it has; `mulebox doctor` lists each Mac's Xcodes, SDKs and runtimes.

`$MULEBOX_DERIVED_DATA` is a folder in the job's own folder, set on every Mac job: pass it to
`xcodebuild -derivedDataPath`, so jobs never share build products and the folder goes with the
job. Without it xcodebuild writes to the node user's own DerivedData. SwiftPM reads no setting
for its cache either: pass `-packageCachePath "$MULEBOX_CACHE_SPM"` to xcodebuild, or
`--cache-path "$MULEBOX_CACHE_SPM"` to `swift build` and `swift test`. CocoaPods finds its cache
by itself (`CP_CACHE_DIR`); every branch shares it, and CocoaPods empties a cache another version
wrote, so keep the project's branches on one CocoaPods version (a `Gemfile.lock` pins it, run as
`bundle exec pod install`). A simulator test needs no signing, hence `CODE_SIGNING_ALLOWED=NO`.

## 3. Moving GitHub Actions to mulebox runners

A repository's CI can run on the node through the same queue. Do this only when
the user asks for it. On a **public repository** only an isolated runner may serve it
(`mulebox runner register --isolated`, a fresh container per job): anyone can open a pull
request, GitHub takes its workflow from that pull request, so it can name the runner itself,
whatever the main branch's workflow says. If the repository is public, or is about to be, tell
the user and ask before registering anything.

1. **Register a runner** (needs `gh` logged in with admin rights on the repository):

       mulebox runner register --repo <owner>/<repo>

   It installs a runner on the node as a service with the labels `self-hosted`,
   `Linux`, `X64`, `mulebox`. It takes only runs that the account `gh` is signed in as
   started; a run by anyone else (a bot such as `dependabot[bot]` too) fails at its first
   step unless the user names it with `--actors`. Send such runs to GitHub's machines in the
   workflow, as forks are below.
2. **Point the workflow at it.** In `.github/workflows/*.yml`:

```yaml
jobs:
  check:
    runs-on: >-
      ${{ fromJSON(github.event_name == 'pull_request'
      && github.event.pull_request.head.repo.full_name != github.repository
      && '["ubuntu-latest"]'
      || vars.CI_RUNS_ON || '["self-hosted","Linux","X64","mulebox"]') }}
```

   With the `CI_RUNS_ON` repository variable the user can switch back (for example to
   `["ubuntu-latest"]`) without a code change. Keep the first lines: a pull request from a
   fork must never reach this runner. Its code would run as the node's user, with
   Docker. On a public repository, ask the user before registering a runner at all, and then
   only `--isolated`; a job there has no Docker, `services:` or `container:`.
3. **Linux differences to check:**
   - The node is Linux, not macOS: Docker is Docker Engine, not Docker Desktop.
     Containers that write into the checkout leave root-owned files. Run them with the
     runner's user id (`user: "${UID}:${GID}"`) or clean them up in a final step: `compose:`
     cleanup covers mulebox jobs, not GitHub runner jobs.
   - Steps that install system packages with `sudo` will fail: the runner has no sudo.
     Ask the user to install such packages on the node once.
   - Use per-run database names, as in section 2.
   - Do not hardcode the node's paths or host name in the workflow.
   - **A GitHub job does not get the machine's `[job_env]`**, which mulebox gives its own jobs
     (on a slow link it often holds `NODE_OPTIONS`, for example
     `--network-family-autoselection-attempt-timeout=5000`). A step that passes in `mulebox run`
     and times out in the runner may need that: set it in the workflow's `env:`. To read a CI
     job's steps and output use `mulebox logs <its job id>` (the dashboard has it too) or
     `gh run view --log`; do not read the runner's folders through a job.
   - **Containers a workflow starts itself** (`docker run`, its own `docker compose`) get Docker
     Engine's default limit of 1024 open files, not the 65536 mulebox gives a job's `compose:`
     services, and Docker Desktop's higher default hides this on a Mac. A database runs out and
     crashes mid-test (MongoDB: `Too many open files`, then exit 139). Set it on the container:
     `docker run --ulimit nofile=64000:64000 ...`, or `ulimits: nofile:` in that compose file.
     mulebox does not change Docker's own settings on the machine.
   - **pnpm on a slow connection:** use corepack (`corepack enable` after `actions/setup-node`,
     with `COREPACK_ENABLE_DOWNLOAD_PROMPT=0`) rather than `pnpm/action-setup`. Corepack takes
     the version and hash from `packageManager`, and on a self-hosted runner its cache in
     `~/.cache/node/corepack` stays between runs, so pnpm is fetched once. `pnpm/action-setup`
     downloads on every run, and can fetch a different version than `packageManager` pins.
   - **A CI job can take longer than `mulebox check`** on the same tree: it shares the machine
     with whatever holds the other slots (another CI job or an agent's), and `actions/checkout`
     starts from a clean folder, so tool caches kept in the tree (ESLint, TypeScript build
     info) start cold unless the workflow restores them. A `mulebox check` keeps its project
     home between jobs.
4. **Verify** with a pull request: the job is picked up by the mulebox runner (its log
   starts with `mulebox: waiting for a build slot` or goes straight on), passes, and a
   deliberately failing commit fails.
5. If the project had a runner on the dev machine before, tell the user it can be stopped; do
   not remove it yourself.

## 4. Reporting what mulebox could not handle

If mulebox itself got in the way, and the user wants it reported, `mulebox feedback guide` prints
the whole procedure. In short:

    mulebox feedback draft <id> [<id> ...] --summary "what happened" \
        --title "short title" --grep "error|FAIL" -o draft.md            # sends nothing
    mulebox feedback post draft.md                                        # opens the issue

The draft holds every job id given, with its result, stages and the mulebox that ran it: the
people who run mulebox trace a report by them. `--grep` adds the log lines matching a pattern with
the lines around them, `--log` the last lines (`--log-lines N`). Leave out the job id when no job
is involved, such as an unreachable machine, and copy what mulebox printed: some notices are in
no log. **Show the user the final file and get their approval before posting.** Read it yourself
too: the scrub replaces names, private links, addresses and secrets, but cannot recognise private
code, customer data or internal names. `post` needs `feedback_repo` in `client.toml`; it refuses a
file that still holds something the scrub would remove, and says on which line and what kind.
It also refuses for a project listed in `feedback_off` in `client.toml`, such as one that belongs
to a client: then tell the user about the problem instead.

## 5. Things you must not do

- Do not run heavy commands locally when mulebox is unavailable; tell the user.
- Do not ssh into the node to change, install or delete things.
- Do not put real secrets, real hosts or personal paths into `.mulebox.yml` or workflows.
- Do not use or modify databases that already exist on the node.
- Do not cancel other people's jobs.
