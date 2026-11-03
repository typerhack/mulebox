"""CLI subcommands of the runners package: hooks and runner management."""

import argparse

from mulebox.runners import commands_hooks, commands_manage


def register(sub: argparse._SubParsersAction) -> None:
    commands_hooks.register(sub)
    commands_manage.register(sub)
