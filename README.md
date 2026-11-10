# mulebox

Send your AI coding agents' heavy work to the Linux machines on your network.

Agents (Claude Code, Codex, and others) edit code on your laptop. Builds, type checks,
linting and test suites are slow, hot and noisy, and several agents running them at once
can freeze the laptop. mulebox gives every project and every agent **one waiting line**
on one or more Linux build machines ("mules"), runs the jobs there, and streams the result
back as if the command had run locally.

Status: **in daily use on one build machine, not yet at 1.0** (version in [VERSION](VERSION)).
Behaviour can still change between versions, and what is open is in the
[roadmap](docs/phases.md).

## Get started

[docs/getting-started.md](docs/getting-started.md) takes you from nothing to a project whose checks
run on a build machine. You need a Linux machine with systemd, git and Python 3.12 or newer, and ssh
access to it with a key. On the laptop, install with pipx, as a binary that needs no Python, or by
hand: [install.md](docs/install.md#2-install-on-the-laptop).

## How it works

```
laptop (agents edit code)              build machine(s) on your LAN
-------------------------              ----------------------------
mulebox check  --SSH-->  coordinator: one queue, history, web dashboard
mulebox queue  --SSH-->        |
                               v
                         worker(s): run jobs in one kept folder per project and branch,
                         with time limits, warm caches, and cleanup; optional GitHub Actions runners
```

- **One command for agents**: `mulebox check` in any project folder runs that project's
  checks on a build machine and exits with the same pass/fail code.
- **One queue for everything**: agent checks and GitHub Actions jobs share it, so the build
  machine is never overloaded.
- **Live views**: a terminal view on the laptop and a web dashboard showing the queue, live
  logs and machine load, opened through an SSH tunnel with `mulebox dashboard open`, or
  directly from other devices on your LAN, with a password if you want one.
- **You steer the queue**: pause or freeze a job, move it up or down the line, boost it, pause a
  machine or a whole project, from the CLI or the dashboard. Upgrades wait their turn in the
  line (`mulebox setup <machine> --queued`), so they never cut a running job short.
- **Made to grow**: jobs are claimed by workers, so more machines need no change to agents or
  projects: `mulebox setup <host> --worker-of <coordinator>` adds one.
- **One command to set up**: `mulebox setup <host>` installs a build machine from the laptop, finds
  out what it offers, and proves it with a first job. It upgrades the same way.
- **Per-project config**: a small `.mulebox.yml` in each repo says what "check" means, and
  `mulebox init` writes it from the project's own files.
- **No job is lost because an agent went away**: a job that is working always finishes, and the
  agent's next command tells it the result, so it need not retest.
- **Long jobs ask, they do not die**: a long job asks its agent if all is well, and the agent
  answers `mulebox ok` or `mulebox cancel`. Only a job that is really stuck, with no answer, stops.
- **Agents choose how to wait**: follow the job, be pinged when it ends, or check back later.
- **A project is set up once**: each project has one folder on the build machine, with a git
  worktree per branch, and installs stay there. A job writes only the files that changed and runs
  `setup` only when what it depends on changed. Compose jobs still run `setup`, in new containers.
- **Folders you can find and clean**: `mulebox projects` shows where each project is and its size;
  `mulebox project clean` and `mulebox project reset` remove what is not needed.
- **How long jobs ran**: `mulebox stats` adds up job minutes today, by day and since the first
  job, by project, job, source (a laptop or GitHub), machine or kind.
- **Only changes cross the network**: over a slow link, a job sends the files that changed since
  the last one, not the whole project.
- **Branches run side by side**: different branches run at once, and a second job on the same
  branch waits for the first.
- **No repeat runs**: on exactly the same files, `mulebox check` gives the earlier result, or joins
  the same job if it is running, and says so. `--again` forces a run.

## Documentation

| Page | For |
| --- | --- |
| [getting-started.md](docs/getting-started.md) | the first install and the first project, in order |
| [install.md](docs/install.md) | build machine, laptop, upgrades, GitHub runners, the dashboard |
| [agents.md](docs/agents.md) | everyday commands, every `.mulebox.yml` field, the agent rule |
| [troubleshooting.md](docs/troubleshooting.md) | what an error means and what to do |
| [design.md](docs/design.md) | how it works and why |
| [design-system.md](docs/design-system.md) | the dashboard's look: tokens, components, rules |
| [phases.md](docs/phases.md) | the roadmap: what is done and what is open |
| [releasing.md](docs/releasing.md) | CI and releases, for maintainers |

## Security

mulebox is for one owner and the projects that owner trusts. A job runs as the build machine's
user, with Docker, so it is not a sandbox: read the
[security model](docs/install.md#security-model) before pointing it at a machine that holds
anything else, and keep fork pull requests away from its GitHub runners.

## For coding agents

[docs/agents.md](docs/agents.md) is written for AI coding agents: everyday use, setting a
project up (`.mulebox.yml`, the agent rule), and moving GitHub Actions to mulebox runners.
Point an agent at it: "read mulebox's docs/agents.md and set this project up".

## Development

Requires Python 3.12 or newer.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/mulebox --version
.venv/bin/python -m pytest              # includes the file-size check
.venv/bin/python -m pytest -n auto      # same, in parallel (about 5x faster)
.venv/bin/python tools/check_line_counts.py
```

After a VERSION bump, rerun the `pip install -e` step: the installed metadata keeps the
old version until then and the version test fails.

CI and the release process: [docs/releasing.md](docs/releasing.md). Rules for contributors and
agents: [AGENTS.md](AGENTS.md). Every change bumps
[VERSION](VERSION) and adds an entry to [PROJECT_LOG.md](PROJECT_LOG.md).

## License

[MIT](LICENSE).
