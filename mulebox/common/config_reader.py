"""Typed, strict reading of parsed config files, for :mod:`mulebox.common.config`.

Split out of config.py to keep each file small. :class:`ConfigError` is defined here and
re-exported by config.py, which is where callers import it from.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, NoReturn

import yaml

from mulebox.common.errors import MuleboxError

REQUIRED: Any = object()
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class ConfigError(MuleboxError):
    """A configuration file is missing, unreadable or invalid."""

    def __init__(self, path: Path | str, field: str | None, problem: str) -> None:
        self.path = Path(path)
        self.field = field
        self.problem = problem
        where = f"{path}: {field}" if field else f"{path}"
        super().__init__(f"{where}: {problem}")


class Reader:
    """Typed access to one mapping of a config file; remembers which keys were read."""

    def __init__(self, path: Path, data: Any, prefix: str = "") -> None:
        self.path, self.prefix, self.seen = path, prefix, set()
        if not isinstance(data, dict):
            where = prefix.rstrip(".") or None
            self.fail_at(where, f"must be a mapping, got {kind(data)}")
        self.data: dict[Any, Any] = data

    def fail_at(self, where: str | None, problem: str) -> NoReturn:
        raise ConfigError(self.path, where, problem)

    def fail(self, key: str, problem: str) -> NoReturn:
        self.fail_at(self.prefix + key, problem)

    def get(self, key: str, default: Any = REQUIRED) -> Any:
        self.seen.add(key)
        if key in self.data and self.data[key] is not None:
            return self.data[key]
        if default is REQUIRED:
            self.fail(key, "is required")
        return default

    def text(self, key: str, default: Any = REQUIRED) -> Any:
        value = self.get(key, default)
        if self.data.get(key) is None:
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            self.fail(key, f"must be a string, got {kind(value)}; put the value in quotes")
        if not isinstance(value, str) or not value.strip():
            self.fail(key, f"must be a non-empty string, got {kind(value)}")
        return value

    def name(self, key: str) -> str:
        value = self.text(key)
        if not NAME_RE.fullmatch(value):
            self.fail(key, "may only contain letters, digits, '.', '_' and '-'")
        return value

    def ssh_target(self, key: str, default: Any = REQUIRED) -> Any:
        value = self.text(key, default)
        if value is not None and (value.startswith("-") or any(c.isspace() for c in value)):
            self.fail(key, "must be an ssh target without spaces, not starting with '-'")
        return value

    def integer(self, key: str, default: int, low: int, high: int | None = None) -> int:
        value = self.get(key, default)
        if not isinstance(value, int) or isinstance(value, bool):
            self.fail(key, f"must be an integer, got {kind(value)}")
        if value < low or (high is not None and value > high):
            limit = f"between {low} and {high}" if high is not None else f"at least {low}"
            self.fail(key, f"must be {limit}, got {value}")
        return value

    def boolean(self, key: str, default: bool) -> bool:
        value = self.get(key, default)
        if not isinstance(value, bool):
            self.fail(key, f"must be true or false, got {kind(value)}")
        return value

    def strings(self, key: str) -> tuple[str, ...]:
        value = self.get(key, [])
        if not isinstance(value, list):
            self.fail(key, f"must be a list of strings, got {kind(value)}")
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                self.fail(f"{key}[{index}]", f"must be a non-empty string, got {kind(item)}")
        return tuple(value)

    def table(self, key: str, required: bool = False) -> Reader:
        value = self.get(key, REQUIRED if required else {})
        return Reader(self.path, value, f"{self.prefix}{key}.")

    def string_map(self, key: str, required: bool = False) -> dict[str, str]:
        sub = self.table(key, required)
        result = {}
        for name in sub.data:
            if not isinstance(name, str) or not name.strip():
                sub.fail_at(self.prefix + key, f"keys must be non-empty strings, got {name!r}")
            result[name] = sub.text(name)
        return result

    def finish(self) -> None:
        unknown = [key for key in self.data if key not in self.seen]
        if unknown:
            known = ", ".join(sorted(self.seen))
            self.fail(str(unknown[0]), f"unknown key; expected one of: {known}")


def kind(value: Any) -> str:
    if value is None:
        return "nothing"
    return f"{type(value).__name__} {value!r}" if not isinstance(value, dict) else "mapping"


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise ConfigError(path, None, "file not found") from None
    except OSError as exc:
        raise ConfigError(path, None, f"cannot read file: {exc.strerror or exc}") from None


def load_yaml(path: Path) -> Any:
    try:
        data = yaml.safe_load(read_bytes(path))
    except yaml.YAMLError as exc:
        raise ConfigError(path, None, f"invalid YAML: {exc}") from None
    if data is None:
        raise ConfigError(path, None, "file is empty")
    return data


def load_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(read_bytes(path).decode("utf-8"))
    except UnicodeDecodeError:
        raise ConfigError(path, None, "file is not valid UTF-8") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(path, None, f"invalid TOML: {exc}") from None
