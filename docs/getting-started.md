# Getting started

From nothing to a project whose checks run on a build machine. This page is the order to do
things in; it links to the details rather than repeating them.

Words used below: the **laptop** is where you and your agents edit code, and the **build
machine** is the Linux machine that runs the jobs. Examples use the build machine `build-1`,
the user `alice` and the project `example-app`.

## What you need

- A Linux build machine with systemd, git, Python 3.12 or newer, and a user you can log in as.
- A macOS or Linux laptop with git, and Python 3.12 or newer unless you use the binary.
- Login from the laptop to the build machine with an ssh key, and no prompts: mulebox never
  answers one. `ssh build-1 true` must print nothing and ask nothing. If your key has a
  passphrase, load it into your ssh agent first.
- A project in a git repository with at least one commit.

### From nothing: what to ask a person for, once

An agent can do everything here except what needs a password or sudo. On a laptop with no ssh
key and a blank Ubuntu machine, the agent first makes a key (`ssh-keygen -t ed25519 -N ""` for a
key with no passphrase) and, if the user name on the machine differs from the laptop's, adds to
`~/.ssh/config`:

```
Host build-1
    User alice
```

Then it asks a person for these, in one message:

1. `ssh-copy-id build-1` from the laptop (it asks for alice's password once), then
   `ssh build-1 true` once, answering yes to the host key after checking its fingerprint.
2. On the machine, with sudo: `sudo apt-get install -y git python3-venv` (Ubuntu ships Python
   without `venv`; Docker too, if projects use `compose:`).
3. `sudo loginctl enable-linger alice`, so the services keep running after logout.

Nothing else needs a person: `mulebox setup build-1` does the rest, and says what is missing if
something is.

A build machine runs whatever its projects' jobs say, and Docker access there is as good as
root. Use it for projects you trust, on a network you trust.

## 1. Install

1. Get mulebox on the laptop: with pipx, as a binary, or by hand from a clone
   ([install.md, section 2](install.md#2-install-on-the-laptop)).
2. Install the build machine, from the laptop: `mulebox setup build-1` (`alice@build-1` works
   too, without the ssh config entry). It installs everything
   there, finds out what the machine offers, writes the laptop's config and runs a first job.

## 2. Decide where the project's tools come from

A job runs on the build machine with your project's files and nothing else from your laptop.
Commands run in bash, as the mulebox service's user, with the service's `PATH`, not your login
shell's, so tools from a shell profile (`nvm`, `~/.local/bin`) are not there.

| The project uses | Do this |
| --- | --- |
| Node or pnpm | Pin exact versions under `toolchain:`. The first job that needs one installs it on the build machine, once. |
| Docker containers, a database, or a language with no toolchain here | Use `compose:` ([agents.md, 2a](agents.md#2a-projects-that-need-containers-compose)). The machine must offer `docker`: [install.md, Node config](install.md#node-config) |
| Python, or anything else already installed for all users | Nothing: jobs find it on the machine. Make a virtual environment in `setup` |

`mulebox doctor` shows what the machine offers, and which versions.

## 3. Set up the project

In the project's root, let mulebox work it out from the project's own files:

```sh
mulebox init
```

It writes `.mulebox.yml`, and prints what you should look at: the versions it pinned, and the
tools the machine must have. Node, pnpm, npm, yarn, PHP with Composer, Python, Flutter, Go and
Rust are recognised, also one folder down, such as `api/` and `web/`. What the project's CI uses
comes first: its compose files and its Node version. A Node version that is only a major, such as
`24`, is pinned as the newest 24.x from nodejs.org, or this computer's own if it has that major. If it cannot tell how the
project is tested, say it yourself: `mulebox init --check "your test command"`. `--print` shows
the file without writing it.

The file is short and yours to edit. It looks like this:

```yaml
project: example-app
toolchain:
  node: "22.22.3"
  pnpm: "11.22.0"
env:
  CI: "1"
setup: pnpm install --frozen-lockfile
jobs:
  check: pnpm test            # required: the project's full gate
  typecheck: pnpm exec tsc --noEmit
```

`project` names the project in the queue, `setup` runs before a job when what it depends on
changed, and `jobs` are what you can run. Every field and its rules: [agents.md, section 2](agents.md#2-setting-up-a-project-muleboxyml).
Never put real secrets here; files such as `.env` are not uploaded at all.

Then, from the project's folder:

```sh
mulebox doctor              # checks the file and the machine; runs nothing
mulebox contract            # what this project looks like to an agent
mulebox check               # runs the job `check`; exits with its exit code
mulebox check typecheck     # runs another job
```

The upload holds your files as they are now, committed or not, except what git ignores and
files that look like secrets. Commit `.mulebox.yml` when it works: mulebox does not need it to
be committed, but your agents do.

Now prove that a failure reads as a failure: break something on purpose, run the job, see the
same error and a non-zero exit code you would get locally, and undo it.

## 4. Tell your agents

- Add the agent rule to the project's `AGENTS.md` or `CLAUDE.md`. The text to paste is in
  [agents.md, section 2, step 4](agents.md#agent-rule).
- With Claude Code, install the skill once for all projects: `mulebox skill install`
  ([details](install.md#skill-for-coding-agents)).
- Or hand all of section 3 to the agent: "read mulebox's docs/agents.md and set this project
  up". That file is written for it.

## Where next

| You want | Read |
| --- | --- |
| Everyday commands and exit codes | [agents.md, section 1](agents.md#1-everyday-use-project-already-set-up) |
| The live view in a browser | [install.md, Using the dashboard](install.md#using-the-dashboard) |
| Containers, package caches, browser tests | [agents.md, 2a to 2b](agents.md#2a-projects-that-need-containers-compose) |
| GitHub Actions on the build machine | [agents.md, section 3](agents.md#3-moving-github-actions-to-mulebox-runners) |
| Something went wrong | [troubleshooting.md](troubleshooting.md) |
