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
run on a build machine. You need a Linux machine with systemd, ssh access to it with a key, and
Python 3.12 or newer on both sides.

## How it works

```
laptop (agents edit code)              build machine(s) on your LAN
-------------------------              ----------------------------
mulebox check  --SSH-->  coordinator: one queue, history, web dashboard
mulebox queue  --SSH-->        |
                               v
                         worker(s): run jobs in isolated folders, with time limits,
                         warm caches, and cleanup; optional GitHub Actions runners
```

- **One command for agents**: `mulebox check` in any project folder runs that project's
  checks on a build machine and exits with the same pass/fail code.
- **One queue for everything**: agent checks and GitHub Actions jobs share it, so the build
  machine is never overloaded.
- **Live views**: a terminal view on the laptop and a read-only web dashboard showing the
  queue, live logs and machine load, opened through an SSH tunnel with `mulebox dashboard
  open`, or directly from other devices on your LAN, with a password unless you turn it off.
- **Made to grow**: jobs are claimed by workers, so more machines need no change to agents or
  projects. Installing a second machine is not finished yet (roadmap, M5).
- **Per-project config**: a small `.mulebox.yml` in each repo says what "check" means.

## Documentation

| Page | For |
| --- | --- |
| [getting-started.md](docs/getting-started.md) | the first install and the first project, in order |
| [install.md](docs/install.md) | build machine, laptop, upgrades, GitHub runners, the dashboard |
| [agents.md](docs/agents.md) | everyday commands, every `.mulebox.yml` field, the agent rule |
| [troubleshooting.md](docs/troubleshooting.md) | what an error means and what to do |
| [design.md](docs/design.md) | how it works and why |
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
