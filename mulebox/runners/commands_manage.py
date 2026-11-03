"""CLI subcommands for runner management (docs/interfaces-m3.md, Runner management).

On the build machine (the token is read from stdin, or prompted without echo on a TTY):

    mulebox runner add --repo <owner/repo> [--labels a,b] [--name N]
    mulebox runner list
    mulebox runner remove <name> | --repo <owner/repo> [--name N]

On the laptop (the token comes from `gh`, the command runs on the coordinator over ssh):

    mulebox runner register --repo <owner/repo> [--labels a,b] [--name N]
    mulebox runner unregister --repo <owner/repo> [--name N]

Exit codes: 0 done, 1 runner operation failed, 2 usage or config error, 3 build machine
unreachable, 4 remote command or `gh` failed.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable

from mulebox.client import report
from mulebox.common.config import ConfigError, load_client_config, load_node_config
from mulebox.common.errors import MuleboxError
from mulebox.common.redact import Redactor
from mulebox.common.ssh import RemoteTimeout, SSHUnavailable
from mulebox.runners.names import RunnerUsageError, default_name, parse_labels

EXIT_FAILED = 1
Handler = Callable[[argparse.Namespace], int]
_TOKENS: list[str] = []  # tokens read in this process, redacted from every error


def register(sub: argparse._SubParsersAction) -> None:
    """Add the subcommands. Each sets func=handler(args) -> int."""
    runner = sub.add_parser("runner", help="manage GitHub Actions runners")
    actions = runner.add_subparsers(dest="runner_command", metavar="<action>", required=True)

    add = actions.add_parser("add", help="add a runner on this build machine (token on stdin)")
    _options(add, labels=True, config=True)
    add.set_defaults(func=_guarded(_add))

    listing = actions.add_parser("list", help="list the runners on this build machine")
    listing.add_argument("--config", help="node config file")
    listing.set_defaults(func=_guarded(_list))

    remove = actions.add_parser("remove", help="remove a runner (removal token on stdin)")
    remove.add_argument("runner", nargs="?", help="runner name")
    remove.add_argument("--repo", help="remove this repository's only runner (owner/name)")
    remove.add_argument("--name", help="runner name (same as the positional argument)")
    remove.add_argument("--config", help="node config file")
    remove.set_defaults(func=_guarded(_remove))

    reg = actions.add_parser("register", help="from the laptop: add a runner for a repo")
    _options(reg, labels=True, config=False)
    reg.set_defaults(func=_guarded(_register))

    unreg = actions.add_parser("unregister", help="from the laptop: remove a repo's runner")
    _options(unreg, labels=False, config=False)
    unreg.set_defaults(func=_guarded(_unregister))


def _options(parser: argparse.ArgumentParser, *, labels: bool, config: bool) -> None:
    parser.add_argument("--repo", required=True, help="GitHub repository, owner/name")
    parser.add_argument("--name", help="runner name (default <node>-<repo name>)")
    if labels:
        parser.add_argument("--labels", help="comma-separated labels (default mulebox)")
    if config:
        parser.add_argument("--config", help="node config file")


def _guarded(handler: Handler) -> Handler:
    def run(args: argparse.Namespace) -> int:
        from mulebox.runners.github import GitHubError

        try:
            return handler(args)
        except KeyboardInterrupt:
            return report.EXIT_CANCELLED
        except (ConfigError, RunnerUsageError) as exc:
            return _fail(exc, report.EXIT_USAGE)
        except (SSHUnavailable, RemoteTimeout) as exc:
            return _fail(exc, report.EXIT_UNREACHABLE)
        except GitHubError as exc:
            return _fail(exc, report.EXIT_REMOTE)
        except MuleboxError as exc:
            return _fail(exc, EXIT_FAILED)

    return run


def _fail(exc: Exception, code: int) -> int:
    print(f"mulebox: {Redactor(_TOKENS).redact(str(exc))}", file=sys.stderr)
    return code


def read_token(prompt: str) -> str:
    """One token line from stdin; prompted without echo when stdin is a terminal."""
    token = getpass.getpass(prompt) if sys.stdin.isatty() else sys.stdin.readline()
    token = token.strip()
    if not token:
        raise RunnerUsageError(
            "no token on stdin; pipe it in, e.g. from `gh api -X POST "
            "repos/<owner/repo>/actions/runners/registration-token --jq .token`")
    _TOKENS.append(token)
    return token


def _machine(args: argparse.Namespace):
    from mulebox.runners.manage import Machine
    from mulebox.worker.paths import NodePaths

    node = load_node_config(getattr(args, "config", None))
    return Machine(NodePaths.from_config(node.roots), node.name,
                   say=lambda text: print(text, flush=True))


def _add(args: argparse.Namespace) -> int:
    from mulebox.runners import manage

    machine = _machine(args)
    name = args.name or default_name(machine.node, args.repo)
    labels = parse_labels(args.labels)
    token = read_token("GitHub runner registration token: ")
    manage.add(machine, args.repo, token, name=name, labels=labels)
    return 0


def _list(args: argparse.Namespace) -> int:
    from mulebox.runners import manage

    rows = manage.list_runners(_machine(args))
    if not rows:
        print("no runners")
        return 0
    print(f"{'NAME':<32} {'REPO':<40} {'SERVICE':<10} JOB")
    for row in rows:
        print(f"{row.name:<32} {row.repo:<40} {row.state:<10} "
              f"{'busy' if row.busy else 'idle'}")
    return 0


def _remove(args: argparse.Namespace) -> int:
    from mulebox.runners import manage

    machine = _machine(args)
    if args.runner and args.name and args.runner != args.name:
        raise RunnerUsageError("two different runner names given")
    name = args.runner or args.name
    if name is None and args.repo is None:
        raise RunnerUsageError("name the runner, or give --repo")
    if name is None:
        name = manage.find_by_repo(machine, args.repo)
    elif args.repo is not None:
        manage.check_runner_repo(machine, name, args.repo)
    token = read_token("GitHub runner removal token: ")
    manage.remove(machine, name, token)
    return 0


def _register(args: argparse.Namespace) -> int:
    from mulebox.runners import github

    github.register(load_client_config(), args.repo, name=args.name, labels=args.labels)
    return 0


def _unregister(args: argparse.Namespace) -> int:
    from mulebox.runners import github

    github.unregister(load_client_config(), args.repo, name=args.name)
    return 0
