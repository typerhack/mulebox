# mulebox

Send your AI coding agents' builds and tests to the Linux machines on your network.

Agents (Claude Code, Codex, and others) edit code on your laptop. Builds, type checks, linting
and test suites are slow, hot and noisy, and several agents running them at once can freeze the
laptop. With mulebox, an agent types `mulebox check` instead. The job waits its turn in **one
line** shared by every project and agent, runs on a Linux build machine, and the agent gets the
output and the exit code as if the command had run locally.

![The mulebox dashboard: CPU, memory, disk and machines on top, the jobs running and waiting below](docs/images/queue-dark.png)

Status: **in daily use on one build machine, not yet at 1.0** (version in [VERSION](VERSION)).
Behaviour can still change between versions; what is open is in the [roadmap](docs/phases.md).

## Install

You need a Linux machine with systemd, git and Python 3.12 or newer, which your laptop reaches
over ssh with a key. On the laptop:

```sh
pipx install git+https://github.com/example-org/mulebox
mulebox setup build-1          # the build machine's ssh name: installs it, then runs a first job
```

Then, in any project:

```sh
mulebox init                   # writes .mulebox.yml from the project's own files
mulebox check                  # runs the project's checks on the build machine
mulebox dashboard open         # the dashboard in your browser, through an ssh tunnel
```

No Python on the laptop? There is a binary for macOS on Apple silicon and Linux on x86-64, and an
install by hand from a clone: [install.md](docs/install.md#2-install-on-the-laptop). The whole
path from nothing to a passing project, in order: [getting-started.md](docs/getting-started.md).

## How it works

Two kinds of machine:

- the **dev machine**: where you and your agents edit code, usually a laptop. It runs only the
  `mulebox` command, which talks to the build machines over ssh.
- **nodes**: the Linux build machines (the docs also call them build machines). Each runs a
  **worker**, which runs jobs. One node is also the **coordinator**: it holds the line of jobs
  and their history, and serves the dashboard.

```
dev machine (laptop)                     nodes (Linux build machines on your LAN)
--------------------                     ----------------------------------------
                                         node 1: coordinator + worker
mulebox check   ------- ssh ------->       one line of jobs, history, dashboard
mulebox queue                              runs jobs in its own slots
mulebox dashboard open                          ^              ^
                                                | ssh          | ssh
                                         node 2: worker   node 3: worker
                                           asks the coordinator for the next job it can run
```

- The dev machine only ever talks to the coordinator. It does not know how many nodes there are,
  so adding one changes nothing for agents or projects.
- Workers ask the coordinator for work. A job goes to the first node with a free slot that has
  what the job needs (Docker, Playwright, a toolchain). A worker reaches the coordinator with a
  key that can do nothing but worker requests.
- The dashboard runs only on the coordinator. Workers send their CPU, memory and network readings
  with every heartbeat, so one page shows every node.
- One node is enough to start: it is both coordinator and worker. A second joins with
  `mulebox setup node-2 --worker-of build-1`. A node can be drained, resumed and removed
  (`mulebox machine`). More than one node has been tried with a stand-in container only, so far.

## The dashboard

Live, in the browser: the line of jobs with each machine's lane, every job's stages and log as
they happen, and controls to pause, freeze, boost, reorder or cancel. It has a dark and a light
theme and follows the system's by default.

| | |
| --- | --- |
| ![The queue in the light theme](docs/images/queue-light.png) | ![A running job: its stages as a waterfall beside its live log](docs/images/job-dark.png) |
| The queue, light theme | A running job: stages and live log |
| ![A GitHub Actions run on a mulebox runner, with its steps](docs/images/ci-run-light.png) | ![Every machine with its state, load, slots and what it offers](docs/images/machines-dark.png) |
| A GitHub Actions run, step by step | Every machine at a glance |
| ![History with search and filters](docs/images/history-light.png) | ![How long jobs ran, today and since the first job](docs/images/statistics-dark.png) |
| History, searchable | Job minutes, by kind, project and machine |

A machine with many cores can show its busiest cores and one line for the rest (compact view,
left). On a phone the page stacks into one column (right).

<p>
  <img src="docs/images/cpu-compact-light.png" alt="The CPU box in its compact view on a 32-core machine" width="68%">
  <img src="docs/images/phone-dark.png" alt="The dashboard at phone width" width="28%">
</p>

Every screen is built on one small design system, Gauge: its tokens, components and rules are in
[design-system.md](docs/design-system.md), with a reference page you can open in a browser
([specimen.html](docs/design-system/specimen.html)).

![The Gauge design system's reference page](docs/images/design-system-light.png)

All pictures come from made-up data (`tools/screenshots.py`).

## What it does

- **One command for agents**: `mulebox check` runs the project's checks on a node and exits with
  the same code. `mulebox run -- <cmd>` runs any command there.
- **One line for everything**: agent jobs and GitHub Actions runs on mulebox runners share it, so
  a node is never overloaded.
- **You steer**: pause or freeze a job, move it in line, boost it, pause a machine or a whole
  project, from the CLI or the dashboard. Upgrades wait their turn (`mulebox setup <node> --queued`).
- **No job lost**: a working job always finishes even if its agent went away, and the agent's next
  command tells it the result. A long job asks its agent if all is well; only a job that is really
  stuck, with no answer, stops.
- **Fast repeats**: each project keeps a folder on the node with a git worktree per branch, a job
  sends only the files that changed, installs run only when the lockfile changes, and on exactly
  the same files `check` gives the earlier result.
- **Branches side by side**: different branches run at once; a second job on the same branch waits.
- **Docker Compose projects**: services per job with their own names, ports and networks, removed
  on every outcome.
- **Per-project config**: a small `.mulebox.yml` says what "check" means; `mulebox init` writes it.

## Documentation

| Page | For |
| --- | --- |
| [getting-started.md](docs/getting-started.md) | the first install and the first project, in order |
| [install.md](docs/install.md) | build machine, laptop, upgrades, more nodes, GitHub runners, the dashboard |
| [agents.md](docs/agents.md) | everyday commands, every `.mulebox.yml` field, the agent rule |
| [troubleshooting.md](docs/troubleshooting.md) | what an error means and what to do |
| [design.md](docs/design.md) | how it works and why |
| [design-system.md](docs/design-system.md) | the dashboard's look: tokens, components, rules |
| [phases.md](docs/phases.md) | the roadmap: what is done and what is open |
| [releasing.md](docs/releasing.md) | CI and releases, for maintainers |

## For coding agents

[docs/agents.md](docs/agents.md) is written for AI coding agents: everyday use, setting a project
up (`.mulebox.yml`, the agent rule), and moving GitHub Actions to mulebox runners. Point an agent
at it: "read mulebox's docs/agents.md and set this project up".

## Security

mulebox is for one owner and the projects that owner trusts. A job runs as the node's user, with
Docker, so it is not a sandbox: read the [security model](docs/install.md#security-model) before
pointing it at a machine that holds anything else. mulebox attaches GitHub runners to private
repositories only, as a public one would run any fork's pull request on your machine.

## Development

Requires Python 3.12 or newer, and Node.js 22 with npm for the dashboard's front end (`web/`,
[web/README.md](web/README.md)): from a checkout, `mulebox setup` builds it and stops without npm,
and the dashboard shows no page until it is built.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/mulebox --version
.venv/bin/python -m pytest              # includes the file-size check
.venv/bin/python -m pytest -n auto      # same, in parallel (about 5x faster)
.venv/bin/python tools/check_line_counts.py
(cd web && npm ci && npm run build)    # the dashboard's page, into mulebox/dashboard/app/
.venv/bin/python tools/screenshots.py   # the README's pictures, from the dashboard's stand-in data
```

After a VERSION bump, rerun the `pip install -e` step: the installed metadata keeps the old
version until then and the version test fails.

CI and the release process: [docs/releasing.md](docs/releasing.md). Rules for contributors and
agents: [AGENTS.md](AGENTS.md). Every change bumps [VERSION](VERSION) and adds an entry to
[PROJECT_LOG.md](PROJECT_LOG.md).

## License

[MIT](LICENSE).
