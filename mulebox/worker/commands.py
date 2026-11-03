"""CLI subcommands of the worker package (docs/interfaces-m1.md, CLI)."""

import argparse


def register(sub: argparse._SubParsersAction) -> None:
    """Add this package's subcommands. Each sets func=handler(args) -> int."""
