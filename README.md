# mulebox

Send your AI coding agents' heavy work to the Linux machines on your network.

Agents (Claude Code, Codex, and others) edit code on your laptop. Builds, type checks,
linting and test suites are slow, hot and noisy, and several agents running them at once
can freeze the laptop. mulebox gives every project and every agent **one waiting line**
on one or more Linux build machines ("mules"), runs the jobs there, and streams the result
back as if the command had run locally.

Status: **early design, not usable yet** (version in [VERSION](VERSION)).

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
- **Grows with your hardware**: add a faster machine as another worker; retire an old one
  by draining it. Agents and projects do not change.
- **Per-project config**: a small `.mulebox.yml` in each repo says what "check" means.

See [docs/design.md](docs/design.md) for the design and [docs/phases.md](docs/phases.md)
for the roadmap.

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

Rules for contributors and agents: [AGENTS.md](AGENTS.md). Every change bumps
[VERSION](VERSION) and adds an entry to [PROJECT_LOG.md](PROJECT_LOG.md).

## License

[MIT](LICENSE).
