"""Compose files as Compose reads them: merged in order, `!reset` and `!override` applied.

Plain YAML rejects those two tags, and a project using them is exactly one with a stack worth
checking. Read off `docker compose config` (Compose 5.6): `!reset` removes the key, whatever
value it carries and in whichever file it stands, and a later file may set the key again;
`!override` replaces what earlier files said instead of merging with it.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from mulebox.common.config_reader import ConfigError, load_yaml

Model = dict[str, Any]
_RESET: Any = object()


@dataclass(frozen=True)
class _Override:
    value: Any


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader, plus the two tags Compose adds."""


def _reset(_loader: yaml.SafeLoader, _node: yaml.Node) -> Any:
    return _RESET


def _override(loader: yaml.SafeLoader, node: yaml.Node) -> _Override:
    """The value as if untagged, so `!override true` is a boolean, not the word."""
    value = node.value if isinstance(node, yaml.ScalarNode) else None
    untagged = copy.copy(node)
    untagged.tag = loader.resolve(type(node), value, (True, False))
    return _Override(loader.construct_object(untagged, deep=True))


_ComposeLoader.add_constructor("!reset", _reset)
_ComposeLoader.add_constructor("!override", _override)


def _merged(base: Any, over: Any) -> Any:
    """Later files win, except that maps merge and lists add up, as Compose does."""
    base = base.value if isinstance(base, _Override) else base
    if isinstance(over, _Override):
        return over
    if isinstance(base, dict) and isinstance(over, dict):
        return {**base, **{key: _merged(base[key], value) if key in base else value
                           for key, value in over.items()}}
    return [*base, *over] if isinstance(base, list) and isinstance(over, list) else over


def _settled(value: Any) -> Any:
    """The merged value with the tags used up."""
    value = value.value if isinstance(value, _Override) else value
    if isinstance(value, dict):
        return {key: _settled(item) for key, item in value.items() if item is not _RESET}
    if isinstance(value, list):
        return [_settled(item) for item in value if item is not _RESET]
    return value


def load(root: Path, files: tuple[str, ...]) -> Model:
    """`files` under `root` as one model, before any variable or profile is looked at."""
    merged: Model = {}
    for name in files:
        data = load_yaml(root / name, _ComposeLoader)
        if not isinstance(data, dict):
            raise ConfigError(root / name, None, "is not a compose file")
        merged = _merged(merged, data)
    return _settled(merged)
