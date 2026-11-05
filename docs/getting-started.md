# Getting started

From nothing to a project whose checks run on a build machine. This page is the order to do
things in; it links to the details rather than repeating them.

Words used below: the **laptop** is where you and your agents edit code, and the **build
machine** is the Linux machine that runs the jobs. Examples use the build machine `build-1`,
the user `alice` and the project `example-app`.

## What you need

- A Linux build machine with systemd, Python 3.12 or newer, and a user you can log in as.
- A macOS or Linux laptop with Python 3.12 or newer, and git.
- Login from the laptop to the build machine with an ssh key, and no prompts: mulebox never
  answers one. `ssh build-1 true` must print nothing and ask nothing. If your key has a
  passphrase, load it into your ssh agent first.
- A project in a git repository with at least one commit.

A build machine runs whatever its projects' jobs say, and Docker access there is as good as
root. Use it for projects you trust, on a network you trust.

## 1. Install

1. Get mulebox on the laptop: `git clone` this repository and `cd` into it.
2. Install the build machine: [install.md, section 1](install.md#1-install-on-the-build-machine).
   Turn on lingering as it says, or the services stop when you log out.
3. Install the client on the laptop and point it at the machine:
   [install.md, section 2](install.md#2-configure-the-laptop).
4. Check it: `mulebox queue` prints an empty queue and exits 0.

## 2. Decide where the project's tools come from

A job runs on the build machine with your project's files and nothing else from your laptop.
Commands run in bash, as the mulebox service's user, with the service's `PATH`, not your login
shell's, so tools from a shell profile (`nvm`, `~/.local/bin`) are not there.

| The project uses | Do this |
| --- | --- |
| Node or pnpm | Pin exact versions under `toolchain:`. They are installed once per version, on the build machine: `ssh build-1 '~/.mulebox/bin/mulebox toolchain install node 22.22.3'`, then the same with `pnpm 11.22.0`. Node first: pnpm is installed with it |
| Docker containers, a database, or a language with no toolchain here | Use `compose:` ([agents.md, 2a](agents.md#2a-projects-that-need-containers-compose)). The machine must offer `docker`: [install.md, Node config](install.md#node-config) |
| Python, or anything else already installed for all users | Nothing: jobs find it on the machine. Make a virtual environment in `setup` |

`mulebox doctor` shows what the machine offers, and which versions.

## 3. Set up the project

In the project's root, write `.mulebox.yml`:

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

`project` names the project in the queue, `setup` runs before every job and `jobs` are what
you can run. Every field and its rules: [agents.md, section 2](agents.md#2-setting-up-a-project-muleboxyml).
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
