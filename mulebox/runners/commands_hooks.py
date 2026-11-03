"""CLI subcommands for runner hooks (docs/interfaces-m3.md)."""

import argparse


def register(sub: argparse._SubParsersAction) -> None:
    """Add the subcommands. Each sets func=handler(args) -> int."""
